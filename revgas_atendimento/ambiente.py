"""Leitura do arquivo .env (CHAVE=valor), sem dependências externas.

O servidor usa `variaveis_do_servidor()`: lê o .env direto para a configuração, sem copiar os
segredos para as variáveis de ambiente do processo (que qualquer programa filho herdaria).
Variáveis já definidas no sistema têm prioridade sobre o arquivo.
"""
from __future__ import annotations

import os
from pathlib import Path

from .modelos import ConfiguracaoInvalidaError

ARQUIVO_PADRAO = Path(".env")


def ler_arquivo_env(caminho: Path = ARQUIVO_PADRAO) -> dict[str, str]:
    """Conteúdo do arquivo como dicionário ({} se não existir).

    Aceita comentários (#), linhas em branco, aspas em volta do valor e o BOM do Bloco de Notas.
    As mensagens de erro citam o número da linha, nunca o conteúdo (que pode ser um segredo).
    """
    if not caminho.is_file():
        return {}
    try:
        linhas = caminho.read_text(encoding="utf-8-sig").splitlines()  # utf-8-sig aceita o BOM do Bloco de Notas
    except UnicodeDecodeError as erro:
        raise ConfiguracaoInvalidaError(f"Não consegui ler {caminho}: salve o arquivo como UTF-8.") from erro

    variaveis: dict[str, str] = {}
    for numero, linha in enumerate(linhas, start=1):
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        chave, separador, valor = linha.partition("=")
        if not separador or not chave.strip():
            raise ConfiguracaoInvalidaError(f"{caminho}, linha {numero}: use o formato CHAVE=valor.")
        variaveis[chave.strip()] = _remover_aspas(valor.strip())
    return variaveis


def variaveis_do_servidor(caminho: Path = ARQUIVO_PADRAO) -> dict[str, str]:
    """O .env com as variáveis do sistema por cima (as do sistema ganham)."""
    return {**ler_arquivo_env(caminho), **os.environ}


def carregar_arquivo_env(caminho: Path = ARQUIVO_PADRAO) -> bool:
    """Copia o .env para os.environ sem sobrescrever o que já existe. Retorna False se não existir.

    Só para scripts auxiliares (testar_webhook.py). O servidor usa variaveis_do_servidor().
    """
    if not caminho.is_file():
        return False
    for chave, valor in ler_arquivo_env(caminho).items():
        os.environ.setdefault(chave, valor)
    return True


def _remover_aspas(valor: str) -> str:
    if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
        return valor[1:-1]
    return valor
