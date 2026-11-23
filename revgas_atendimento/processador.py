"""Ponte entre o webhook e o atendimento. Independente de framework web: fácil de testar."""
from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any

from .atendimento import MENSAGEM_FALHA_TECNICA, ServicoDeAtendimento
from .modelos import Resposta
from .portas import WhatsAppGateway
from .whatsapp import extrair_mensagem, montar_mensagem

logger = logging.getLogger(__name__)


class _Deduplicador:
    """A Meta reenvia webhooks; descartamos ids repetidos. PRODUÇÃO: Redis SET NX com TTL."""

    def __init__(self, capacidade: int = 10_000) -> None:
        self._capacidade = capacidade
        self._vistos: OrderedDict[str, None] = OrderedDict()

    def ja_visto(self, chave: str) -> bool:
        if chave in self._vistos:
            return True
        self._vistos[chave] = None
        if len(self._vistos) > self._capacidade:
            self._vistos.popitem(last=False)
        return False


class ProcessadorWhatsApp:
    """PRODUÇÃO: com Redis nas sessões, serialize as mensagens do mesmo telefone (lock por telefone)."""

    def __init__(self, atendimento: ServicoDeAtendimento, whatsapp: WhatsAppGateway) -> None:
        self._atendimento = atendimento
        self._whatsapp = whatsapp
        self._deduplicador = _Deduplicador()

    async def processar(self, corpo_webhook: Mapping[str, Any]) -> None:
        mensagem = extrair_mensagem(corpo_webhook)
        if mensagem is None or self._deduplicador.ja_visto(mensagem.id):
            return
        try:
            resposta = await self._atendimento.atender(mensagem.telefone, mensagem.entrada)
        except Exception:  # fronteira do fluxo: o cliente nunca fica sem resposta
            # Só o id da mensagem vai para o log: nome, e-mail e endereço nunca são registrados.
            logger.exception("Falha ao atender a mensagem %s", mensagem.id)
            resposta = Resposta(MENSAGEM_FALHA_TECNICA)
        await self._whatsapp.enviar(mensagem.telefone, montar_mensagem(mensagem.telefone, resposta))
