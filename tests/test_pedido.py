"""Testes do pedido de gás e da integração com o atendimento de cadastro.
Rodar: python -m unittest -v tests.test_pedido"""
from __future__ import annotations

import unittest

from revgas_atendimento.atendimento import ServicoDeAtendimento
from revgas_atendimento.atendimento_integrado import ServicoDeAtendimentoIntegrado
from revgas_atendimento.atendimento_pedido import ServicoDePedido
from revgas_atendimento.modelos import Cadastro, DadoInvalidoError, Entrada
from revgas_atendimento.modelos_pedido import TipoBotijao
from revgas_atendimento.simulacoes import CadastrosEmMemoria, CepsEmMemoria, SessoesEmMemoria
from revgas_atendimento.simulacoes_pedido import PedidosEmMemoria
from revgas_atendimento.validacao_pedido import validar_quantidade, validar_tipo_botijao
from tests.apoio import (
    ENDERECO,
    FALAS_ENDERECO,
    PAGAMENTO,
    FALAS_OUTRO_ENDERECO,
    OUTRO_ENDERECO,
    TELEFONE,
    TELEFONE_CONTATO,
    TELEFONE_CONTATO_FORMATADO,
    TTL,
)


class TesteValidacaoDoPedido(unittest.TestCase):
    def test_tipo_de_botijao_aceita_codigo_peso_e_apelido(self):
        self.assertEqual(validar_tipo_botijao("p13"), TipoBotijao.P13)
        self.assertEqual(validar_tipo_botijao("20kg"), TipoBotijao.P20)
        self.assertEqual(validar_tipo_botijao("quero o grande mesmo"), TipoBotijao.P45)

    def test_tipo_de_botijao_dentro_de_uma_frase_inteira(self):
        self.assertEqual(validar_tipo_botijao("Oi, queria um botijão P13 por favor"), TipoBotijao.P13)
        self.assertEqual(validar_tipo_botijao("pode ser o residencial"), TipoBotijao.P13)

    def test_tipo_de_botijao_desconhecido_e_rejeitado(self):
        with self.assertRaises(DadoInvalidoError):
            validar_tipo_botijao("um botijão voador")

    def test_quantidade_em_numero_e_por_extenso(self):
        self.assertEqual(validar_quantidade("2"), 2)
        self.assertEqual(validar_quantidade("duas, por favor"), 2)
        self.assertEqual(validar_quantidade("quero um"), 1)

    def test_quantidade_fora_do_limite_e_rejeitada(self):
        with self.assertRaises(DadoInvalidoError):
            validar_quantidade("0")
        with self.assertRaises(DadoInvalidoError):
            validar_quantidade("99")

    def test_quantidade_nao_numerica_e_rejeitada(self):
        with self.assertRaises(DadoInvalidoError):
            validar_quantidade("muitas")


class ConversaDePedido:
    def __init__(self, cadastros: CadastrosEmMemoria | None = None) -> None:
        self.pedidos = PedidosEmMemoria()
        self.servico = ServicoDePedido(self.pedidos, SessoesEmMemoria(TTL), cadastros, CepsEmMemoria())

    async def texto(self, *textos: str):
        resposta = None
        for texto in textos:
            resposta = await self.servico.atender(TELEFONE, Entrada(texto=texto))
        return resposta

    async def ate_a_confirmacao(self, tipo: str = "p13", quantidade: str = "1"):
        return await self.texto("gás", tipo, quantidade, *FALAS_ENDERECO, PAGAMENTO)


