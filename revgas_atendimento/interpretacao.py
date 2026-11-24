"""Entende, em texto livre, a resposta do cliente quando pedimos para confirmar os dados.

Usado tanto no cadastro quanto no pedido de gás, para que os dois funcionem do mesmo jeito:
- "sim", "isso mesmo", "pode mandar"...                -> CONFIRMAR
- um CEP ("01001-000") ou um endereço com número         -> NOVO_ENDERECO (abre a coleta pelo CEP)
- "não", "tá errado", "mudou"...                        -> NEGAR (pedimos o CEP do endereço certo)
- "refazer", "corrigir"                                 -> REFAZER (recomeça do início)
- qualquer outra coisa                                  -> DESCONHECIDO (repetimos o resumo)
"""
from __future__ import annotations

from enum import Enum

from .endereco import extrair_cep, parece_endereco
from .texto import palavras as _palavras

_PALAVRAS_CONFIRMAR = frozenset({
    "sim", "s", "confirmo", "confirmar", "confirmado", "certo", "certinho", "correto", "isso",
    "ok", "beleza", "blz", "pode", "claro", "perfeito", "exato", "positivo",
})
_PALAVRAS_NEGAR = frozenset({"nao", "n", "errado", "errada", "mudar", "mudou", "mudei", "trocar", "outro"})
_PALAVRAS_REFAZER = frozenset({"refazer", "corrigir", "recomecar"})


class Intencao(Enum):
    CONFIRMAR = "CONFIRMAR"
    NOVO_ENDERECO = "NOVO_ENDERECO"
    NEGAR = "NEGAR"
    REFAZER = "REFAZER"
    DESCONHECIDO = "DESCONHECIDO"


def interpretar_confirmacao(texto: str | None) -> Intencao:
    if not texto:
        return Intencao.DESCONHECIDO
    palavras = set(_palavras(texto))

    if palavras & _PALAVRAS_REFAZER:
        return Intencao.REFAZER
    # Um CEP é sempre um pedido de troca, mesmo com "não"/"mudou" junto ("mudou, CEP 01001-000").
    if extrair_cep(texto):
        return Intencao.NOVO_ENDERECO
    # Endereço sem CEP: só se não houver "sim"/"não" na frase. Assim "sim, os 2" confirma e
    # "não, é Rua X, 12" vira NEGAR (aí pedimos o CEP do endereço certo).
    tem_sim_ou_nao = bool(palavras & (_PALAVRAS_CONFIRMAR | _PALAVRAS_NEGAR))
    if not tem_sim_ou_nao and parece_endereco(texto):
        return Intencao.NOVO_ENDERECO
    if palavras & _PALAVRAS_NEGAR:
        return Intencao.NEGAR
    if palavras & _PALAVRAS_CONFIRMAR:
        return Intencao.CONFIRMAR
    return Intencao.DESCONHECIDO
