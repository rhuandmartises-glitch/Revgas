"""Validação e normalização dos três dados coletados. Funções puras, fáceis de testar."""
from __future__ import annotations

import re

from .modelos import DadoInvalidoError

_PADRAO_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}")
_TAMANHO_MAXIMO_EMAIL = 254


def _normalizar_espacos(texto: str) -> str:
    return " ".join(texto.split())


def validar_nome(texto: str) -> str:
    nome = _normalizar_espacos(texto)
    tamanho_valido = 2 <= len(nome) <= 100
    tem_letra = any(caractere.isalpha() for caractere in nome)
    tem_caractere_estranho = any(caractere.isdigit() or caractere == "@" for caractere in nome)
    if not tamanho_valido or not tem_letra or tem_caractere_estranho:
        raise DadoInvalidoError(
            "Não consegui entender o nome. Pode enviar seu nome completo, só com letras?"
        )
    return nome


def validar_email(texto: str) -> str:
    email = texto.strip().lower()
    if len(email) > _TAMANHO_MAXIMO_EMAIL or not _PADRAO_EMAIL.fullmatch(email):
        raise DadoInvalidoError("Esse e-mail parece inválido. Exemplo: nome@email.com. Pode conferir?")
    return email


def validar_endereco(texto: str) -> str:
    endereco = _normalizar_espacos(texto)
    tamanho_valido = 8 <= len(endereco) <= 200
    tem_letra = any(caractere.isalpha() for caractere in endereco)
    if not tamanho_valido or not tem_letra:
        raise DadoInvalidoError(
            "Preciso do endereço completo: rua, número e bairro. Pode enviar de novo?"
        )
    return endereco