class TesteFluxoDePedido(unittest.IsolatedAsyncioTestCase):
    async def test_mensagem_sem_relacao_com_pedido_nao_e_tratada(self):
        self.assertIsNone(await ConversaDePedido().texto("oi"))

    async def test_resposta_nunca_tem_botoes(self):
        conversa = ConversaDePedido()
        primeira = await conversa.texto("gás")
        self.assertEqual(primeira.botoes, ())
        resumo = await conversa.texto("p13", "2", *FALAS_ENDERECO, PAGAMENTO)
        self.assertEqual(resumo.botoes, ())

    async def test_fluxo_completo_em_linguagem_natural_registra_o_pedido(self):
        conversa = ConversaDePedido()
        primeira = await conversa.texto("quero pedir gás")
        self.assertIn("botijão", primeira.texto.lower())

        await conversa.texto("um botijão P13, o pequeno mesmo")
        pergunta_cep = await conversa.texto("duas, por favor")
        self.assertIn("CEP", pergunta_cep.texto)
        resumo = await conversa.texto(*FALAS_ENDERECO, PAGAMENTO)
        self.assertIn("certo?", resumo.texto.lower())

        await conversa.texto("sim, pode confirmar")

        pedidos = await conversa.pedidos.listar_por_telefone(TELEFONE)
        self.assertEqual(len(pedidos), 1)
        self.assertEqual((pedidos[0].tipo_botijao, pedidos[0].quantidade), (TipoBotijao.P13, 2))
        self.assertEqual(pedidos[0].endereco_entrega, ENDERECO)

    async def test_tipo_invalido_nao_avanca(self):
        conversa = ConversaDePedido()
        await conversa.texto("pedido")
        resposta = await conversa.texto("botijão voador")
        self.assertIn("botijão", resposta.texto.lower())

    async def test_quantidade_invalida_nao_avanca(self):
        conversa = ConversaDePedido()
        resposta = await conversa.texto("gas", "p13", "muitíssimas")
        self.assertIn("quantidade", resposta.texto.lower())

    async def test_corrigir_recomeca_do_tipo(self):
        conversa = ConversaDePedido()
        await conversa.ate_a_confirmacao(tipo="p20")
        resposta = await conversa.texto("refazer")
        self.assertIn("botijão", resposta.texto.lower())

    async def test_sem_cadastro_mandar_cep_novo_na_confirmacao(self):
        conversa = ConversaDePedido()
        await conversa.ate_a_confirmacao()
        await conversa.texto(*FALAS_OUTRO_ENDERECO, "sim")
        pedidos = await conversa.pedidos.listar_por_telefone(TELEFONE)
        self.assertEqual(pedidos[0].endereco_entrega, OUTRO_ENDERECO)

    async def test_nao_sei_o_cep_aceita_endereco_digitado_com_numero(self):
        conversa = ConversaDePedido()
        await conversa.texto("gás", "p13", "1")
        resposta = await conversa.texto("não sei")
        self.assertIn("endereço completo", resposta.texto)
        sem_numero = await conversa.texto("Rua das Flores, Centro")
        self.assertIn("Faltou o número", sem_numero.texto)
        await conversa.texto("Rua das Flores, 120 - Centro", PAGAMENTO, "sim")
        pedidos = await conversa.pedidos.listar_por_telefone(TELEFONE)
        self.assertEqual(pedidos[0].endereco_entrega, "Rua das Flores, 120 - Centro")

    async def test_cep_inexistente_pede_de_novo(self):
        conversa = ConversaDePedido()
        resposta = await conversa.texto("gás", "p13", "1", "12345-678")
        self.assertIn("Não encontrei o CEP 12345-678", resposta.texto)

    async def test_cancelar_descarta_o_pedido(self):
        conversa = ConversaDePedido()
        await conversa.texto("quero gas")
        resposta = await conversa.texto("cancelar")
        self.assertIn("cancelei", resposta.texto.lower())
        self.assertEqual(await conversa.pedidos.listar_por_telefone(TELEFONE), [])

    async def test_confirmar_de_varios_jeitos_funciona(self):
        for resposta_de_confirmacao in ("sim", "confirmo", "isso mesmo", "ok", "pode mandar"):
            with self.subTest(resposta=resposta_de_confirmacao):
                conversa = ConversaDePedido()
                await conversa.ate_a_confirmacao()
                await conversa.texto(resposta_de_confirmacao)
                self.assertEqual(len(await conversa.pedidos.listar_por_telefone(TELEFONE)), 1)


