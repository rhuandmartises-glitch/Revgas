"""Leitura opcional de um arquivo .env (CHAVE=valor), sem dependências externas."""
from __future__ import annotations

import os
from pathlib import Path

from .modelos import ConfiguracaoInvalidaError


def carregar_arquivo_env(caminho: Path = Path(".env")) -> bool:
    """Carrega o arquivo em os.environ sem sobrescrever variáveis já definidas.

    Retorna False se o arquivo não existir. Nunca inclui o conteúdo das linhas nas mensagens de erro.
    """
    if not caminho.is_file():
        return False
    try:
        linhas = caminho.read_text(encoding="utf-8-sig").splitlines()  # utf-8-sig aceita o BOM do Bloco de Notas
    except UnicodeDecodeError as erro:
        raise ConfiguracaoInvalidaError(f"Não consegui ler {caminho}: salve o arquivo como UTF-8.") from erro

    for numero, linha in enumerate(linhas, start=1):
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        chave, separador, valor = linha.partition("=")
        if not separador or not chave.strip():
            raise ConfiguracaoInvalidaError(f"{caminho}, linha {numero}: use o formato CHAVE=valor.")
        os.environ.setdefault(chave.strip(), _remover_aspas(valor.strip()))
    return True


def _remover_aspas(valor: str) -> str:
    if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
        return valor[1:-1]
    return valor
