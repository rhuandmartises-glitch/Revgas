"""Forma de pagamento e prazo de cancelamento do pedido.
Rodar: python -m unittest -v tests.test_pagamento_e_cancelamento"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from revgas_atendimento.atendimento import ServicoDeAtendimento
from revgas_atendimento.atendimento_integrado import ServicoDeAtendimentoIntegrado
from revgas_atendimento.atendimento_pedido import MENSAGEM_SEM_PEDIDO_PARA_CANCELAR, ServicoDePedido
from revgas_atendimento.config import Configuracao
from revgas_atendimento.modelos import ConfiguracaoInvalidaError, DadoInvalidoError, Entrada
from revgas_atendimento.modelos_pedido import FormaPagamento, Pedido, StatusPedido, TipoBotijao, formatar_reais
from revgas_atendimento.persistencia_sqlite import BancoSqlite, PedidosSqlite
from revgas_atendimento.simulacoes import CadastrosEmMemoria, CepsEmMemoria, SessoesEmMemoria
from revgas_atendimento.simulacoes_pedido import PedidosEmMemoria
from revgas_atendimento.validacao_pedido import validar_forma_pagamento, validar_troco
from tests.apoio import ENDERECO, FALAS_ENDERECO, TELEFONE, TTL


class RelogioDeData:
    """Relógio controlado pelo teste, com fuso horário (como o do servidor)."""

    def __init__(self) -> None:
        self.agora = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.agora

    def avancar(self, **intervalo) -> None:
        self.agora += timedelta(**intervalo)


class Loja:
    """Pedido de gás com relógio falso; prazo de cancelamento de 5 minutos, a menos que se diga outro."""

    def __init__(self, prazo: timedelta = timedelta(minutes=5)) -> None:
        self.relogio = RelogioDeData()
        self.pedidos = PedidosEmMemoria()
        self.servico = ServicoDePedido(
            self.pedidos, SessoesEmMemoria(TTL), None, CepsEmMemoria(), prazo_cancelamento=prazo, relogio=self.relogio
        )

    async def texto(self, *textos: str):
        resposta = None
        for texto in textos:
            resposta = await self.servico.atender(TELEFONE, Entrada(texto=texto))
        return resposta

    async def ate_o_pagamento(self):
        return await self.texto("gás", "p13", "2", *FALAS_ENDERECO)

    async def pedido_confirmado(self, pagamento: str = "pix"):
        await self.ate_o_pagamento()
        return await self.texto(pagamento, "sim")

    async def ultimo(self) -> Pedido:
        return await self.pedidos.ultimo_por_telefone(TELEFONE)


class TesteValidacaoDoPagamento(unittest.TestCase):
    def test_formas_de_pagamento_em_frase(self):
        casos = {
            "pix": FormaPagamento.PIX,
            "Vou pagar no PIX": FormaPagamento.PIX,
            "dinheiro": FormaPagamento.DINHEIRO,
            "em espécie": FormaPagamento.DINHEIRO,
            "cartão de débito": FormaPagamento.DEBITO,
            "no crédito, por favor": FormaPagamento.CREDITO,
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertIs(validar_forma_pagamento(texto), esperado)

    def test_so_cartao_pergunta_debito_ou_credito(self):
        with self.assertRaises(DadoInvalidoError) as contexto:
            validar_forma_pagamento("no cartão")
        self.assertIn("débito ou de crédito", str(contexto.exception))

    def test_forma_desconhecida(self):
        with self.assertRaises(DadoInvalidoError):
            validar_forma_pagamento("cheque")

    def test_troco(self):
        self.assertEqual(validar_troco("troco para 100"), Decimal("100.00"))
        self.assertEqual(validar_troco("R$ 50,50"), Decimal("50.50"))
        self.assertIsNone(validar_troco("não"))
        self.assertIsNone(validar_troco("Não precisa"))
        for invalido in ("sim", "1.000", "0", "5000"):
            with self.subTest(texto=invalido):
                with self.assertRaises(DadoInvalidoError):
                    validar_troco(invalido)

    def test_formatacao_em_reais(self):
        self.assertEqual(formatar_reais(Decimal("100")), "R$ 100,00")
        self.assertEqual(formatar_reais(Decimal("1234.5")), "R$ 1.234,50")


class TesteFluxoDoPagamento(unittest.IsolatedAsyncioTestCase):
    async def test_pergunta_o_pagamento_depois_do_endereco(self):
        pergunta = await Loja().ate_o_pagamento()
        self.assertIn("Como prefere pagar? O pagamento é na entrega", pergunta.texto)

    async def test_dinheiro_pergunta_troco_e_mostra_no_resumo(self):
        loja = Loja()
        await loja.ate_o_pagamento()
        pergunta = await loja.texto("dinheiro")
        self.assertIn("troco", pergunta.texto)
        resumo = await loja.texto("troco para 100")
        self.assertIn("Pagamento: Dinheiro, na entrega (troco para R$ 100,00)", resumo.texto)

        confirmado = await loja.texto("sim")
        self.assertIn("Pagamento: Dinheiro, na entrega (troco para R$ 100,00)", confirmado.texto)
        pedido = await loja.ultimo()
        self.assertEqual((pedido.forma_pagamento, pedido.troco_para), (FormaPagamento.DINHEIRO, Decimal("100.00")))

    async def test_dinheiro_sem_troco(self):
        loja = Loja()
        await loja.ate_o_pagamento()
        resumo = await loja.texto("dinheiro", "não")
        self.assertIn("Pagamento: Dinheiro, na entrega (sem troco)", resumo.texto)

    async def test_cartao_sem_dizer_qual_pergunta_e_continua(self):
        loja = Loja()
        await loja.ate_o_pagamento()
        self.assertIn("débito ou de crédito", (await loja.texto("cartão")).texto)
        resumo = await loja.texto("crédito")
        self.assertIn("Pagamento: Cartão de crédito, na entrega", resumo.texto)

    async def test_trocar_pagamento_na_confirmacao(self):
        loja = Loja()
        await loja.ate_o_pagamento()
        await loja.texto("pix")
        resumo = await loja.texto("prefiro pagar no débito")
        self.assertIn("Troquei a forma de pagamento", resumo.texto)
        self.assertIn("Pagamento: Cartão de débito", resumo.texto)
        await loja.texto("sim")
        self.assertIs((await loja.ultimo()).forma_pagamento, FormaPagamento.DEBITO)

    async def test_trocar_para_dinheiro_na_confirmacao_pergunta_troco(self):
        loja = Loja()
        await loja.ate_o_pagamento()
        await loja.texto("pix")
        self.assertIn("troco", (await loja.texto("vou pagar em dinheiro")).texto)
        resumo = await loja.texto("50")
        self.assertIn("troco para R$ 50,00", resumo.texto)

    async def test_sim_no_pix_com_pix_ja_escolhido_confirma(self):
        loja = Loja()
        await loja.ate_o_pagamento()
        await loja.texto("pix")
        self.assertIn("confirmado", (await loja.texto("sim, no pix")).texto)

    async def test_trocar_endereco_depois_volta_para_confirmacao_mantendo_pagamento(self):
        loja = Loja()
        await loja.ate_o_pagamento()
        await loja.texto("pix")
        resumo = await loja.texto("01310-100", "500")
        self.assertIn("Avenida Paulista, 500", resumo.texto)
        self.assertIn("Pagamento: Pix", resumo.texto)

    async def test_cliente_cadastrado_ve_o_endereco_e_vai_para_o_pagamento(self):
        from revgas_atendimento.modelos import Cadastro

        cadastros = CadastrosEmMemoria()
        await cadastros.salvar(Cadastro(TELEFONE, "Maria da Silva", "11988887777", ENDERECO))
        servico = ServicoDePedido(PedidosEmMemoria(), SessoesEmMemoria(TTL), cadastros)
        for fala in ("gás", "p13"):
            await servico.atender(TELEFONE, Entrada(texto=fala))
        resposta = await servico.atender(TELEFONE, Entrada(texto="1"))
        self.assertIn(f"Vou entregar em: {ENDERECO}", resposta.texto)
        self.assertIn("Como prefere pagar", resposta.texto)


class TesteCancelamentoDepoisDeConfirmar(unittest.IsolatedAsyncioTestCase):
    async def test_confirmacao_avisa_o_prazo(self):
        confirmado = await Loja().pedido_confirmado()
        self.assertIn("Se precisar cancelar, mande CANCELAR em até 5 minutos", confirmado.texto)

    async def test_cancela_dentro_do_prazo(self):
        loja = Loja()
        await loja.pedido_confirmado()
        loja.relogio.avancar(minutes=4, seconds=59)
        resposta = await loja.texto("quero cancelar o pedido")
        self.assertIn("Pedido cancelado: 2x P13 (13 kg)", resposta.texto)
        self.assertIs((await loja.ultimo()).status, StatusPedido.CANCELADO)

    async def test_fora_do_prazo_nao_cancela_e_orienta(self):
        loja = Loja()
        await loja.pedido_confirmado()
        loja.relogio.avancar(minutes=12)
        resposta = await loja.texto("cancelar")
        self.assertIn("confirmado há 12 minutos", resposta.texto)
        self.assertIn("prazo para cancelar por aqui é de 5 minutos", resposta.texto)
        self.assertIn("fale com a loja", resposta.texto)
        self.assertIs((await loja.ultimo()).status, StatusPedido.CONFIRMADO)

    async def test_cancelar_duas_vezes(self):
        loja = Loja()
        await loja.pedido_confirmado()
        await loja.texto("cancelar")
        self.assertEqual((await loja.texto("cancelar")).texto, MENSAGEM_SEM_PEDIDO_PARA_CANCELAR)

    async def test_cancelar_pedido_sem_ter_pedido_nao_abre_pedido_novo(self):
        loja = Loja()
        resposta = await loja.texto("cancelar pedido")  # tem "pedido", que também começa um pedido
        self.assertEqual(resposta.texto, MENSAGEM_SEM_PEDIDO_PARA_CANCELAR)
        self.assertFalse(await loja.servico.tem_sessao_ativa(TELEFONE))

    async def test_cancelar_no_meio_do_pedido_descarta_o_rascunho(self):
        loja = Loja()
        await loja.texto("gás", "p13")
        self.assertIn("cancelei seu pedido", (await loja.texto("cancela o pedido")).texto)
        self.assertIsNone(await loja.ultimo())

    async def test_prazo_zero_desliga_o_cancelamento_pelo_whatsapp(self):
        loja = Loja(prazo=timedelta(0))
        confirmado = await loja.pedido_confirmado()
        self.assertNotIn("CANCELAR", confirmado.texto)
        loja.relogio.avancar(seconds=10)
        resposta = await loja.texto("cancelar")
        self.assertIn("o cancelamento não é feito por aqui", resposta.texto)

    async def test_cancelar_sem_conversa_aberta_chega_ao_pedido_pelo_atendimento_integrado(self):
        cadastros, sessoes = CadastrosEmMemoria(), SessoesEmMemoria(TTL)
        loja = Loja()
        integrado = ServicoDeAtendimentoIntegrado(ServicoDeAtendimento(cadastros, sessoes), sessoes, loja.servico)
        for fala in ("gás", "p13", "1", *FALAS_ENDERECO, "pix", "sim"):
            await integrado.atender(TELEFONE, Entrada(texto=fala))
        resposta = await integrado.atender(TELEFONE, Entrada(texto="cancelar"))
        self.assertIn("Pedido cancelado", resposta.texto)


class TestePedidosNoSqlite(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._pasta = tempfile.TemporaryDirectory()
        self.caminho = Path(self._pasta.name) / "revgas.sqlite3"

    def tearDown(self) -> None:
        self._pasta.cleanup()

    async def test_grava_pagamento_status_e_horario(self):
        pedidos = PedidosSqlite(BancoSqlite(self.caminho))
        criado = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
        salvo = await pedidos.salvar(Pedido(
            TELEFONE, TipoBotijao.P45, 1, ENDERECO, FormaPagamento.DINHEIRO, Decimal("100.00"), criado_em=criado
        ))
        self.assertIsNotNone(salvo.id)

        lido = await PedidosSqlite(BancoSqlite(self.caminho)).ultimo_por_telefone(TELEFONE)  # "reinício"
        self.assertEqual(lido, salvo)

        self.assertTrue(await pedidos.cancelar(salvo.id))
        self.assertFalse(await pedidos.cancelar(salvo.id))  # já estava cancelado
        self.assertIs((await pedidos.ultimo_por_telefone(TELEFONE)).status, StatusPedido.CANCELADO)

    async def test_banco_antigo_ganha_as_colunas_novas_sem_perder_pedidos(self):
        with closing(sqlite3.connect(self.caminho)) as conexao, conexao:
            conexao.execute(
                "CREATE TABLE pedidos (id INTEGER PRIMARY KEY AUTOINCREMENT, telefone TEXT NOT NULL, "
                "tipo_botijao TEXT NOT NULL, quantidade INTEGER NOT NULL, endereco_entrega TEXT NOT NULL, "
                "criado_em TEXT NOT NULL)"
            )
            conexao.execute(
                "INSERT INTO pedidos (telefone, tipo_botijao, quantidade, endereco_entrega, criado_em) "
                "VALUES (?, 'P13', 2, 'Rua A, 1', '2026-11-20T10:00:00+00:00')",
                (TELEFONE,),
            )
        antigo = await PedidosSqlite(BancoSqlite(self.caminho)).ultimo_por_telefone(TELEFONE)
        self.assertEqual((antigo.quantidade, antigo.status, antigo.forma_pagamento), (2, StatusPedido.CONFIRMADO, None))
        self.assertIn("não informado", antigo.descricao_pagamento)


class TesteConfiguracaoDoPrazo(unittest.TestCase):
    def test_padrao_e_pelo_ambiente(self):
        with patch.dict(os.environ, {"N8N_API_KEY": "k"}, clear=True):
            self.assertEqual(Configuracao.do_ambiente().prazo_cancelamento_min, 5)
        with patch.dict(os.environ, {"N8N_API_KEY": "k", "REVGAS_PRAZO_CANCELAMENTO_MIN": "15"}, clear=True):
            self.assertEqual(Configuracao.do_ambiente().prazo_cancelamento_min, 15)

    def test_valor_invalido_falha_cedo(self):
        for valor in ("cinco", "-1", "5000"):
            with self.subTest(valor=valor):
                with patch.dict(os.environ, {"N8N_API_KEY": "k", "REVGAS_PRAZO_CANCELAMENTO_MIN": valor}, clear=True):
                    with self.assertRaises(ConfiguracaoInvalidaError):
                        Configuracao.do_ambiente()


if __name__ == "__main__":
    unittest.main()
