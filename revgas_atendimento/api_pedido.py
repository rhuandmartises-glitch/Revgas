"""Servidor HTTP completo: cadastro + pedido de gás. É o recomendado.

Uso: uvicorn revgas_atendimento.api_pedido:criar_app_com_pedido_de_gas --factory --host 127.0.0.1 --port 8000
Rotas e modos (webhook direto da Meta ou n8n): veja aplicacao.py e README_N8N.md.
"""
from __future__ import annotations

from fastapi import FastAPI

from .ambiente import carregar_arquivo_env
from .aplicacao import MensagemDeAutomacao, RespostaDeAutomacao, criar_aplicacao
from .composicao_pedido import montar_atendimento_com_pedido_de_gas
from .config import Configuracao

__all__ = ["MensagemDeAutomacao", "RespostaDeAutomacao", "criar_app_com_pedido_de_gas"]


def criar_app_com_pedido_de_gas(configuracao: Configuracao | None = None) -> FastAPI:
    if configuracao is None:
        carregar_arquivo_env()  # .env opcional; variáveis já definidas no ambiente têm prioridade
        configuracao = Configuracao.do_ambiente()
    return criar_aplicacao(
        configuracao, montar_atendimento_com_pedido_de_gas(configuracao), "RevGás Atendimento + Pedido de Gás"
    )
