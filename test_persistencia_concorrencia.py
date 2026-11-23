"""Integração SQLite e worker: reinício, concorrência, deduplicação e retries."""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from revgas_atendimento.atendimento import ServicoDeAtendimento
from revgas_atendimento.composicao import montar_componentes
from revgas_atendimento.config import Configuracao
from revgas_atendimento.modelos import Cadastro, Etapa, Sessao, IntegracaoError
from revgas_atendimento.persistencia import BancoSQLite, CadastrosSQLite, CaixaDeMensagensSQLite, SessoesSQLite
from revgas_atendimento.simulacoes import evento_de_texto, WhatsAppEmMemoria
from revgas_atendimento.whatsapp import extrair_mensagens
from revgas_atendimento.worker import WorkerDeMensagens

TELEFONE = '5511999990000'


def evento(texto: str, identificador: str) -> dict:
    payload = evento_de_texto(TELEFONE, texto)
    payload['entry'][0]['changes'][0]['value']['messages'][0]['id'] = identificador
    return payload


class TestesPersistenciaEWorker(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.caminho = str(Path(self.temp.name) / 'dados.sqlite3')
        self.banco = BancoSQLite(self.caminho)
        self.caixa = CaixaDeMensagensSQLite(self.banco, 5)
        self.whatsapp = WhatsAppEmMemoria(imprimir=False)
        self.worker = WorkerDeMensagens(
            self.banco, self.caixa,
            ServicoDeAtendimento(CadastrosSQLite(self.banco), SessoesSQLite(self.banco, 900)),
            self.whatsapp,
        )

    async def test_cadastro_e_sessao_sobrevivem_reinicio(self):
        cadastro = Cadastro(TELEFONE, 'Maria da Silva', 'maria@email.com', 'Rua das Flores 120')
        await CadastrosSQLite(self.banco).salvar(cadastro)
        await SessoesSQLite(self.banco, 900).salvar(Sessao(TELEFONE, Etapa.EMAIL, nome='Maria da Silva'))
        novo = BancoSQLite(self.caminho)
        self.assertEqual(await CadastrosSQLite(novo).buscar_por_telefone(TELEFONE), cadastro)
        self.assertEqual((await SessoesSQLite(novo, 900).obter(TELEFONE)).etapa, Etapa.EMAIL)

    async def test_mensagem_duplicada_e_concorrente_responde_uma_vez(self):
        recebida = extrair_mensagens(evento('oi', 'wa-1'))
        await asyncio.gather(*(self.caixa.registrar(recebida) for _ in range(12)))
        self.assertEqual(await self.caixa.situacao('wa-1'), 'pending')
        await asyncio.gather(*(self.worker.executar_uma() for _ in range(12)))
        self.assertEqual(await self.caixa.situacao('wa-1'), 'sent')
        self.assertEqual(len(self.whatsapp.enviadas), 1)

    async def test_mensagens_do_mesmo_telefone_mantem_ordem(self):
        for i, fala in enumerate(['oi', 'Maria da Silva', 'maria@email.com', 'Rua das Flores 120']):
            await self.caixa.registrar(extrair_mensagens(evento(fala, f'wa-{i}')))
        await asyncio.gather(*(self.worker.executar_uma() for _ in range(8)))
        # Apenas o primeiro evento pode ser processado inicialmente; o restante não é descartado.
        for _ in range(4):
            await self.worker.executar_uma()
        respostas = [m['text']['body'] if m['type'] == 'text' else m['interactive']['body']['text']
                     for _, m in self.whatsapp.enviadas]
        self.assertEqual(len(respostas), 4)
        self.assertIn('nome completo', respostas[0])
        self.assertIn('e-mail', respostas[1])
        self.assertIn('endereço', respostas[2])
        self.assertIn('Confere?', respostas[3])

    async def test_resposta_preparada_reenviada_sem_reexecutar_regra(self):
        await self.caixa.registrar(extrair_mensagens(evento('oi', 'wa-falha')))
        class FalhaUmaVez(WhatsAppEmMemoria):
            def __init__(self):
                super().__init__(imprimir=False)
                self.chamadas = 0
            async def enviar(self, telefone, mensagem):
                self.chamadas += 1
                if self.chamadas == 1:
                    raise IntegracaoError('indisponível')
                await super().enviar(telefone, mensagem)
        instavel = FalhaUmaVez()
        self.worker.whatsapp = instavel
        with self.assertLogs('revgas_atendimento.worker', level='ERROR'):
            await self.worker.executar_uma()
        self.assertEqual(await self.caixa.situacao('wa-falha'), 'ready')
        self.assertEqual((await SessoesSQLite(self.banco, 900).obter(TELEFONE)).etapa, Etapa.NOME)
        with self.banco.conexao() as con:
            con.execute("UPDATE mensagens SET disponivel_em=0 WHERE id='wa-falha'")
        await self.worker.executar_uma()
        self.assertEqual(await self.caixa.situacao('wa-falha'), 'sent')
        self.assertEqual(len(instavel.enviadas), 1)

    async def test_restart_reprocessa_inbox_nao_concluida(self):
        await self.caixa.registrar(extrair_mensagens(evento('oi', 'wa-restart')))
        novo_banco = BancoSQLite(self.caminho)
        novo_caixa = CaixaDeMensagensSQLite(novo_banco)
        novo_whatsapp = WhatsAppEmMemoria(imprimir=False)
        novo_worker = WorkerDeMensagens(novo_banco, novo_caixa,
            ServicoDeAtendimento(CadastrosSQLite(novo_banco), SessoesSQLite(novo_banco, 900)), novo_whatsapp)
        await novo_worker.executar_uma()
        self.assertEqual(await novo_caixa.situacao('wa-restart'), 'sent')

    async def test_falha_na_regra_nao_confirma_processamento(self):
        class Erro:
            async def atender(self, telefone, entrada):
                raise RuntimeError('falha')
        self.worker.atendimento = Erro()
        await self.caixa.registrar(extrair_mensagens(evento('oi', 'wa-fail-logic')))
        with self.assertLogs('revgas_atendimento.worker', level='ERROR'):
            await self.worker.executar_uma()
        self.assertEqual(await self.caixa.situacao('wa-fail-logic'), 'pending')
        self.assertIsNone(await SessoesSQLite(self.banco, 900).obter(TELEFONE))

    async def test_composicao_por_configuracao_usa_sqlite(self):
        config = Configuracao('segredo', 'token', caminho_banco=self.caminho)
        componentes = montar_componentes(config)
        self.assertIsInstance(componentes.atendimento._cadastros, CadastrosSQLite)
        self.assertIsInstance(componentes.whatsapp, WhatsAppEmMemoria)


class TesteConfiguracao(unittest.TestCase):
    def test_env_valida_credenciais_e_banco(self):
        with tempfile.TemporaryDirectory() as pasta:
            with patch.dict('os.environ', {
                'WA_APP_SECRET': ' segredo ', 'WA_VERIFY_TOKEN': ' token ',
                'WA_ACCESS_TOKEN': ' tok ', 'WA_PHONE_NUMBER_ID': ' 123 ',
                'REVGAS_DB_PATH': str(Path(pasta) / 'db.sqlite3'),
            }, clear=True):
                config = Configuracao.do_ambiente()
        self.assertEqual(config.credenciais_whatsapp.token_acesso, 'tok')
        self.assertEqual(config.token_verificacao_whatsapp, 'token')
