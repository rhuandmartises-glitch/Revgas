"""Entidades, mensagens e erros de domínio. Sem dependências externas."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

LIMITE_DE_BOTOES = 3
LIMITE_DO_TITULO_DO_BOTAO = 20  # restrição da API do WhatsApp


# ── Erros de domínio ────────────────────────────────────────────────────────
class ErroDeDominio(Exception):
    """Base de todos os erros previstos pelo negócio."""


class ConfiguracaoInvalidaError(ErroDeDominio):
    """Variável de ambiente ausente."""


class IntegracaoError(ErroDeDominio):
    """Falha ao gravar no ERP ou ao enviar pelo WhatsApp."""


class DadoInvalidoError(ErroDeDominio):
    """Entrada rejeitada. A mensagem é amigável e pode ser enviada ao cliente."""


# ── Entidades ───────────────────────────────────────────────────────────────
class Etapa(str, Enum):
    NOME = "NOME"
    EMAIL = "EMAIL"
    ENDERECO = "ENDERECO"
    CONFIRMACAO = "CONFIRMACAO"


@dataclass(frozen=True)
class Cadastro:
    """Único dado pessoal guardado (além do telefone, que identifica o cliente)."""

    telefone: str = field(repr=False)
    nome: str = field(repr=False)
    email: str = field(repr=False)
    endereco: str = field(repr=False)


@dataclass(frozen=True)
class Sessao:
    """Progresso de uma conversa em andamento. Descartada ao concluir, cancelar ou expirar."""

    telefone: str = field(repr=False)
    etapa: Etapa
    nome: str | None = field(default=None, repr=False)
    email: str | None = field(default=None, repr=False)
    endereco: str | None = field(default=None, repr=False)


# ── Entrada e saída da conversa (independentes do WhatsApp) ─────────────────
@dataclass(frozen=True)
class Entrada:
    texto: str | None = field(default=None, repr=False)
    botao_id: str | None = None


@dataclass(frozen=True)
class Botao:
    id: str
    titulo: str

    def __post_init__(self) -> None:
        if len(self.titulo) > LIMITE_DO_TITULO_DO_BOTAO:
            raise ValueError(
                f"Título de botão acima de {LIMITE_DO_TITULO_DO_BOTAO} caracteres: {self.titulo!r}"
            )


@dataclass(frozen=True)
class Resposta:
    texto: str = field(repr=False)
    botoes: tuple[Botao, ...] = ()

    def __post_init__(self) -> None:
        if len(self.botoes) > LIMITE_DE_BOTOES:
            raise ValueError(f"No máximo {LIMITE_DE_BOTOES} botões por mensagem.")
