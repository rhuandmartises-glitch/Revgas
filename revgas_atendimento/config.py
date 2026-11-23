"""Configuração centralizada: lida uma vez, na inicialização, e injetada onde for preciso."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from .modelos import ConfiguracaoInvalidaError


@dataclass(frozen=True)
class Configuracao:
    segredo_app_whatsapp: str = field(repr=False)  # repr=False: não vaza em logs/tracebacks
    token_verificacao_whatsapp: str = field(repr=False)
    ttl_sessao_s: float = 900.0  # 15 min de inatividade e os dados parciais são descartados

    @classmethod
    def do_ambiente(cls) -> Configuracao:
        return cls(
            segredo_app_whatsapp=_ler_obrigatoria("WA_APP_SECRET"),
            token_verificacao_whatsapp=_ler_obrigatoria("WA_VERIFY_TOKEN"),
        )


def _ler_obrigatoria(nome: str) -> str:
    valor = os.getenv(nome)
    if not valor:
        raise ConfiguracaoInvalidaError(f"Defina a variável de ambiente {nome}.")
    return valor
