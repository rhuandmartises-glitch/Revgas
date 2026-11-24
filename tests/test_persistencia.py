"""Cadastro lembrado pelo número do WhatsApp, mesmo depois de reiniciar o servidor.
Rodar: python -m unittest -v tests.test_persistencia"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from revgas_atendimento.composicao_pedido import montar_atendimento_com_pedido_de_gas
from revgas_atendimento.config import CAMINHO_BANCO_PADRAO, Configuracao
from revgas_atendimento.modelos import Cadastro, Entrada
from revgas_atendimento.modelos_pedido import Pedido, TipoBotijao
from revgas_atendimento.persistencia_sqlite import BancoSqlite, CadastrosSqlite, PedidosSqlite

from tests.apoio import TELEFONE, TELEFONE_CONTATO, TELEFONE_CONTATO_FORMATADO

OUTRO_TELEFONE = "5521988887777"
# A montagem pela Configuracao (sem consulta online) confere o CEP e pede o endereço digitado.
ENDERECO_DIGITADO = ("01001-000", "Praça da Sé, 120 - Sé")
ENDERECO = "Praça da Sé, 120 - Sé - CEP 01001-000"
CADASTRO = ("oi", "Maria da Silva", TELEFONE_CONTATO, *ENDERECO_DIGITADO, "sim")


class ComBancoTemporario(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._pasta = tempfile.TemporaryDirectory()
        self.caminho = str(Path(self._pasta.name) / "sub" / "revgas.sqlite3")  # cria a subpasta sozinho

    def tearDown(self) -> None:
        self._pasta.cleanup()

    def servidor(self):
        """Cada chamada é um "servidor novo": só o arquivo do banco passa de um para o outro."""
        return montar_atendimento_com_pedido_de_gas(Configuracao(caminho_banco=self.caminho))

    @staticmethod
    async def conversar(servidor, telefone: str, *falas: str):
        resposta = None
        for fala in falas:
            resposta = await servidor.atender(telefone, Entrada(texto=fala))
        return resposta


class TesteCadastroLembradoDepoisDeReiniciar(ComBancoTemporario):
    async def test_novo_pedido_depois_de_reiniciar_usa_o_cadastro(self):
        primeiro = self.servidor()
        await self.conversar(primeiro, TELEFONE, *CADASTRO)

        reiniciado = self.servidor()  # memória zerada, banco no disco
        saudacao = await self.conversar(reiniciado, TELEFONE, "quero gás")
        self.assertIn("Oi de novo, Maria", saudacao.texto)

        resumo = await self.conversar(reiniciado, TELEFONE, "p13", "2", "pix")
        for dado in ("Maria da Silva", TELEFONE_CONTATO_FORMATADO, ENDERECO):
            self.assertIn(dado, resumo.texto)  # não perguntou o endereço: foi direto ao resumo
        confirmado = await self.conversar(reiniciado, TELEFONE, "sim")
        self.assertIn("confirmado", confirmado.texto)

        pedidos = await PedidosSqlite(BancoSqlite(self.caminho)).listar_por_telefone(TELEFONE)
        self.assertEqual([(p.tipo_botijao, p.quantidade) for p in pedidos], [(TipoBotijao.P13, 2)])

    async def test_oi_de_cliente_cadastrado_depois_de_reiniciar(self):
        await self.conversar(self.servidor(), TELEFONE, *CADASTRO)
        resposta = await self.conversar(self.servidor(), TELEFONE, "oi")
        self.assertIn("já está completo", resposta.texto)

    async def test_outro_numero_nao_ve_o_cadastro(self):
        await self.conversar(self.servidor(), TELEFONE, *CADASTRO)
        reiniciado = self.servidor()
        saudacao = await self.conversar(reiniciado, OUTRO_TELEFONE, "quero gás")
        self.assertNotIn("Maria", saudacao.texto)
        pergunta = await self.conversar(reiniciado, OUTRO_TELEFONE, "p13", "1")
        self.assertIn("endereço de entrega", pergunta.texto)  # sem cadastro: pergunta o endereço

    async def test_atualizar_troca_o_endereco_guardado(self):
        await self.conversar(self.servidor(), TELEFONE, *CADASTRO)
        await self.conversar(self.servidor(), TELEFONE, "atualizar", "Maria da Silva", TELEFONE_CONTATO,
                             "01310-100", "Avenida Paulista, 500 - Bela Vista", "sim")
        cadastro = await CadastrosSqlite(BancoSqlite(self.caminho)).buscar_por_telefone(TELEFONE)
        self.assertEqual(cadastro.endereco, "Avenida Paulista, 500 - Bela Vista - CEP 01310-100")


class TesteRepositoriosSqlite(ComBancoTemporario):
    async def test_cadastro_salvo_e_atualizado_sem_duplicar(self):
        cadastros = CadastrosSqlite(BancoSqlite(self.caminho))
        await cadastros.salvar(Cadastro(TELEFONE, "Maria", "11988887777", "Rua A, 1 - Centro"))
        await cadastros.salvar(Cadastro(TELEFONE, "Maria Silva", "11988887777", "Rua B, 2 - Centro"))
        self.assertEqual((await cadastros.buscar_por_telefone(TELEFONE)).nome, "Maria Silva")
        self.assertIsNone(await cadastros.buscar_por_telefone(OUTRO_TELEFONE))

    async def test_pedidos_em_ordem_e_separados_por_numero(self):
        pedidos = PedidosSqlite(BancoSqlite(self.caminho))
        await pedidos.salvar(Pedido(TELEFONE, TipoBotijao.P13, 1, "Rua A, 1 - Centro"))
        await pedidos.salvar(Pedido(OUTRO_TELEFONE, TipoBotijao.P45, 2, "Rua C, 3 - Centro"))
        await pedidos.salvar(Pedido(TELEFONE, TipoBotijao.P20, 3, "Rua A, 1 - Centro"))
        lista = await pedidos.listar_por_telefone(TELEFONE)
        self.assertEqual([p.tipo_botijao for p in lista], [TipoBotijao.P13, TipoBotijao.P20])


class TesteConfiguracaoDoBanco(unittest.TestCase):
    def test_servidor_guarda_em_disco_por_padrao(self):
        with patch.dict(os.environ, {"N8N_API_KEY": "k"}, clear=True):
            self.assertEqual(Configuracao.do_ambiente().caminho_banco, CAMINHO_BANCO_PADRAO)

    def test_caminho_do_banco_pelo_ambiente(self):
        with patch.dict(os.environ, {"N8N_API_KEY": "k", "REVGAS_BANCO": "C:/dados/rev.db"}, clear=True):
            self.assertEqual(Configuracao.do_ambiente().caminho_banco, "C:/dados/rev.db")

    def test_testes_e_demos_continuam_em_memoria(self):
        self.assertIsNone(Configuracao().caminho_banco)


if __name__ == "__main__":
    unittest.main()
