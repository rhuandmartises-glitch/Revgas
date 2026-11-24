"""Ponte entre o webhook e o atendimento. Independente de framework web: fácil de testar."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from .atendimento import MENSAGEM_FALHA_TECNICA
from .deduplicador import Deduplicador
from .modelos import Resposta
from .portas import Atendente, WhatsAppGateway
from .whatsapp import extrair_mensagem, montar_mensagem

logger = logging.getLogger(__name__)


class ProcessadorWhatsApp:
    """PRODUÇÃO: com Redis nas sessões, serialize as mensagens do mesmo telefone (lock por telefone)."""

    def __init__(self, atendimento: Atendente, whatsapp: WhatsAppGateway) -> None:
        self._atendimento = atendimento
        self._whatsapp = whatsapp
        self._deduplicador = Deduplicador()

    async def processar(self, corpo_webhook: Mapping[str, Any]) -> None:
        mensagem = extrair_mensagem(corpo_webhook)
        if mensagem is None or self._deduplicador.ja_visto(mensagem.id):
            return
        try:
            resposta = await self._atendimento.atender(mensagem.telefone, mensagem.entrada)
        except Exception:  # fronteira do fluxo: o cliente nunca fica sem resposta
            # Só o id da mensagem vai para o log: nome, telefone e endereço nunca são registrados.
            logger.exception("Falha ao atender a mensagem %s", mensagem.id)
            resposta = Resposta(MENSAGEM_FALHA_TECNICA)
        await self._whatsapp.enviar(mensagem.telefone, montar_mensagem(mensagem.telefone, resposta))
