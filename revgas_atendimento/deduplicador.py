"""Descarta mensagens repetidas: a Meta reenvia webhooks, e o n8n repassa cada reenvio."""
from __future__ import annotations

from collections import OrderedDict


class Deduplicador:
    """Guarda os últimos `capacidade` ids em memória. PRODUÇÃO: Redis SET NX com TTL."""

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
