"""Testes do webhook, da leitura de payloads reais da Meta, da composição e do .env. Rodar: python -m unittest -v tests.test_webhook"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from revgas_atendimento.ambiente import carregar_arquivo_env
from revgas_atendimento.atendimento import ServicoDeAtendimento
from revgas_atendimento.composicao import montar_whatsapp
from revgas_atendimento.config import Configuracao, CredenciaisWhatsApp
from revgas_atendimento.modelos import ConfiguracaoInvalidaError
from revgas_atendimento.processador import ProcessadorWhatsApp
from revgas_atendimento.simulacoes import CadastrosEmMemoria, SessoesEmMemoria, WhatsAppEmMemoria
from revgas_atendimento.webhook import RequisicaoRecusadaError, ServicoDeWebhook
from revgas_atendimento.whatsapp import extrair_mensagem
from revgas_atendimento.whatsapp_cloud import WhatsAppCloudApi

# Formatos copiados da documentação da Meta (mensagem de texto, resposta de botão e status de entrega).
PAYLOAD_TEXTO = {"object": "whatsapp_business_account", "entry": [{"id": "0", "changes": [{"field": "messages", "value": {
    "messaging_product": "whatsapp", "metadata": {"display_phone_number": "16505551111", "phone_number_id": "123456123"},
    "contacts": [{"profile": {"name": "test user name"}, "wa_id": "16315551181"}],
    "messages": [{"from": "16315551181", "id": "ABGGFlA5Fpa", "timestamp": "1504902988", "type": "text",
                  "text": {"body": "this is a text message"}}]}}]}]}
PAYLOAD_BOTAO = {"object": "whatsapp_business_account", "entry": [{"id": "0", "changes": [{"field": "messages", "value": {
    "messaging_product": "whatsapp", "metadata": {"phone_number_id": "106540352242922"},
    "contacts": [{"profile": {"name": "Pablo Morales"}, "wa_id": "16505551234"}],
    "messages": [{"context": {"from": "15550783881", "id": "wamid.CTX"}, "from": "16505551234", "id": "wamid.XYZ",
                  "timestamp": "1714510003", "type": "interactive",
                  "interactive": {"type": "button_reply", "button_reply": {"id": "CONFIRMAR", "title": "Confirmar"}}}]}}]}]}
PAYLOAD_STATUS = {"entry": [{"changes": [{"field": "messages", "value": {
    "statuses": [{"id": "wamid.X", "status": "delivered", "timestamp": "1", "recipient_id": "16505551234"}]}}]}]}


class TesteLeituraDePayloadsDaMeta(unittest.TestCase):
    def test_mensagem_de_texto(self):
        mensagem = extrair_mensagem(PAYLOAD_TEXTO)
        self.assertEqual((mensagem.telefone, mensagem.entrada.texto), ("16315551181", "this is a text message"))

    def test_resposta_de_botao(self):
        mensagem = extrair_mensagem(PAYLOAD_BOTAO)
        self.assertEqual(mensagem.entrada.botao_id, "CONFIRMAR")

    def test_evento_de_status_e_ignorado(self):
        self.assertIsNone(extrair_mensagem(PAYLOAD_STATUS))

    def test_json_de_formato_inesperado_e_ignorado(self):
        self.assertIsNone(extrair_mensagem([1, 2, 3]))
        self.assertIsNone(extrair_mensagem({"entry": []}))


def assinar(corpo: bytes) -> str:
    return "sha256=" + hmac.new(b"segredo", corpo, hashlib.sha256).hexdigest()


class TesteServicoDeWebhook(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.whatsapp = WhatsAppEmMemoria(imprimir=False)
        atendimento = ServicoDeAtendimento(CadastrosEmMemoria(), SessoesEmMemoria(900.0))
        self.servico = ServicoDeWebhook(
            Configuracao("segredo", "token-verificacao"), ProcessadorWhatsApp(atendimento, self.whatsapp)
        )

    def test_verificacao_devolve_o_desafio(self):
        self.assertEqual(self.servico.verificar("subscribe", "token-verificacao", "12345"), "12345")

    def test_verificacao_com_token_ou_modo_errado_e_403(self):
        for modo, token in (("subscribe", "errado"), ("outro", "token-verificacao"), ("", "")):
            with self.assertRaises(RequisicaoRecusadaError) as contexto:
                self.servico.verificar(modo, token, "12345")
            self.assertEqual(contexto.exception.status_http, 403)

    async def test_assinatura_invalida_e_401_e_nada_e_processado(self):
        corpo = json.dumps(PAYLOAD_TEXTO).encode()
        with self.assertRaises(RequisicaoRecusadaError) as contexto:
            await self.servico.receber(corpo, "sha256=00")
        self.assertEqual(contexto.exception.status_http, 401)
        await self.servico.aguardar_pendentes()
        self.assertEqual(self.whatsapp.enviadas, [])

    async def test_json_invalido_com_assinatura_correta_e_400(self):
        corpo = b"isto nao e json"
        with self.assertRaises(RequisicaoRecusadaError) as contexto:
            await self.servico.receber(corpo, assinar(corpo))
        self.assertEqual(contexto.exception.status_http, 400)

    async def test_evento_valido_e_processado_e_respondido(self):
        corpo = json.dumps(PAYLOAD_TEXTO).encode()
        await self.servico.receber(corpo, assinar(corpo))
        await self.servico.aguardar_pendentes()

        telefone, mensagem = self.whatsapp.enviadas[0]
        self.assertEqual(telefone, "16315551181")
        self.assertIn("nome completo", mensagem["text"]["body"])

    async def test_evento_de_status_nao_gera_resposta(self):
        corpo = json.dumps(PAYLOAD_STATUS).encode()
        await self.servico.receber(corpo, assinar(corpo))
        await self.servico.aguardar_pendentes()
        self.assertEqual(self.whatsapp.enviadas, [])


class TesteComposicaoEConfiguracao(unittest.TestCase):
    def test_sem_credenciais_usa_modo_console_e_avisa(self):
        with self.assertLogs("revgas_atendimento.composicao", level="WARNING"):
            gateway = montar_whatsapp(Configuracao("a", "b"))
        self.assertIsInstance(gateway, WhatsAppEmMemoria)

    def test_com_credenciais_usa_a_api_real(self):
        configuracao = Configuracao("a", "b", credenciais_whatsapp=CredenciaisWhatsApp("tok", "123"))
        self.assertIsInstance(montar_whatsapp(configuracao), WhatsAppCloudApi)

    def test_ambiente_sem_credenciais_do_whatsapp_e_valido(self):
        with patch.dict(os.environ, {"WA_APP_SECRET": "s", "WA_VERIFY_TOKEN": "t"}, clear=True):
            self.assertIsNone(Configuracao.do_ambiente().credenciais_whatsapp)

    def test_ambiente_com_credenciais_completas(self):
        ambiente = {"WA_APP_SECRET": "s", "WA_VERIFY_TOKEN": "t", "WA_ACCESS_TOKEN": " tok \n", "WA_PHONE_NUMBER_ID": "123"}
        with patch.dict(os.environ, ambiente, clear=True):
            credenciais = Configuracao.do_ambiente().credenciais_whatsapp
        self.assertEqual((credenciais.token_acesso, credenciais.id_numero, credenciais.versao_api), ("tok", "123", "v26.0"))

    def test_credenciais_pela_metade_falham_cedo(self):
        with patch.dict(os.environ, {"WA_APP_SECRET": "s", "WA_VERIFY_TOKEN": "t", "WA_ACCESS_TOKEN": "tok"}, clear=True):
            with self.assertRaises(ConfiguracaoInvalidaError):
                Configuracao.do_ambiente()

    def test_segredo_ausente_falha_cedo(self):
        with patch.dict(os.environ, {"WA_VERIFY_TOKEN": "t"}, clear=True):
            with self.assertRaises(ConfiguracaoInvalidaError):
                Configuracao.do_ambiente()


class TesteArquivoEnv(unittest.TestCase):
    def escrever(self, conteudo: bytes) -> Path:
        pasta = Path(tempfile.mkdtemp())
        caminho = pasta / ".env"
        caminho.write_bytes(conteudo)
        return caminho

    def test_le_comentarios_aspas_e_bom_do_bloco_de_notas(self):
        caminho = self.escrever("\ufeff# comentário\nA=1\n\nB = \"dois\"\nC='tres'\n".encode("utf-8"))
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(carregar_arquivo_env(caminho))
            self.assertEqual((os.environ["A"], os.environ["B"], os.environ["C"]), ("1", "dois", "tres"))

    def test_nao_sobrescreve_variavel_ja_definida(self):
        caminho = self.escrever(b"A=do-arquivo\n")
        with patch.dict(os.environ, {"A": "do-ambiente"}, clear=True):
            carregar_arquivo_env(caminho)
            self.assertEqual(os.environ["A"], "do-ambiente")

    def test_arquivo_inexistente_retorna_falso(self):
        self.assertFalse(carregar_arquivo_env(Path(tempfile.mkdtemp()) / ".env"))

    def test_linha_invalida_aponta_a_linha_sem_vazar_o_conteudo(self):
        caminho = self.escrever(b"A=1\nsegredo-solto-sem-igual\n")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfiguracaoInvalidaError) as contexto:
                carregar_arquivo_env(caminho)
        self.assertIn("linha 2", str(contexto.exception))
        self.assertNotIn("segredo-solto", str(contexto.exception))

    def test_arquivo_utf16_do_powershell_da_erro_claro(self):
        caminho = self.escrever("A=1\n".encode("utf-16"))
        with self.assertRaises(ConfiguracaoInvalidaError) as contexto:
            carregar_arquivo_env(caminho)
        self.assertIn("UTF-8", str(contexto.exception))


if __name__ == "__main__":
    unittest.main()
