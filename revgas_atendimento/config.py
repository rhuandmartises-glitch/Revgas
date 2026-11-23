"""Configuração única para execução HTTP, webhook e console."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from .modelos import ConfiguracaoInvalidaError


@dataclass(frozen=True)
class CredenciaisWhatsApp:
    token_acesso: str = field(repr=False)
    id_numero: str
    versao_api: str = "v26.0"


@dataclass(frozen=True)
class Configuracao:
    segredo_app_whatsapp: str = field(repr=False)
    token_verificacao_whatsapp: str = field(repr=False)
    ttl_sessao_s: float = 900.0
    credenciais_whatsapp: CredenciaisWhatsApp | None = None
    caminho_banco: str = "dados/revgas.sqlite3"
    intervalo_worker_s: float = 0.2
    tentativas_maximas: int = 5

    @classmethod
    def do_ambiente(cls) -> Configuracao:
        from .ambiente import carregar_arquivo_env
        carregar_arquivo_env()
        token = os.getenv("WA_ACCESS_TOKEN", "").strip()
        numero = os.getenv("WA_PHONE_NUMBER_ID", "").strip()
        if bool(token) != bool(numero):
            raise ConfiguracaoInvalidaError("WA_ACCESS_TOKEN e WA_PHONE_NUMBER_ID devem ser configurados juntos.")
        versao = os.getenv("WA_API_VERSION", "v26.0").strip()
        if not versao.startswith("v") or not versao[1:].replace(".", "").isdigit():
            raise ConfiguracaoInvalidaError("WA_API_VERSION deve ter formato v26.0.")
        credenciais = CredenciaisWhatsApp(token, numero, versao) if token else None
        caminho = os.getenv("REVGAS_DB_PATH", "dados/revgas.sqlite3").strip()
        if not caminho:
            raise ConfiguracaoInvalidaError("REVGAS_DB_PATH não pode ser vazio.")
        return cls(
            segredo_app_whatsapp=_ler_obrigatoria("WA_APP_SECRET"),
            token_verificacao_whatsapp=_ler_obrigatoria("WA_VERIFY_TOKEN"),
            credenciais_whatsapp=credenciais,
            caminho_banco=caminho,
        )


def _ler_obrigatoria(nome: str) -> str:
    valor = os.getenv(nome, "").strip()
    if not valor:
        raise ConfiguracaoInvalidaError(f"Defina a variável de ambiente {nome}.")
    return valor
