"""Adaptador em memória para os pedidos de gás (demos e testes). No servidor: PedidosSqlite."""
from __future__ import annotations

from dataclasses import replace

from .modelos_pedido import Pedido, StatusPedido


class PedidosEmMemoria:
    """Em produção: chamadas ao ERP/sistema de logística da RevGás."""

    def __init__(self) -> None:
        self._pedidos: list[Pedido] = []

    async def salvar(self, pedido: Pedido) -> Pedido:
        salvo = replace(pedido, id=len(self._pedidos) + 1)
        self._pedidos.append(salvo)
        return salvo

    async def listar_por_telefone(self, telefone: str) -> list[Pedido]:
        return [pedido for pedido in self._pedidos if pedido.telefone == telefone]

    async def ultimo_por_telefone(self, telefone: str) -> Pedido | None:
        pedidos = await self.listar_por_telefone(telefone)
        return pedidos[-1] if pedidos else None

    async def cancelar(self, id_pedido: int) -> bool:
        for posicao, pedido in enumerate(self._pedidos):
            if pedido.id == id_pedido and pedido.status is StatusPedido.CONFIRMADO:
                self._pedidos[posicao] = replace(pedido, status=StatusPedido.CANCELADO)
                return True
        return False
