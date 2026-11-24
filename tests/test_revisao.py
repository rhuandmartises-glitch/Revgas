"""Testes das mudanças da revisão de segurança e configuração. Rodar: python -m unittest -v tests.test_revisao"""
from __future__ import annotations

import logging
import os
import unittest
from unittest.mock import patch

from revgas_atendimento.composicao import montar_atendimento_cadastro
from revgas_atendimento.config import Configuracao
from revgas_atendimento.modelos import ConfiguracaoInvalidaError
from revgas_atendimento.processador import ProcessadorWhatsApp
from revgas_atendimento.seguranca import FiltroDeSegredosNoLog, ocultar_segredos
from revgas_atendimento.simulacoes import WhatsAppEmMemoria
from revgas_atendimento.texto import comando, palavras
from revgas_atendimento.webhook import RequisicaoRecusadaError, ServicoDeWebhook


def ambiente(**variaveis):
    return patch.dict(os.environ, variaveis, clear=True)


class TesteConfiguracaoPorModo(unittest.TestCase):
    def test_so_n8n_sem_segredos_da_meta_e_valido(self):
        with ambiente(N8N_API_KEY="k"):
            configuracao = Configuracao.do_ambiente()
        self.assertFalse(configuracao.webhook_meta_ativo)
        self.assertEqual(configuracao.chave_api_automacao.revelar(), "k")

    def test_sem_nenhum_modo_falha_cedo(self):
        with ambiente():
            with self.assertRaises(ConfiguracaoInvalidaError):
                Configuracao.do_ambiente()

    def test_texto_de_exemplo_e_recusado_sem_mostrar_o_valor(self):
        with ambiente(WA_APP_SECRET="COLE_A_CHAVE_SECRETA_DO_APP_AQUI", WA_VERIFY_TOKEN="t"):
            with self.assertRaises(ConfiguracaoInvalidaError) as contexto:
                Configuracao.do_ambiente()
        self.assertIn("WA_APP_SECRET", str(contexto.exception))
        self.assertNotIn("COLE_A_CHAVE", str(contexto.exception))


class TesteWebhookDesativado(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        configuracao = Configuracao(chave_api_automacao="k")  # modo só n8n
        processador = ProcessadorWhatsApp(montar_atendimento_cadastro(configuracao), WhatsAppEmMemoria(imprimir=False))
        self.servico = ServicoDeWebhook(configuracao, processador)

    def test_verificacao_responde_503(self):
        with self.assertRaises(RequisicaoRecusadaError) as contexto:
            self.servico.verificar("subscribe", "", "1")
        self.assertEqual(contexto.exception.status_http, 503)

    async def test_post_responde_503(self):
        with self.assertRaises(RequisicaoRecusadaError) as contexto:
            await self.servico.receber(b"{}", "sha256=00")
        self.assertEqual(contexto.exception.status_http, 503)


class TesteSegredosNoLog(unittest.TestCase):
    def test_token_de_verificacao_some_da_url(self):
        url = "/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=SEGREDO123&hub.challenge=9"
        self.assertEqual(ocultar_segredos(url), "/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=***&hub.challenge=9")
        self.assertNotIn("SEGREDO", ocultar_segredos("hub_verify_token=SEGREDO&x=1"))

    def test_filtro_age_nos_argumentos_do_log_de_acesso(self):
        registro = logging.LogRecord(
            "uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
            ("1.2.3.4", "GET", "/webhook/whatsapp?hub.verify_token=SEGREDO", "1.1", 200), None,
        )
        FiltroDeSegredosNoLog().filter(registro)
        self.assertNotIn("SEGREDO", registro.getMessage())


class TesteTextoCompartilhado(unittest.TestCase):
    def test_palavras_e_comando(self):
        self.assertEqual(palavras("Quero GÁS, já!"), ["quero", "gas", "ja"])
        self.assertEqual(comando("  Deixa pra lá. "), "deixa pra la")
        self.assertEqual(palavras(None), [])


if __name__ == "__main__":
    unittest.main()
