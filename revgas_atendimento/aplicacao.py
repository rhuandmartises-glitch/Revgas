"""Fábrica da aplicação HTTP (FastAPI), única para api.py e api_pedido.py.

Rotas:
- GET  /saude              verificação de que o servidor está no ar.
- GET  /webhook/whatsapp   handshake da Meta (webhook direto).
- POST /webhook/whatsapp   mensagens da Meta (webhook direto): responde 200 e processa em segundo plano.
- POST /mensagem           para o n8n: recebe a mensagem e devolve o texto da resposta (não envia nada).

Use só um modo por número de WhatsApp (direto OU n8n), senão o cliente recebe respostas em dobro.
"""
from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from .automacao import ServicoDeAutomacao
from .composicao import montar_servico_de_webhook
from .config import Configuracao
from .erros_http import RequisicaoRecusadaError
from .portas import Atendente
from .seguranca import proteger_logs_de_acesso


class MensagemDeAutomacao(BaseModel):
    telefone: str = Field(min_length=1, max_length=32, description="Número do cliente (campo `from` da Meta).")
    texto: str | None = Field(default=None, max_length=4096, description="Texto enviado pelo cliente.")
    id: str | None = Field(default=None, max_length=256, description="Id da mensagem (wamid), evita responder duas vezes.")


class RespostaDeAutomacao(BaseModel):
    resposta: str | None = Field(description="Texto para enviar ao cliente; null se a mensagem já foi respondida.")
    duplicada: bool = False


def criar_aplicacao(configuracao: Configuracao, atendimento: Atendente, titulo: str) -> FastAPI:
    """Um só `atendimento` para todas as rotas: a conversa é a mesma, venha da Meta ou do n8n."""
    webhook = montar_servico_de_webhook(configuracao, atendimento)
    automacao = ServicoDeAutomacao(atendimento, configuracao.chave_api_automacao)
    proteger_logs_de_acesso()

    # Sem /docs, /redoc e /openapi.json: o servidor fica exposto pelo túnel, e o mapa da API
    # não precisa ficar público. Para consultar localmente, rode uma cópia com docs ativados.
    app = FastAPI(title=titulo, docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(RequestValidationError)
    async def corpo_invalido(_: Request, erro: RequestValidationError) -> JSONResponse:
        # O padrão do FastAPI devolve o corpo recebido ("input"), que pode ter dados do cliente.
        detalhes = [{"campo": ".".join(map(str, e["loc"])), "erro": e["msg"]} for e in erro.errors()]
        return JSONResponse(status_code=422, content={"detail": detalhes})

    @app.get("/saude")
    async def saude() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/webhook/whatsapp")
    async def verificar_webhook(
        modo: str = Query("", alias="hub.mode"),
        token: str = Query("", alias="hub.verify_token"),
        desafio: str = Query("", alias="hub.challenge"),
    ) -> PlainTextResponse:
        try:
            return PlainTextResponse(webhook.verificar(modo, token, desafio))
        except RequisicaoRecusadaError as erro:
            raise HTTPException(status_code=erro.status_http, detail=str(erro)) from erro

    @app.post("/webhook/whatsapp")
    async def receber_webhook(requisicao: Request, x_hub_signature_256: str = Header(default="")) -> dict[str, str]:
        try:
            await webhook.receber(await requisicao.body(), x_hub_signature_256)
        except RequisicaoRecusadaError as erro:
            raise HTTPException(status_code=erro.status_http, detail=str(erro)) from erro
        return {"status": "ok"}

    @app.post("/mensagem")
    async def responder_mensagem(
        mensagem: MensagemDeAutomacao, x_api_key: str = Header(default="")
    ) -> RespostaDeAutomacao:
        try:
            texto = await automacao.responder(x_api_key, mensagem.telefone, mensagem.texto, mensagem.id)
        except RequisicaoRecusadaError as erro:
            raise HTTPException(status_code=erro.status_http, detail=str(erro)) from erro
        return RespostaDeAutomacao(resposta=texto, duplicada=texto is None)

    app.state.webhook = webhook  # acesso para testes e para aguardar pendentes no desligamento
    return app
