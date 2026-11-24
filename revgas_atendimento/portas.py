"""Contratos (ports) das integrações externas. A produção fornece implementações destes Protocols."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, TypeVar

from .endereco import EnderecoDoCep
from .modelos import Cadastro, Entrada, Resposta

S = TypeVar("S")  # tipo da sessão guardada: Sessao (cadastro) ou SessaoPedido (pedido)


class Atendente(Protocol):
    """Quem responde a conversa: ServicoDeAtendimento (só cadastro) ou ServicoDeAtendimentoIntegrado."""

    async def atender(self, telefone: str, entrada: Entrada) -> Resposta: ...


class RepositorioDeCadastros(Protocol):
    async def buscar_por_telefone(self, telefone: str) -> Cadastro | None: ...

    async def salvar(self, cadastro: Cadastro) -> None:
        """Insere ou atualiza o cadastro do telefone. Levanta IntegracaoError se falhar."""
        ...


class RepositorioDeSessoes(Protocol[S]):
    """Sessões expiram sozinhas após inatividade (em produção, Redis com SETEX).

    A sessão precisa ter o atributo `telefone`, que é a chave de armazenamento."""

    async def obter(self, telefone: str) -> S | None: ...

    async def salvar(self, sessao: S) -> None: ...

    async def remover(self, telefone: str) -> None: ...


class ConsultaDeCep(Protocol):
    async def consultar(self, cep: str) -> EnderecoDoCep | None:
        """`cep` com 8 dígitos. None se o CEP não existe. Levanta IntegracaoError se o serviço falhar."""
        ...


class WhatsAppGateway(Protocol):
    async def enviar(self, telefone: str, mensagem: Mapping[str, Any]) -> None: ...
