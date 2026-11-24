"""Testes da rota para automação (n8n). Rodar: python -m unittest -v tests.test_automacao"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from revgas_atendimento.atendimento import MENSAGEM_FALHA_TECNICA
from revgas_atendimento.automacao import ServicoDeAutomacao
from revgas_atendimento.composicao_pedido import montar_atendimento_com_pedido_de_gas
from revgas_atendimento.config import Configuracao
from revgas_atendimento.webhook import RequisicaoRecusadaError

CHAVE = "chave-do-n8n"
TELEFONE = "5511999990000"


class TesteServicoDeAutomacao(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        configuracao = Configuracao("s", "t")
        self.servico = ServicoDeAutomacao(montar_atendimento_com_pedido_de_gas(configuracao), CHAVE)

    async def responder(self, texto, id_mensagem=None, telefone=TELEFONE, chave=CHAVE):
        return await self.servico.responder(chave, telefone, texto, id_mensagem)

    async def test_conversa_de_pedido_completa(self):
        self.assertIn("botijão", (await self.responder("Quero gás!")).lower())
        await self.responder("p13")
        await self.responder("2")
        # Montagem sem consulta online (padrão dos testes): confere o CEP e pede o endereço digitado.
        self.assertIn("Anotei o CEP 01001-000", await self.responder("01001-000"))
        self.assertIn("Como prefere pagar", await self.responder("Praça da Sé, 120 - Sé"))
        resumo = await self.responder("pix")
        self.assertIn("2x P13", resumo)
        self.assertIn("confirmado", await self.responder("sim"))

    async def test_telefone_com_mais_e_espacos_e_a_mesma_conversa(self):
        await self.responder("gás", telefone="+55 11 99999-0000")
        resposta = await self.responder("p13", telefone=TELEFONE)
        self.assertIn("quantos", resposta.lower())

    async def test_mensagem_repetida_responde_uma_vez_so(self):
        self.assertIsNotNone(await self.responder("oi", id_mensagem="wamid.1"))
        self.assertIsNone(await self.responder("oi", id_mensagem="wamid.1"))

    async def test_sem_texto_repete_a_pergunta(self):
        await self.responder("oi")
        self.assertIn("nome completo", await self.responder(None))

    async def test_chave_errada_e_401(self):
        with self.assertRaises(RequisicaoRecusadaError) as contexto:
            await self.responder("oi", chave="errada")
        self.assertEqual(contexto.exception.status_http, 401)

    async def test_sem_chave_configurada_a_rota_fica_desativada(self):
        servico = ServicoDeAutomacao(montar_atendimento_com_pedido_de_gas(Configuracao("s", "t")), None)
        with self.assertRaises(RequisicaoRecusadaError) as contexto:
            await servico.responder("", TELEFONE, "oi")
        self.assertEqual(contexto.exception.status_http, 503)

    async def test_telefone_invalido_e_422(self):
        with self.assertRaises(RequisicaoRecusadaError) as contexto:
            await self.responder("oi", telefone="abc")
        self.assertEqual(contexto.exception.status_http, 422)

    async def test_erro_inesperado_vira_mensagem_amigavel(self):
        class Quebrado:
            async def atender(self, telefone, entrada):
                raise RuntimeError("falha")

        servico = ServicoDeAutomacao(Quebrado(), CHAVE)
        with self.assertLogs("revgas_atendimento.automacao", level="ERROR"):
            self.assertEqual(await servico.responder(CHAVE, TELEFONE, "oi"), MENSAGEM_FALHA_TECNICA)


class TesteConfiguracaoDaChave(unittest.TestCase):
    def test_chave_lida_do_ambiente_e_fora_do_repr(self):
        with patch.dict(os.environ, {"WA_APP_SECRET": "s", "WA_VERIFY_TOKEN": "t", "N8N_API_KEY": " k-secreta \n"}, clear=True):
            configuracao = Configuracao.do_ambiente()
        self.assertEqual(configuracao.chave_api_automacao.revelar(), "k-secreta")
        self.assertNotIn("k-secreta", repr(configuracao))

    def test_sem_chave_no_ambiente_fica_none(self):
        with patch.dict(os.environ, {"WA_APP_SECRET": "s", "WA_VERIFY_TOKEN": "t"}, clear=True):
            self.assertIsNone(Configuracao.do_ambiente().chave_api_automacao)


if __name__ == "__main__":
    unittest.main()
