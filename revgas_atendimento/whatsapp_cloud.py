"""Adaptador real do WhatsApp Cloud API (Meta): envia as mensagens pela Graph API.

Usa só a biblioteca padrão (urllib) em uma thread, para não exigir dependências extras.
Para volume alto, troque por um cliente assíncrono (ex.: httpx) mantendo o mesmo contrato.
"""
from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any

from .modelos import IntegracaoError
from .segredo import Segredo

URL_BASE_PADRAO = "https://graph.facebook.com"
CODIGO_TOKEN_INVALIDO = 190


class WhatsAppCloudApi:
    def __init__(
        self,
        token_acesso: Segredo | str,
        id_numero: str,
        versao_api: str,
        url_base: str = URL_BASE_PADRAO,
        timeout_s: float = 10.0,
    ) -> None:
        self._url = f"{url_base}/{versao_api}/{id_numero}/messages"
        self._token_acesso = Segredo.de(token_acesso)  # Segredo: não aparece se este objeto for logado
        self._timeout_s = timeout_s

    async def enviar(self, telefone: str, mensagem: Mapping[str, Any]) -> None:
        await asyncio.to_thread(self._enviar_sincrono, {**mensagem, "to": telefone})

    def _enviar_sincrono(self, payload: Mapping[str, Any]) -> None:
        requisicao = urllib.request.Request(
            self._url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": "Bearer " + self._token_acesso.revelar(),
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(requisicao, timeout=self._timeout_s) as resposta:
                resposta.read()
        except urllib.error.HTTPError as erro:
            raise IntegracaoError(_descrever_erro_http(erro)) from erro
        except (urllib.error.URLError, TimeoutError) as erro:
            raise IntegracaoError(
                f"Falha de rede ao chamar a API do WhatsApp ({type(erro).__name__})."
            ) from erro


def _descrever_erro_http(erro: urllib.error.HTTPError) -> str:
    """Resume o erro da Meta sem jamais incluir o token de acesso."""
    try:
        detalhe = json.loads(erro.read().decode("utf-8")).get("error", {})
        mensagem = f"API do WhatsApp respondeu HTTP {erro.code}: {detalhe.get('message', 'sem detalhe')}"
        if detalhe.get("code") == CODIGO_TOKEN_INVALIDO:
            mensagem += " | Token de acesso inválido ou expirado: gere outro no painel da Meta."
        return mensagem
    except (ValueError, AttributeError):
        return f"API do WhatsApp respondeu HTTP {erro.code}."
