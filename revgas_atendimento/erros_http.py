"""Erro que a camada HTTP traduz em status: os serviços não dependem de FastAPI."""
from __future__ import annotations

from .modelos import ErroDeDominio


class RequisicaoRecusadaError(ErroDeDominio):
    """A requisição deve ser rejeitada com o status HTTP indicado."""

    def __init__(self, status_http: int, motivo: str) -> None:
        super().__init__(motivo)
        self.status_http = status_http
