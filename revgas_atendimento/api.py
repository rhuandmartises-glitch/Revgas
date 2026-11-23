"""Camada HTTP (FastAPI): valida a assinatura, responde 200 rápido e processa em segundo plano."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from .atendimento import ServicoDeAtendimento
from .config import Configuracao
from .processador import ProcessadorWhatsApp
from .seguranca import assinatura_valida, tokens_iguais
from .simulacoes import CadastrosEmMemoria, SessoesEmMemoria, WhatsAppEmMemoria

logger = logging.getLogger(__name__)


def montar_processador(configuracao: Configuracao) -> ProcessadorWhatsApp:
    """Raiz de composição: único lugar que conhece as implementações concretas.

    PRODUÇÃO: troque CadastrosEmMemoria pelo ERP RevGás, SessoesEmMemoria por Redis e
    WhatsAppEmMemoria pelo cliente da WhatsApp Cloud API. Do jeito que está, os cadastros
    se perdem ao reiniciar e as respostas só aparecem no console.
    """
    atendimento = ServicoDeAtendimento(
        CadastrosEmMemoria(), SessoesEmMemoria(configuracao.ttl_sessao_s)
    )
    return ProcessadorWhatsApp(atendimento, WhatsAppEmMemoria())


def criar_app(configuracao: Configuracao | None = None) -> FastAPI:
    configuracao = configuracao or Configuracao.do_ambiente()
    processador = montar_processador(configuracao)
    tarefas_em_andamento: set[asyncio.Task[None]] = set()
    app = FastAPI(title="RevGás Atendimento")

    @app.get("/webhook/whatsapp")
    async def verificar_webhook(
        modo: str = Query("", alias="hub.mode"),
        token: str = Query("", alias="hub.verify_token"),
        desafio: str = Query("", alias="hub.challenge"),
    ) -> PlainTextResponse:
        if modo == "subscribe" and tokens_iguais(configuracao.token_verificacao_whatsapp, token):
            return PlainTextResponse(desafio)
        raise HTTPException(status_code=403)

    @app.post("/webhook/whatsapp")
    async def receber_webhook(
        requisicao: Request, x_hub_signature_256: str = Header(default="")
    ) -> dict[str, str]:
        corpo_bruto = await requisicao.body()
        if not assinatura_valida(configuracao.segredo_app_whatsapp, corpo_bruto, x_hub_signature_256):
            raise HTTPException(status_code=401)
        try:
            corpo = json.loads(corpo_bruto)
        except json.JSONDecodeError as erro:
            raise HTTPException(status_code=400, detail="JSON inválido") from erro

        # Responde 200 na hora (a Meta espera poucos segundos) e processa em segundo plano.
        # PRODUÇÃO: fila (Redis Streams, Celery) em vez de create_task.
        tarefa = asyncio.create_task(_processar_sem_propagar(processador, corpo))
        tarefas_em_andamento.add(tarefa)
        tarefa.add_done_callback(tarefas_em_andamento.discard)
        return {"status": "ok"}

    return app


async def _processar_sem_propagar(processador: ProcessadorWhatsApp, corpo: dict[str, Any]) -> None:
    try:
        await processador.processar(corpo)
    except Exception:
        logger.exception("Falha inesperada no processamento do webhook")
