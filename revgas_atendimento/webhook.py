"""Lógica do webhook sem framework web: verificação, assinatura e processamento em segundo plano."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from .config import Configuracao
from .erros_http import RequisicaoRecusadaError
from .processador import ProcessadorWhatsApp
from .seguranca import assinatura_valida, tokens_iguais

__all__ = ["RequisicaoRecusadaError", "ServicoDeWebhook"]  # erro reexportado: imports antigos continuam valendo

logger = logging.getLogger(__name__)

_MOTIVO_DESATIVADO = "Webhook direto da Meta desativado: defina WA_APP_SECRET e WA_VERIFY_TOKEN no servidor."


class ServicoDeWebhook:
    def __init__(self, configuracao: Configuracao, processador: ProcessadorWhatsApp) -> None:
        self._config = configuracao
        self._processador = processador
        self._tarefas: set[asyncio.Task[None]] = set()

    def verificar(self, modo: str, token: str, desafio: str) -> str:
        """Handshake inicial da Meta (GET): devolve o desafio se o token de verificação conferir."""
        esperado = self._config.token_verificacao_whatsapp
        if not esperado:
            raise RequisicaoRecusadaError(503, _MOTIVO_DESATIVADO)
        if modo == "subscribe" and tokens_iguais(esperado, token):
            return desafio
        raise RequisicaoRecusadaError(403, "Token de verificação inválido.")

    async def receber(self, corpo_bruto: bytes, assinatura: str) -> None:
        """Valida a assinatura e agenda o processamento, devolvendo o controle na hora.

        A Meta espera resposta em poucos segundos. PRODUÇÃO: fila (Redis Streams, Celery).
        """
        segredo = self._config.segredo_app_whatsapp
        if not segredo:
            raise RequisicaoRecusadaError(503, _MOTIVO_DESATIVADO)
        if not assinatura_valida(segredo, corpo_bruto, assinatura):
            raise RequisicaoRecusadaError(401, "Assinatura inválida.")
        try:
            corpo = json.loads(corpo_bruto)
        except json.JSONDecodeError as erro:
            raise RequisicaoRecusadaError(400, "JSON inválido.") from erro

        tarefa = asyncio.create_task(self._processar_sem_propagar(corpo))
        self._tarefas.add(tarefa)
        tarefa.add_done_callback(self._tarefas.discard)

    async def aguardar_pendentes(self) -> None:
        """Espera o processamento em andamento terminar (útil em testes e no desligamento)."""
        if self._tarefas:
            await asyncio.gather(*self._tarefas)

    async def _processar_sem_propagar(self, corpo: Any) -> None:
        try:
            await self._processador.processar(corpo)
        except Exception:
            logger.exception("Falha inesperada no processamento do webhook")
