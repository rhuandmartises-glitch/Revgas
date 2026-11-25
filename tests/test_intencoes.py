"""O bot entende sinônimos do dia a dia e não obriga o cliente a digitar uma palavra exata.
Rodar: python -m unittest -v tests.test_intencoes"""
from __future__ import annotations

import re
import unittest

from revgas_atendimento import atendimento, atendimento_pedido, endereco, validacao_pedido
from revgas_atendimento.atendimento import ServicoDeAtendimento
from revgas_atendimento.atendimento_integrado import ServicoDeAtendimentoIntegrado
from revgas_atendimento.atendimento_pedido import ServicoDePedido, eh_pedido_de_gas
from revgas_atendimento.endereco import validar_numero
from revgas_atendimento.intencoes import (
    concorda,
    discorda,
    dispensa_troco,
    nao_sabe,
    quer_atualizar_cadastro,
    quer_cancelar,
    quer_refazer,
)
from revgas_atendimento.interpretacao import Intencao, interpretar_confirmacao
from revgas_atendimento.modelos import Cadastro, Entrada, Etapa
from revgas_atendimento.simulacoes import CadastrosEmMemoria, CepsEmMemoria, SessoesEmMemoria
from revgas_atendimento.simulacoes_pedido import PedidosEmMemoria
from revgas_atendimento.validacao_pedido import validar_troco
from tests.apoio import ENDERECO, FALAS_ENDERECO, TELEFONE, TELEFONE_CONTATO, TTL


class TesteSinonimos(unittest.TestCase):
    def verificar(self, funcao, sim: list[str], nao: list[str]) -> None:
        for texto in sim:
            with self.subTest(funcao=funcao.__name__, texto=texto, esperado=True):
                self.assertTrue(funcao(texto))
        for texto in nao:
            with self.subTest(funcao=funcao.__name__, texto=texto, esperado=False):
                self.assertFalse(funcao(texto))

    def test_cancelar(self):
        self.verificar(
            quer_cancelar,
            ["cancela", "Cancelar!", "quero cancelar o pedido", "desisto", "desisti", "deixa pra lá",
             "esquece", "não quero mais", "Não quero", "mudei de ideia", "para", "chega", "sair", "pode cancelar"],
            ["troco para 100", "não quero troco", "Rua Para, 10", "pix", "sim", "não"],
        )

    def test_cancelar_na_etapa_do_nome_so_com_a_frase_inteira(self):
        self.assertFalse(quer_cancelar("Maria Cancela", so_frase_exata=True))
        self.assertTrue(quer_cancelar("cancelar", so_frase_exata=True))
        self.assertTrue(quer_cancelar("desisto", so_frase_exata=True))

    def test_nao_sei(self):
        self.verificar(
            nao_sabe,
            ["não sei", "Não sei o CEP", "sei lá", "não lembro", "esqueci", "não tenho", "nem sei",
             "não faço ideia", "ns", "sei não"],
            ["01001-000", "sei", "sim", "Rua A, 10"],
        )

    def test_sim(self):
        self.verificar(
            concorda,
            ["sim", "Sim!", "s", "isso", "isso mesmo", "pode mandar", "tá certo", "ta bom", "fechado",
             "beleza", "blz", "ok", "pode ser", "com certeza", "perfeito", "bora", "👍", "✅", "uhum"],
            ["não", "talvez", "Rua A, 10"],
        )

    def test_nao(self):
        self.verificar(discorda, ["não", "nao", "n", "tá errado", "mudou", "quero trocar", "negativo"], ["sim", "ok"])

    def test_refazer(self):
        self.verificar(quer_refazer, ["refazer", "corrigir", "começar de novo", "do zero", "quero recomeçar"], ["sim"])

    def test_atualizar_cadastro(self):
        self.verificar(
            quer_atualizar_cadastro,
            ["atualizar", "quero mudar meu endereço", "trocar meus dados", "corrigir meu nome", "editar"],
            ["oi", "bom dia"],
        )

    def test_sem_troco(self):
        self.verificar(
            dispensa_troco,
            ["não", "Não precisa", "sem troco", "vou dar certinho", "tenho trocado", "nada", "não vou precisar"],
            ["100", "sim"],
        )
        self.assertIsNone(validar_troco("não precisa não"))

    def test_casa_sem_numero(self):
        for texto in ("s/n", "sem número", "não tem número", "Não tem", "não possui"):
            with self.subTest(texto=texto):
                self.assertEqual(validar_numero(texto)[0], "s/n")

    def test_confirmacao_com_jeitos_diferentes(self):
        self.assertIs(interpretar_confirmacao("fechado, pode mandar"), Intencao.CONFIRMAR)
        self.assertIs(interpretar_confirmacao("👍"), Intencao.CONFIRMAR)
        self.assertIs(interpretar_confirmacao("tá errado"), Intencao.NEGAR)
        self.assertIs(interpretar_confirmacao("quero começar de novo"), Intencao.REFAZER)

    def test_gatilho_de_pedido(self):
        for texto in ("gás", "quero um botijão", "preciso de um bujão", "quero pedir", "novo pedido"):
            with self.subTest(texto=texto):
                self.assertTrue(eh_pedido_de_gas(Entrada(texto=texto)))
        self.assertFalse(eh_pedido_de_gas(Entrada(texto="gasolina")))


