"""Normalização de texto livre do cliente. Único lugar com essas regras (antes repetidas em 4 módulos)."""
from __future__ import annotations

import re
import unicodedata

_PADRAO_PALAVRA = re.compile(r"[a-z0-9]+")


def sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")


def palavras(texto: str | None) -> list[str]:
    """Minúsculas, sem acento e sem pontuação: "Quero GÁS, já!" -> ["quero", "gas", "ja"]."""
    return _PADRAO_PALAVRA.findall(sem_acento((texto or "").lower()))


def comando(texto: str | None) -> str:
    """A mensagem inteira como comando: "Cancelar!" -> "cancelar", "Deixa pra lá." -> "deixa pra la"."""
    return " ".join(palavras(texto))


def normalizar_espacos(texto: str) -> str:
    return " ".join(texto.split())
