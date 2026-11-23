"""HTTP: autentica, persiste em SQLite, então confirma o recebimento."""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, JSONResponse

from .composicao import montar_componentes
from .config import Configuracao
from .seguranca import assinatura_valida, tokens_iguais
from .whatsapp import extrair_mensagens

logger = logging.getLogger(__name__)


def criar_app(configuracao: Configuracao | None = None) -> FastAPI:
    configuracao = configuracao or Configuracao.do_ambiente()
    componentes = montar_componentes(configuracao)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        tarefa = asyncio.create_task(componentes.worker.executar_continuamente(configuracao.intervalo_worker_s))
        app.state.tarefa_worker = tarefa
        try:
            yield
        finally:
            tarefa.cancel()
            try:
                await tarefa
            except asyncio.CancelledError:
                pass

    app = FastAPI(title='RevGás Atendimento', lifespan=lifespan)
    app.state.componentes = componentes

    @app.get('/health')
    async def saude() -> JSONResponse:
        """Sinal operacional mínimo; sem mensagens, telefones nem tokens."""
        tarefa = getattr(app.state, 'tarefa_worker', None)
        worker_ativo = tarefa is not None and not tarefa.done()
        try:
            with componentes.banco.conexao() as conexao:
                conexao.execute('SELECT 1').fetchone()
            banco_ativo = True
        except Exception:
            logger.exception('Falha ao verificar disponibilidade do banco')
            banco_ativo = False
        pronto = worker_ativo and banco_ativo
        return JSONResponse(
            {'status': 'ok' if pronto else 'unavailable',
             'worker': 'running' if worker_ativo else 'stopped',
             'database': 'ok' if banco_ativo else 'unavailable',
             'mode': 'simulation' if configuracao.credenciais_whatsapp is None else 'whatsapp'},
            status_code=200 if pronto else 503,
        )

    @app.get('/webhook/whatsapp')
    async def verificar_webhook(
        modo: str = Query('', alias='hub.mode'),
        token: str = Query('', alias='hub.verify_token'),
        desafio: str = Query('', alias='hub.challenge'),
    ) -> PlainTextResponse:
        if modo == 'subscribe' and tokens_iguais(configuracao.token_verificacao_whatsapp, token):
            return PlainTextResponse(desafio)
        raise HTTPException(status_code=403)

    @app.post('/webhook/whatsapp')
    async def receber_webhook(requisicao: Request, x_hub_signature_256: str = Header(default='')) -> dict[str, str]:
        corpo = await requisicao.body()
        if not assinatura_valida(configuracao.segredo_app_whatsapp, corpo, x_hub_signature_256):
            raise HTTPException(status_code=401)
        try:
            evento = json.loads(corpo)
        except json.JSONDecodeError as erro:
            raise HTTPException(status_code=400, detail='JSON inválido') from erro
        try:
            await componentes.caixa.registrar(extrair_mensagens(evento))
        except Exception:
            logger.exception('Falha ao persistir webhook (responder com erro para retry Meta)')
            raise HTTPException(status_code=503, detail='Armazenamento indisponível')
        return {'status': 'ok'}

    return app
