"""Validação e normalização dos dados do pedido de gás. Funções puras, fáceis de testar.

O endereço é validado em endereco.py (pelo CEP), igual ao cadastro.

Sem botões, o cliente escreve como quiser ("quero um botijão P13, o pequeno mesmo", "umas 2
unidades", "duas, por favor", "vou pagar no pix"), então as validações abaixo procuram a
informação dentro da frase inteira, em vez de exigir uma palavra exata sozinha.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from types import MappingProxyType

from .modelos import DadoInvalidoError
from .modelos_pedido import LIMITE_DE_BOTIJOES_POR_PEDIDO, MOMENTO_DO_PAGAMENTO, FormaPagamento, TipoBotijao
from .intencoes import dispensa_troco
from .texto import palavras

PERGUNTA_PAGAMENTO = (
    f"Como prefere pagar? O pagamento é {MOMENTO_DO_PAGAMENTO}: Pix, dinheiro, cartão de débito "
    "ou cartão de crédito."
)
PERGUNTA_TROCO = "Vai precisar de troco? Se sim, me diz para quanto (ex.: troco para 100)."

_ALIAS_PAGAMENTO: MappingProxyType[str, FormaPagamento] = MappingProxyType({
    "pix": FormaPagamento.PIX,
    "dinheiro": FormaPagamento.DINHEIRO, "especie": FormaPagamento.DINHEIRO, "cash": FormaPagamento.DINHEIRO,
    "debito": FormaPagamento.DEBITO,
    "credito": FormaPagamento.CREDITO,
})
_PALAVRAS_CARTAO = frozenset({"cartao", "maquininha", "maquina"})
_TROCO_MAXIMO = Decimal("1000")

# MappingProxyType: visão somente leitura, ninguém de fora altera esse mapa por engano.
# Aceitamos o código (P13), o peso (13kg) e apelidos do dia a dia (pequeno/residencial etc.).
_ALIAS_TIPO_BOTIJAO: MappingProxyType[str, TipoBotijao] = MappingProxyType({
    "p13": TipoBotijao.P13, "13": TipoBotijao.P13, "13kg": TipoBotijao.P13,
    "pequeno": TipoBotijao.P13, "residencial": TipoBotijao.P13,
    "p20": TipoBotijao.P20, "20": TipoBotijao.P20, "20kg": TipoBotijao.P20,
    "medio": TipoBotijao.P20, "media": TipoBotijao.P20,
    "p45": TipoBotijao.P45, "45": TipoBotijao.P45, "45kg": TipoBotijao.P45,
    "grande": TipoBotijao.P45, "comercial": TipoBotijao.P45,
})

_NUMERO_POR_EXTENSO: MappingProxyType[str, int] = MappingProxyType({
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6,
})

_PADRAO_NUMERO = re.compile(r"(\d+)x?")


def validar_tipo_botijao(texto: str) -> TipoBotijao:
    for token in palavras(texto):  # "P-13" vira "p", "13": o "13" já basta
        tipo = _ALIAS_TIPO_BOTIJAO.get(token)
        if tipo is not None:
            return tipo
    raise DadoInvalidoError(
        "Não reconheci esse botijão. Me diz se é P13, P20 ou P45 (ou pequeno, médio ou grande)?"
    )


def validar_quantidade(texto: str) -> int:
    """Usa o primeiro número da frase, em algarismo ou por extenso: "2 botijões, um pra casa" -> 2."""
    quantidade = None
    for token in palavras(texto):
        numero = _PADRAO_NUMERO.fullmatch(token)  # "2" ou "2x"; ignora "p13", "13kg"
        if numero is not None:
            quantidade = int(numero.group(1))
            break
        if token in _NUMERO_POR_EXTENSO:
            quantidade = _NUMERO_POR_EXTENSO[token]
            break
    if quantidade is None:
        raise DadoInvalidoError("Não entendi a quantidade. Pode me dizer em números? Por exemplo: 2")
    if not (1 <= quantidade <= LIMITE_DE_BOTIJOES_POR_PEDIDO):
        raise DadoInvalidoError(
            f"Posso entregar de 1 a {LIMITE_DE_BOTIJOES_POR_PEDIDO} botijões por pedido. Quantos você quer?"
        )
    return quantidade


def detectar_forma_pagamento(texto: str | None) -> FormaPagamento | None:
    """A forma de pagamento citada na frase, ou None: "vou pagar no pix" -> PIX."""
    for token in palavras(texto):
        if token in _ALIAS_PAGAMENTO:
            return _ALIAS_PAGAMENTO[token]
    return None


def validar_forma_pagamento(texto: str) -> FormaPagamento:
    forma = detectar_forma_pagamento(texto)
    if forma is not None:
        return forma
    if set(palavras(texto)) & _PALAVRAS_CARTAO:
        raise DadoInvalidoError("No cartão de débito ou de crédito?")
    raise DadoInvalidoError(f"Não entendi a forma de pagamento. {PERGUNTA_PAGAMENTO}")


# Valor em reais, sem separador de milhar: "100", "50,50", "R$ 20.00". "1.000" é recusado
# (seria lido como R$ 1,00), e o cliente é orientado a mandar "1000".
_PADRAO_VALOR = re.compile(r"(?<![\d.,])(\d{1,4})(?:[.,](\d{1,2}))?(?![\d.,])")


def validar_troco(texto: str) -> Decimal | None:
    """None quando não precisa de troco ("não", "sem troco"); senão, o valor da nota (ex.: 100)."""
    encontrado = _PADRAO_VALOR.search(texto)
    if encontrado is None:
        if dispensa_troco(texto) or "nao" in palavras(texto):
            return None
        raise DadoInvalidoError(f"Não entendi. {PERGUNTA_TROCO}")
    try:
        valor = Decimal(f"{encontrado.group(1)}.{encontrado.group(2) or '0'}").quantize(Decimal("0.01"))
    except InvalidOperation as erro:  # não acontece com o padrão acima; por garantia
        raise DadoInvalidoError(f"Não entendi o valor. {PERGUNTA_TROCO}") from erro
    if not (Decimal("1") <= valor <= _TROCO_MAXIMO):
        raise DadoInvalidoError(f"Me manda o valor da nota, até R$ {_TROCO_MAXIMO:.0f} (ex.: troco para 100).")
    return valor
