"""Contratos (ports) das integrações externas. A produção fornece implementações destes Protocols."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from .modelos import Cadastro, Sessao


class RepositorioDeCadastros(Protocol):
    async def buscar_por_telefone(self, telefone: str) -> Cadastro | None: ...

    async def salvar(self, cadastro: Cadastro) -> None:
        """Insere ou atualiza o cadastro do telefone. Levanta IntegracaoError se falhar."""
        ...


class RepositorioDeSessoes(Protocol):
    """Sessões expiram sozinhas após inatividade (em produção, Redis com SETEX)."""

    async def obter(self, telefone: str) -> Sessao | None: ...

    async def salvar(self, sessao: Sessao) -> None: ...

    async def remover(self, telefone: str) -> None: ...


class WhatsAppGateway(Protocol):
    async def enviar(self, telefone: str, mensagem: Mapping[str, Any]) -> None: ...
