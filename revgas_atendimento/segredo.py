"""Valor sensível (token, chave, segredo) que nunca aparece em log, print, traceback ou f-string.

    chave = Segredo("abc")
    print(chave)          -> ***
    repr(chave)           -> Segredo('***')
    f"{chave}"            -> ***
    chave.revelar()       -> "abc"   (só onde o valor é realmente usado)

Assim um `logger.info(configuracao)` ou um erro com a configuração no meio não vaza nada.
"""
from __future__ import annotations

import hmac


class Segredo:
    __slots__ = ("_valor",)

    def __init__(self, valor: str) -> None:
        if not isinstance(valor, str) or not valor:
            raise ValueError("Segredo precisa de um texto não vazio.")
        self._valor = valor

    @classmethod
    def de(cls, valor: str | Segredo | None) -> Segredo | None:
        """Aceita texto, Segredo ou None (útil para quem monta a configuração à mão, como os testes)."""
        if valor is None or isinstance(valor, Segredo):
            return valor
        return cls(valor)

    def revelar(self) -> str:
        return self._valor

    def confere(self, recebido: str) -> bool:
        """Comparação em tempo constante com um valor recebido de fora (cabeçalho, query string)."""
        return hmac.compare_digest(self._valor.encode(), recebido.encode())

    def __repr__(self) -> str:
        return "Segredo('***')"

    def __str__(self) -> str:
        return "***"

    def __format__(self, especificacao: str) -> str:
        return "***"

    def __eq__(self, outro: object) -> bool:
        return isinstance(outro, Segredo) and self.confere(outro._valor)

    def __hash__(self) -> int:
        return hash((Segredo, self._valor))

    def __reduce__(self):  # impede gravar o segredo por pickle (cache, fila, arquivo) sem querer
        raise TypeError("Segredo não pode ser serializado.")
