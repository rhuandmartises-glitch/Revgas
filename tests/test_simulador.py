"""Simulador visual: só atende este computador e conversa com o mesmo atendimento do servidor.
Rodar: python -m unittest -v tests.test_simulador"""
from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from fastapi.routing import APIRoute

from revgas_atendimento.config import Configuracao
from revgas_atendimento.simulador import (
    ConsultaDeCliente,
    MensagemDoSimulador,
    criar_simulador,
    requisicao_local,
    telefone_do_whatsapp,
)
from tests.apoio import TELEFONE


def rota(app, caminho: str):
    return next(r for r in app.routes if isinstance(r, APIRoute) and r.path == caminho)


class TesteSoEsteComputador(unittest.TestCase):
    def test_aceita_o_navegador_local(self):
        for host in ("127.0.0.1:8001", "localhost:8001", "[::1]:8001"):
            with self.subTest(host=host):
                self.assertTrue(requisicao_local("127.0.0.1", {"host": host}))

    def test_recusa_outra_maquina_proxy_tunel_e_host_estranho(self):
        casos = [
            ("192.168.0.10", {"host": "127.0.0.1:8001"}),  # outra máquina da rede
            ("127.0.0.1", {"host": "127.0.0.1:8001", "x-forwarded-for": "1.2.3.4"}),  # proxy
            ("127.0.0.1", {"host": "127.0.0.1:8001", "cf-connecting-ip": "1.2.3.4"}),  # túnel cloudflared
            ("127.0.0.1", {"host": "ataque.example:8001"}),  # DNS rebinding
            (None, {"host": "127.0.0.1:8001"}),
        ]
        for ip, cabecalhos in casos:
            with self.subTest(ip=ip, cabecalhos=cabecalhos):
                self.assertFalse(requisicao_local(ip, cabecalhos))

    def test_numero_do_cliente(self):
        self.assertEqual(telefone_do_whatsapp("11 99999-0001"), "5511999990001")
        self.assertEqual(telefone_do_whatsapp("+55 (11) 99999-0001"), "5511999990001")
        self.assertIsNone(telefone_do_whatsapp("123"))


class TesteRotasDoSimulador(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.app = criar_simulador(Configuracao())  # memória, sem consulta online

    async def falar(self, texto: str, telefone: str = TELEFONE) -> str:
        resposta = await rota(self.app, "/api/mensagem").endpoint(MensagemDoSimulador(telefone=telefone, texto=texto))
        return json.loads(resposta.body)["resposta"]

    async def test_conversa_completa_aparece_no_painel(self):
        self.assertIn("botijão", (await self.falar("quero gás")).lower())
        for fala in ("p13", "1", "01001-000", "Praça da Sé, 120 - Sé", "pix"):
            await self.falar(fala)
        self.assertIn("confirmado", await self.falar("sim"))

        resposta = await rota(self.app, "/api/cliente").endpoint(ConsultaDeCliente(telefone=TELEFONE))
        dados = json.loads(resposta.body)
        self.assertIsNone(dados["cadastro"])
        self.assertEqual(len(dados["pedidos"]), 1)
        self.assertEqual(dados["pedidos"][0]["status"], "CONFIRMADO")
        self.assertEqual(dados["pedidos"][0]["pagamento"], "Pix, na entrega")

    async def test_numero_invalido_e_recusado(self):
        resposta = await rota(self.app, "/api/mensagem").endpoint(MensagemDoSimulador(telefone="12345678", texto="oi"))
        self.assertEqual(resposta.status_code, 422)

    async def test_info_nao_tem_segredo_nenhum(self):
        app = criar_simulador(Configuracao(chave_api_automacao="chave-secreta-do-n8n"))
        info = await rota(app, "/api/info").endpoint()
        self.assertNotIn("chave-secreta-do-n8n", json.dumps(info))
        self.assertEqual(set(info), {"prazo_cancelamento_min", "cep_online", "banco"})

    async def test_pagina_e_arquivos_sem_dependencia_externa(self):
        for caminho in ("/", "/chat.css", "/chat.js"):
            with self.subTest(caminho=caminho):
                corpo = (await rota(self.app, caminho).endpoint()).body.decode("utf-8")
                self.assertNotIn("http://", corpo.replace("http://www.w3.org", ""))
                self.assertNotIn("https://", corpo)
        html = (await rota(self.app, "/").endpoint()).body.decode("utf-8")
        self.assertNotIn("<script>", html)  # nada de script em linha: a CSP pode ser estrita
        self.assertNotIn(" style=", html)

    def test_sem_documentacao_publica(self):
        self.assertIsNone(self.app.openapi_url)

    def test_sobe_sem_webhook_nem_n8n_configurados(self):
        with patch.dict(os.environ, {"REVGAS_CEP_ONLINE": "0", "REVGAS_BANCO": ""}, clear=True):
            configuracao = Configuracao.do_ambiente(exigir_canal=False)
        self.assertFalse(configuracao.webhook_meta_ativo)
        self.assertIsNone(configuracao.chave_api_automacao)


if __name__ == "__main__":
    unittest.main()