class TesteMensagensNaoObrigamPalavraExata(unittest.TestCase):
    """Nenhuma mensagem manda o cliente "responder SIM", "digitar REFAZER", "enviar CANCELAR"..."""

    ORDENS = re.compile(r"\b(responda|digite|envie|mande)\s+[A-ZÁÉÍÓÚÃÕÇ/]{2,}")

    def test_textos_fixos(self):
        textos = [
            valor
            for modulo in (atendimento, atendimento_pedido, endereco, validacao_pedido)
            for nome, valor in vars(modulo).items()
            if nome.isupper() and isinstance(valor, str)
        ]
        self.assertGreater(len(textos), 5)
        for texto in textos:
            with self.subTest(texto=texto[:50]):
                self.assertIsNone(self.ORDENS.search(texto), texto)
                for palavra in ("NÃO SEI", "REFAZER", "ATUALIZAR", "S/N", " SIM", "GÁS"):
                    self.assertNotIn(palavra, texto)


class TesteConversasComSinonimos(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.cadastros = CadastrosEmMemoria()
        sessoes = SessoesEmMemoria(TTL)
        ceps = CepsEmMemoria()
        self.pedidos = PedidosEmMemoria()
        self.sessoes_cadastro = sessoes
        self.bot = ServicoDeAtendimentoIntegrado(
            ServicoDeAtendimento(self.cadastros, sessoes, ceps),
            sessoes,
            ServicoDePedido(self.pedidos, SessoesEmMemoria(TTL), self.cadastros, ceps),
        )

    async def falar(self, *falas: str):
        resposta = None
        for fala in falas:
            resposta = await self.bot.atender(TELEFONE, Entrada(texto=fala))
        return resposta

    async def test_cadastro_inteiro_sem_nenhuma_palavra_exata(self):
        await self.falar("oi", "Maria da Silva", TELEFONE_CONTATO)
        self.assertIn("endereço completo", (await self.falar("sei lá o cep")).texto)
        await self.falar("Praça da Sé, 120 - Sé")
        self.assertIn("Pronto, Maria", (await self.falar("fechado, pode salvar")).texto)

    async def test_desistir_no_meio_do_cadastro(self):
        await self.falar("oi", "Maria da Silva")
        self.assertIn("não guardei nenhum dado", (await self.falar("desisto")).texto)
        self.assertIsNone(await self.sessoes_cadastro.obter(TELEFONE))

    async def test_sobrenome_cancela_nao_cancela_o_cadastro(self):
        await self.falar("oi")
        resposta = await self.falar("Maria Cancela")
        self.assertIn("telefone", resposta.texto)
        self.assertEqual((await self.sessoes_cadastro.obter(TELEFONE)).etapa, Etapa.TELEFONE)

    async def test_cliente_cadastrado_pede_para_mudar_o_endereco(self):
        await self.cadastros.salvar(Cadastro(TELEFONE, "Maria da Silva", TELEFONE_CONTATO, ENDERECO))
        self.assertIn("atualizar seus dados", (await self.falar("quero mudar meu endereço")).texto)

    async def test_pedido_com_bujao_dinheiro_sem_troco_e_mudei_de_ideia(self):
        self.assertIn("botijão", (await self.falar("me vê um bujão")).texto.lower())
        await self.falar("p13", "1", *FALAS_ENDERECO, "dinheiro")
        resumo = await self.falar("não precisa de troco")
        self.assertIn("(sem troco)", resumo.texto)
        self.assertIn("confirmado", (await self.falar("pode mandar 👍")).texto)
        self.assertIn("Pedido cancelado", (await self.falar("mudei de ideia")).texto)


if __name__ == "__main__":
    unittest.main()
