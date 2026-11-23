"""Falhas controladas: confirmação, locks, recuperação, inbox e saúde HTTP."""
from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from revgas_atendimento.api import criar_app
from revgas_atendimento.atendimento import ServicoDeAtendimento
from revgas_atendimento.config import Configuracao
from revgas_atendimento.modelos import EntregaIncertaError
from revgas_atendimento.persistencia import (
    BancoSQLite, CaixaDeMensagensSQLite, CadastrosSQLite, SessoesSQLite,
)
from revgas_atendimento.simulacoes import WhatsAppEmMemoria, evento_de_texto
from revgas_atendimento.whatsapp import extrair_mensagens
from revgas_atendimento.worker import WorkerDeMensagens

TELEFONE = '5511999990000'


def evento(texto: str, identificador: str, telefone: str = TELEFONE):
    payload = evento_de_texto(telefone, texto)
    payload['entry'][0]['changes'][0]['value']['messages'][0]['id'] = identificador
    return extrair_mensagens(payload)


class TestesDeFalhas(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / 'revgas.db')
        self.banco = BancoSQLite(self.path)
        self.caixa = CaixaDeMensagensSQLite(self.banco)
        self.gateway = WhatsAppEmMemoria(imprimir=False)
        atendimento = ServicoDeAtendimento(CadastrosSQLite(self.banco), SessoesSQLite(self.banco, 900))
        self.worker = WorkerDeMensagens(self.banco, self.caixa, atendimento, self.gateway)

    async def test_falha_de_confirmacao_apos_envio_nao_interrompe_worker(self):
        await self.caixa.registrar(evento('oi', 'm-ack'))
        with patch.object(self.caixa, 'enviado', new=AsyncMock(side_effect=sqlite3.OperationalError('db busy'))):
            with self.assertLogs('revgas_atendimento.worker', level='ERROR'):
                self.assertTrue(await self.worker.executar_uma())
        self.assertEqual(await self.caixa.situacao('m-ack'), 'uncertain')
        self.assertEqual(len(self.gateway.enviadas), 1)
        self.assertFalse(await self.worker.executar_uma())
        self.assertEqual(len(self.gateway.enviadas), 1)

    async def test_se_o_banco_cair_ao_marcar_incerta_lease_isola_envio(self):
        await self.caixa.registrar(evento('oi', 'm-lease'))
        with patch.object(self.caixa, 'enviado', new=AsyncMock(side_effect=sqlite3.OperationalError('off'))), \
             patch.object(self.caixa, 'marcar_incerta', new=AsyncMock(side_effect=sqlite3.OperationalError('off'))):
            with self.assertLogs('revgas_atendimento.worker', level='ERROR'):
                await self.worker.executar_uma()
        self.assertEqual(await self.caixa.situacao('m-lease'), 'sending')
        with self.banco.conexao() as con:
            con.execute("UPDATE mensagens SET lease_ate=0 WHERE id='m-lease'")
        self.assertFalse(await self.worker.executar_uma())
        self.assertEqual(await self.caixa.situacao('m-lease'), 'uncertain')
        self.assertEqual(len(self.gateway.enviadas), 1)

    async def test_falha_de_rede_com_envio_incerto_nao_retransmite(self):
        await self.caixa.registrar(evento('oi', 'm-rede'))
        self.worker.whatsapp = AsyncMock()
        self.worker.whatsapp.enviar.side_effect = EntregaIncertaError('timeout')
        with self.assertLogs('revgas_atendimento.worker', level='ERROR'):
            await self.worker.executar_uma()
        self.assertEqual(await self.caixa.situacao('m-rede'), 'uncertain')
        self.assertFalse(await self.worker.executar_uma())
        self.worker.whatsapp.enviar.assert_awaited_once()

    async def test_lease_de_processamento_reinicia_sem_perder_mensagem(self):
        await self.caixa.registrar(evento('oi', 'm-processing'))
        item = await self.caixa.reivindicar()
        self.assertIsNotNone(item)
        with self.banco.conexao() as con:
            con.execute("UPDATE mensagens SET lease_ate=0 WHERE id='m-processing'")
        await self.worker.executar_uma()
        self.assertEqual(await self.caixa.situacao('m-processing'), 'sent')

    async def test_dead_bloqueia_mensagens_posteriores_e_reabertura_manual(self):
        caixa = CaixaDeMensagensSQLite(self.banco, tentativas_maximas=1)
        await caixa.registrar(evento('oi', 'm-dead') + evento('Maria da Silva', 'm-next'))
        item = await caixa.reivindicar()
        self.assertEqual(item['id'], 'm-dead')
        await caixa.falhou('m-dead', 'pending')
        self.assertEqual(await caixa.situacao('m-dead'), 'dead')
        self.assertIsNone(await caixa.reivindicar())
        self.assertTrue(await caixa.reprocessar_manualmente('m-dead'))
        worker = WorkerDeMensagens(self.banco, caixa, self.worker.atendimento, self.gateway)
        self.assertTrue(await worker.executar_uma())
        self.assertTrue(await worker.executar_uma())
        self.assertEqual(await caixa.situacao('m-next'), 'sent')
        self.assertEqual(len(self.gateway.enviadas), 2)

    async def test_mensagem_incerta_exige_autorizacao_de_reenvio(self):
        await self.caixa.registrar(evento('oi', 'm-uncertain'))
        with patch.object(self.caixa, 'enviado', new=AsyncMock(side_effect=RuntimeError('falha'))):
            with self.assertLogs('revgas_atendimento.worker', level='ERROR'):
                await self.worker.executar_uma()
        self.assertFalse(await self.caixa.reprocessar_manualmente('m-uncertain'))
        self.assertTrue(await self.caixa.reprocessar_manualmente('m-uncertain', reenviar_incerta=True))
        self.assertEqual(await self.caixa.situacao('m-uncertain'), 'ready')
        await self.worker.executar_uma()
        self.assertEqual(len(self.gateway.enviadas), 2)
        self.assertEqual(await self.caixa.situacao('m-uncertain'), 'sent')

    async def test_multiplos_workers_e_clientes_independentes(self):
        for i in range(10):
            numero = f'551198880{i:04d}'
            await self.caixa.registrar(evento('oi', f'm-{i}', numero))
        outro = WorkerDeMensagens(BancoSQLite(self.path),
                                 CaixaDeMensagensSQLite(BancoSQLite(self.path)),
                                 self.worker.atendimento, self.gateway)
        await asyncio.gather(*[self.worker.executar_uma() for _ in range(15)],
                             *[outro.executar_uma() for _ in range(15)])
        self.assertEqual(len(self.gateway.enviadas), 10)
        self.assertEqual((await self.caixa.resumo()).get('sent'), 10)

    async def test_supervisor_recupera_erro_e_aceita_cancelamento(self):
        calls = 0
        async def instavel():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise sqlite3.OperationalError('disco indisponível')
            return False
        self.worker.executar_uma = instavel
        with self.assertLogs('revgas_atendimento.worker', level='ERROR'):
            task = asyncio.create_task(self.worker.executar_continuamente(0.001))
            await asyncio.sleep(0.27)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertGreaterEqual(calls, 2)
        self.assertFalse(self.worker.ativo)

    async def test_mensagens_de_um_telefone_nao_se_atropelam_em_dois_workers(self):
        for indice, texto in enumerate(('oi', 'Maria da Silva', 'maria@email.com', 'Rua das Flores 120')):
            await self.caixa.registrar(evento(texto, f'fila-{indice}'))
        outro_banco = BancoSQLite(self.path)
        outro = WorkerDeMensagens(outro_banco, CaixaDeMensagensSQLite(outro_banco),
                                 ServicoDeAtendimento(CadastrosSQLite(outro_banco),
                                                      SessoesSQLite(outro_banco, 900)), self.gateway)
        await asyncio.gather(*[self.worker.executar_uma() for _ in range(8)],
                             *[outro.executar_uma() for _ in range(8)])
        self.assertEqual((await self.caixa.resumo()).get('sent'), 4)
        textos = [msg['text']['body'] if msg['type'] == 'text' else msg['interactive']['body']['text']
                  for _, msg in self.gateway.enviadas]
        self.assertIn('nome completo', textos[0])
        self.assertIn('e-mail', textos[1])
        self.assertIn('endereço', textos[2])
        self.assertIn('Confere?', textos[3])

    async def test_mensagem_duplicada_nao_cria_novo_processamento(self):
        await asyncio.gather(*(self.caixa.registrar(evento('oi', 'm-dupla')) for _ in range(15)))
        await asyncio.gather(*(self.worker.executar_uma() for _ in range(15)))
        self.assertEqual(len(self.gateway.enviadas), 1)
        self.assertEqual(await self.caixa.situacao('m-dupla'), 'sent')

    async def test_transacao_desfaz_atualizacao_se_falhar(self):
        await self.caixa.registrar(evento('oi', 'm-rollback'))
        with self.assertRaises(sqlite3.OperationalError):
            async with self.banco.transacao() as con:
                con.execute("UPDATE mensagens SET status='sent' WHERE id='m-rollback'")
                raise sqlite3.OperationalError('falha artificial')
        self.assertEqual(await self.caixa.situacao('m-rollback'), 'pending')

    async def test_entrada_persiste_apos_reiniciar(self):
        await self.caixa.registrar(evento('oi', 'm-restart'))
        novo = CaixaDeMensagensSQLite(BancoSQLite(self.path))
        self.assertEqual(await novo.situacao('m-restart'), 'pending')
        self.assertEqual((await novo.resumo())['pending'], 1)