class TesteClienteCadastradoSoConfirma(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        cadastros = CadastrosEmMemoria()
        await cadastros.salvar(Cadastro(TELEFONE, "Maria da Silva", TELEFONE_CONTATO, ENDERECO))
        self.conversa = ConversaDePedido(cadastros)

    async def test_nao_pergunta_endereco_e_mostra_nome_numero_e_endereco(self):
        resumo = await self.conversa.texto("gás", "p13", "2", PAGAMENTO)
        for dado in ("Maria da Silva", TELEFONE_CONTATO_FORMATADO, ENDERECO):
            self.assertIn(dado, resumo.texto)

        await self.conversa.texto("sim")
        pedidos = await self.conversa.pedidos.listar_por_telefone(TELEFONE)
        self.assertEqual(pedidos[0].endereco_entrega, ENDERECO)

    async def test_pode_mandar_cep_novo_na_confirmacao(self):
        await self.conversa.texto("gás", "p13", "1", PAGAMENTO)
        achado = await self.conversa.texto(FALAS_OUTRO_ENDERECO[0])
        self.assertIn("Avenida Paulista", achado.texto)
        await self.conversa.texto(FALAS_OUTRO_ENDERECO[1], "isso mesmo")
        pedidos = await self.conversa.pedidos.listar_por_telefone(TELEFONE)
        self.assertEqual(pedidos[0].endereco_entrega, OUTRO_ENDERECO)

    async def test_responder_nao_pede_o_cep_novo(self):
        await self.conversa.texto("gás", "p13", "1", PAGAMENTO)
        resposta = await self.conversa.texto("não")
        self.assertIn("CEP do endereço certo", resposta.texto)
        self.assertTrue(await self.conversa.servico.tem_sessao_ativa(TELEFONE))


class TesteIntegracaoComOCadastro(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.cadastros = CadastrosEmMemoria()
        self.sessoes_cadastro = SessoesEmMemoria(TTL)
        ceps = CepsEmMemoria()
        self.atendimento_cadastro = ServicoDeAtendimento(self.cadastros, self.sessoes_cadastro, ceps)
        self.pedidos = PedidosEmMemoria()
        self.servico_pedido = ServicoDePedido(self.pedidos, SessoesEmMemoria(TTL), self.cadastros, ceps)
        self.integrado = ServicoDeAtendimentoIntegrado(
            self.atendimento_cadastro, self.sessoes_cadastro, self.servico_pedido
        )

    async def texto(self, *textos: str):
        resposta = None
        for texto in textos:
            resposta = await self.integrado.atender(TELEFONE, Entrada(texto=texto))
        return resposta

    async def test_primeira_mensagem_comeca_o_cadastro_como_sempre(self):
        self.assertIn("nome completo", (await self.texto("oi")).texto)

    async def test_pedir_gas_direto_comeca_o_pedido(self):
        self.assertIn("botijão", (await self.texto("quero pedir gás")).texto.lower())

    async def test_gatilho_de_pedido_nao_interrompe_um_cadastro_em_andamento(self):
        await self.texto("oi", "gás")
        self.assertFalse(await self.servico_pedido.tem_sessao_ativa(TELEFONE))

    async def test_pedido_completo_nao_interfere_no_cadastro_do_mesmo_telefone(self):
        await self.texto("gás", "p13", "1", *FALAS_ENDERECO, PAGAMENTO, "sim")
        self.assertEqual(len(await self.pedidos.listar_por_telefone(TELEFONE)), 1)
        self.assertIsNone(await self.cadastros.buscar_por_telefone(TELEFONE))  # cadastro não foi tocado

    async def test_depois_do_pedido_o_cadastro_continua_funcionando_normalmente(self):
        await self.texto("gás", "p13", "1", *FALAS_ENDERECO, PAGAMENTO, "sim")
        self.assertIn("nome completo", (await self.texto("oi")).texto)


if __name__ == "__main__":
    unittest.main()
