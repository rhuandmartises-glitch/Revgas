"""Validação e normalização do nome e do telefone de contato. Funções puras, fáceis de testar.

O endereço tem um módulo próprio (endereco.py), porque é validado pelo CEP.
"""
from __future__ import annotations

from .modelos import DadoInvalidoError
from .texto import normalizar_espacos

# DDDs em uso no Brasil (plano de numeração da Anatel). Um número com DDD fora desta lista não existe.
DDDS_VALIDOS = frozenset({
    11, 12, 13, 14, 15, 16, 17, 18, 19,
    21, 22, 24, 27, 28,
    31, 32, 33, 34, 35, 37, 38,
    41, 42, 43, 44, 45, 46, 47, 48, 49,
    51, 53, 54, 55,
    61, 62, 63, 64, 65, 66, 67, 68, 69,
    71, 73, 74, 75, 77, 79,
    81, 82, 83, 84, 85, 86, 87, 88, 89,
    91, 92, 93, 94, 95, 96, 97, 98, 99,
})

_EXEMPLO_TELEFONE = "por exemplo: 11 98888-7777"


def validar_nome(texto: str) -> str:
    nome = normalizar_espacos(texto)
    tamanho_valido = 2 <= len(nome) <= 100
    tem_letra = any(caractere.isalpha() for caractere in nome)
    tem_caractere_estranho = any(caractere.isdigit() or caractere == "@" for caractere in nome)
    if not tamanho_valido or not tem_letra or tem_caractere_estranho:
        raise DadoInvalidoError(
            "Não consegui entender o nome. Pode enviar seu nome completo, só com letras?"
        )
    return nome


def validar_telefone(texto: str) -> str:
    """Aceita o telefone escrito de qualquer jeito ("(11) 98888-7777", "+55 11 98888 7777",
    "011 98888-7777") e devolve só DDD + número, conferindo:
    - se tem DDD e se esse DDD existe;
    - celular: 11 dígitos, começando com 9 depois do DDD;
    - fixo: 10 dígitos, começando com 2, 3, 4 ou 5 depois do DDD;
    - número que não seja só um dígito repetido (ex.: 99999-9999).
    """
    digitos = "".join(caractere for caractere in texto if caractere.isdigit())
    if len(digitos) > 11 and digitos.startswith("0"):  # "0" de longa distância: 011 98888-7777
        digitos = digitos.lstrip("0")
    if len(digitos) > 11 and digitos.startswith("55"):  # código do Brasil: +55 11 98888-7777
        digitos = digitos[2:]

    if len(digitos) in (8, 9):
        raise DadoInvalidoError(f"Faltou o DDD. Pode mandar o telefone com DDD, {_EXEMPLO_TELEFONE}?")
    if len(digitos) not in (10, 11):
        raise DadoInvalidoError(
            f"Esse telefone parece incompleto ou com números a mais. Envie com DDD, {_EXEMPLO_TELEFONE}."
        )

    ddd, numero = int(digitos[:2]), digitos[2:]
    if ddd not in DDDS_VALIDOS:
        raise DadoInvalidoError(f"O DDD {digitos[:2]} não existe. Confere e me manda de novo, {_EXEMPLO_TELEFONE}.")
    if len(numero) == 9 and numero[0] != "9":
        raise DadoInvalidoError(f"Celular tem que começar com 9 depois do DDD, {_EXEMPLO_TELEFONE}.")
    if len(numero) == 8 and numero[0] not in "2345":
        mensagem = (
            "Parece um celular sem o 9 na frente. Pode mandar de novo com o 9"
            if numero[0] in "6789"
            else "Esse número fixo não parece válido. Confere e me manda de novo"
        )
        raise DadoInvalidoError(f"{mensagem}, {_EXEMPLO_TELEFONE}?")
    if len(set(numero)) == 1:
        raise DadoInvalidoError(f"Esse número não parece real. Confere e me manda de novo, {_EXEMPLO_TELEFONE}.")
    return digitos


def formatar_telefone(digitos: str) -> str:
    """"11988887777" -> "(11) 98888-7777"; "1133334444" -> "(11) 3333-4444"."""
    if len(digitos) not in (10, 11):
        return digitos
    return f"({digitos[:2]}) {digitos[2:-4]}-{digitos[-4:]}"