class TesteHealth(unittest.TestCase):
    def test_saude_expoe_somente_estado_sem_dados_pessoais(self):
        from fastapi.testclient import TestClient
        with tempfile.TemporaryDirectory() as pasta:
            app = criar_app(Configuracao('segredo-de-demo', 'token-de-demo',
                                        caminho_banco=str(Path(pasta) / 'base.db')))
            with TestClient(app) as client:
                resposta = client.get('/health')
                self.assertEqual(resposta.status_code, 200)
                self.assertEqual(resposta.json(), {
                    'status': 'ok', 'worker': 'running', 'database': 'ok', 'mode': 'simulation'
                })
            with TestClient(app) as client:
                resposta = client.get('/health')
                self.assertEqual(resposta.status_code, 200)

    def test_banco_indisponivel_retornara_503_sem_expor_detalhes(self):
        from fastapi.testclient import TestClient
        with tempfile.TemporaryDirectory() as pasta:
            app = criar_app(Configuracao('s', 'v', caminho_banco=str(Path(pasta) / 'base.db')))
            with TestClient(app) as client:
                with patch.object(app.state.componentes.banco, 'conexao',
                                  side_effect=sqlite3.OperationalError('erro interno privado')):
                    with self.assertLogs('revgas_atendimento.api', level='ERROR'):
                        resposta = client.get('/health')
                self.assertEqual(resposta.status_code, 503)
                self.assertEqual(resposta.json()['database'], 'unavailable')
                self.assertNotIn('privado', resposta.text)

    def test_worker_nao_iniciado_retornara_503(self):
        from fastapi.testclient import TestClient
        with tempfile.TemporaryDirectory() as pasta:
            app = criar_app(Configuracao('s', 'v', caminho_banco=str(Path(pasta) / 'base.db')))
            # Sem lifespan iniciado a aplicação não está pronta.
            client = TestClient(app)
            resposta = client.get('/health')
            self.assertEqual(resposta.status_code, 503)
            self.assertEqual(resposta.json()['worker'], 'stopped')
