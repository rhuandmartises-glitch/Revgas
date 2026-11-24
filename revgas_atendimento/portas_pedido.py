"""Contrato (port) do repositório de pedidos de gás.

A sessão de pedido em andamento usa o próprio RepositorioDeSessoes de portas.py (e, na prática,
a classe SessoesEmMemoria de simulacoes.py).
"""
from __future__ import annotations

from typing import Protocol

from .modelos_pedido import Pedido


class RepositorioDePedidos(Protocol):
    async def salvar(self, pedido: Pedido) -> Pedido:
        """Registra um novo pedido e devolve o mesmo pedido com `id`. Levanta IntegracaoError se falhar."""
        ...

    async def listar_por_telefone(self, telefone: str) -> list[Pedido]:
        """Todos os pedidos do número, do mais antigo ao mais novo."""
        ...

    async def ultimo_por_telefone(self, telefone: str) -> Pedido | None: ...

    async def cancelar(self, id_pedido: int) -> bool:
        """Marca como CANCELADO. False se o pedido não existe ou já não estava CONFIRMADO."""
        ...
