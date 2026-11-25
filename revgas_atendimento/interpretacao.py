"""Entende, em texto livre, a resposta do cliente quando pedimos para confirmar os dados.

Usado no cadastro e no pedido de gás, para os dois funcionarem do mesmo jeito. Os sinônimos
ficam em intencoes.py.
- "sim", "pode mandar", "tá certo", "fechado", "👍"     -> CONFIRMAR
- um CEP ("01001-000") ou um endereço com número         -> NOVO_ENDERECO (abre a coleta pelo CEP)
- "não", "tá errado", "mudou"...                        -> NEGAR (pedimos o CEP do endereço certo)
- "refazer", "corrigir", "começar de novo"              -> REFAZER (recomeça do início)
- qualquer outra coisa                                  -> DESCONHECIDO (repetimos o resumo)
"""
from __future__ import annotations

from enum import Enum

from .endereco import extrair_cep, parece_endereco
from .intencoes import concorda, discorda, quer_refazer


class Intencao(Enum):
    CONFIRMAR = "CONFIRMAR"
    NOVO_ENDERECO = "NOVO_ENDERECO"
    NEGAR = "NEGAR"
    REFAZER = "REFAZER"
    DESCONHECIDO = "DESCONHECIDO"


def interpretar_confirmacao(texto: str | None) -> Intencao:
    if not texto:
        return Intencao.DESCONHECIDO
    if quer_refazer(texto):
        return Intencao.REFAZER
    # Um CEP é sempre um pedido de troca, mesmo com "não"/"mudou" junto ("mudou, CEP 01001-000").
    if extrair_cep(texto):
        return Intencao.NOVO_ENDERECO
    # Endereço sem CEP: só se não houver "sim"/"não" na frase. Assim "sim, os 2" confirma e
    # "não, é Rua X, 12" vira NEGAR (aí pedimos o CEP do endereço certo).
    sim, nao = concorda(texto), discorda(texto)
    if not sim and not nao and parece_endereco(texto):
        return Intencao.NOVO_ENDERECO
    if nao:
        return Intencao.NEGAR
    if sim:
        return Intencao.CONFIRMAR
    return Intencao.DESCONHECIDO
