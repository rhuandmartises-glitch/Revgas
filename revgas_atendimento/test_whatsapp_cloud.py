"""Testes do adaptador real do WhatsApp contra um servidor HTTP falso local. Rodar: python -m unittest -v test_whatsapp_cloud"""
from __future__ import annotations

import json
import socket
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from revgas_atendimento.modelos import IntegracaoError
from revgas_atendimento.whatsapp_cloud import WhatsAppCloudApi

TOKEN = "EAAB-token-super-secreto"
MENSAGEM = {"messaging_product": "whatsapp", "type": "text", "text": {"body": "olá"}}


class ServidorFalso:
    """Imita a Graph API: registra o que recebeu e responde com o status configurado."""

    def __init__(self, status: int = 200, corpo: bytes = b'{"messages":[{"id":"wamid.X"}]}', atraso_s: float = 0.0):
        self.requisicoes: list[dict] = []
        dono = self

        class Manipulador(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                tamanho = int(self.headers.get("Content-Length", 0))
                dono.requisicoes.append({
                    "caminho": self.path,
                    "autorizacao": self.headers.get("Authorization"),
                    "corpo": json.loads(self.rfile.read(tamanho)),
                })
                time.sleep(atraso_s)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            def log_message(self, *args) -> None:
                pass

        class Servidor(ThreadingHTTPServer):
            def handle_error(self, *args) -> None:  # silencia conexões cortadas pelo timeout do teste
                pass

        self._httpd = Servidor(("127.0.0.1", 0), Manipulador)
        self.url_base = f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def __enter__(self) -> ServidorFalso:
        threading.Thread(target=self._httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
        return self

    def __exit__(self, *args) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


def cliente(url_base: str, timeout_s: float = 5.0) -> WhatsAppCloudApi:
    return WhatsAppCloudApi(TOKEN, "123456", "v26.0", url_base=url_base, timeout_s=timeout_s)


class TesteEnvioPelaApiDaMeta(unittest.IsolatedAsyncioTestCase):
    async def test_envia_para_a_url_correta_com_token_e_destinatario(self):
        with ServidorFalso() as servidor:
            await cliente(servidor.url_base).enviar("5511999990000", MENSAGEM)

        requisicao = servidor.requisicoes[0]
        self.assertEqual(requisicao["caminho"], "/v26.0/123456/messages")
        self.assertEqual(requisicao["autorizacao"], f"Bearer {TOKEN}")
        self.assertEqual(requisicao["corpo"]["to"], "5511999990000")
        self.assertEqual(requisicao["corpo"]["text"]["body"], "olá")

    async def test_erro_da_meta_vira_integracao_error_sem_vazar_o_token(self):
        erro_meta = json.dumps({"error": {"message": "(#131030) Recipient phone number not in allowed list", "code": 131030}})
        with ServidorFalso(status=400, corpo=erro_meta.encode()) as servidor:
            with self.assertRaises(IntegracaoError) as contexto:
                await cliente(servidor.url_base).enviar("5511999990000", MENSAGEM)

        texto = str(contexto.exception)
        self.assertIn("HTTP 400", texto)
        self.assertIn("131030", texto)
        self.assertNotIn(TOKEN, texto)

    async def test_token_expirado_traz_orientacao(self):
        erro_meta = json.dumps({"error": {"message": "Error validating access token: Session has expired", "code": 190}})
        with ServidorFalso(status=401, corpo=erro_meta.encode()) as servidor:
            with self.assertRaises(IntegracaoError) as contexto:
                await cliente(servidor.url_base).enviar("5511999990000", MENSAGEM)
        self.assertIn("gere outro no painel da Meta", str(contexto.exception))

    async def test_resposta_de_erro_que_nao_e_json_nao_quebra(self):
        with ServidorFalso(status=500, corpo=b"<html>erro</html>") as servidor:
            with self.assertRaises(IntegracaoError) as contexto:
                await cliente(servidor.url_base).enviar("5511999990000", MENSAGEM)
        self.assertIn("HTTP 500", str(contexto.exception))

    async def test_conexao_recusada_vira_integracao_error(self):
        with socket.socket() as soquete:
            soquete.bind(("127.0.0.1", 0))
            porta_livre = soquete.getsockname()[1]
        with self.assertRaises(IntegracaoError):
            await cliente(f"http://127.0.0.1:{porta_livre}").enviar("5511999990000", MENSAGEM)

    async def test_timeout_vira_integracao_error(self):
        with ServidorFalso(atraso_s=0.6) as servidor:
            with self.assertRaises(IntegracaoError):
                await cliente(servidor.url_base, timeout_s=0.2).enviar("5511999990000", MENSAGEM)


if __name__ == "__main__":
    unittest.main()
