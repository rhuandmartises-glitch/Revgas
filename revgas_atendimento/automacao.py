"""Atendimento para ferramentas de automação (n8n, Make, Zapier...), sem framework web.

Diferente do webhook da Meta, aqui quem recebe e envia as mensagens do WhatsApp é a ferramenta.
Ela manda o telefone e o texto do cliente, e recebe de volta o texto da resposta para enviar.
Nada é enviado ao WhatsApp por este módulo.
"""
from __future__ import annotations

import logging

from .atendimento import MENSAGEM_FALHA_TECNICA
from .deduplicador import Deduplicador
from .erros_http import RequisicaoRecusadaError
from .modelos import Entrada
from .portas import Atendente
from .seguranca import tokens_iguais

logger = logging.getLogger(__name__)

_MINIMO_DIGITOS_TELEFONE = 8
_MAXIMO_DIGITOS_TELEFONE = 15  # limite internacional (E.164)


class ServicoDeAutomacao:
    def __init__(self, atendimento: Atendente, chave_api: str | None) -> None:
        self._atendimento = atendimento
        self._chave_api = chave_api
        self._deduplicador = Deduplicador()

    async def responder(
        self, chave_recebida: str, telefone: str, texto: str | None, id_mensagem: str | None = None
    ) -> str | None:
        """Devolve o texto da resposta, ou None se a mensagem já foi respondida (mesmo `id_mensagem`).

        Levanta RequisicaoRecusadaError: 503 se a rota não foi configurada, 401 se a chave não
        confere, 422 se o telefone é inválido.
        """
        if not self._chave_api:
            raise RequisicaoRecusadaError(503, "Rota desativada: defina N8N_API_KEY no servidor.")
        if not tokens_iguais(self._chave_api, chave_recebida):
            raise RequisicaoRecusadaError(401, "Chave de API inválida.")

        digitos = "".join(caractere for caractere in telefone if caractere.isdigit())
        if not (_MINIMO_DIGITOS_TELEFONE <= len(digitos) <= _MAXIMO_DIGITOS_TELEFONE):
            raise RequisicaoRecusadaError(422, "Telefone inválido: envie só os dígitos, com DDI e DDD.")

        # A Meta reenvia webhooks, e o n8n repassa cada reenvio: sem isso a conversa andaria duas vezes.
        if id_mensagem and self._deduplicador.ja_visto(id_mensagem):
            return None

        try:
            resposta = await self._atendimento.atender(digitos, Entrada(texto=texto or None))
        except Exception:  # fronteira do fluxo: o cliente nunca fica sem resposta
            logger.exception("Falha ao atender a mensagem de automação %s", id_mensagem or "(sem id)")
            return MENSAGEM_FALHA_TECNICA
        return resposta.texto
