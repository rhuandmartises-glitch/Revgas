"""Servidor HTTP só com o cadastro (sem pedido de gás).

Uso: uvicorn revgas_atendimento.api:criar_app --factory --host 127.0.0.1 --port 8000
Para cadastro + pedido de gás, use revgas_atendimento.api_pedido:criar_app_com_pedido_de_gas.
"""
from __future__ import annotations

from fastapi import FastAPI

from .ambiente import variaveis_do_servidor
from .aplicacao import criar_aplicacao
from .composicao import montar_atendimento_cadastro
from .config import Configuracao


def criar_app(configuracao: Configuracao | None = None) -> FastAPI:
    if configuracao is None:
        configuracao = Configuracao.do_ambiente(variaveis_do_servidor())  # .env + sistema (sistema ganha)
    return criar_aplicacao(configuracao, montar_atendimento_cadastro(configuracao), "RevGás Atendimento")
