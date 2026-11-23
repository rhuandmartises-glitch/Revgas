"""Funcoes de seguranca do webhook, independentes de framework (por isso faceis de testar)."""
from __future__ import annotations

import hashlib
import hmac


def tokens_iguais(esperado: str, recebido: str) -> bool:
    """Comparacao em tempo constante: o tempo de resposta nao revela quantos caracteres batem."""
    return hmac.compare_digest(esperado.encode(), recebido.encode())


def assinatura_valida(segredo: str, corpo_bruto: bytes, assinatura_recebida: str) -> bool:
    """Confere o cabecalho X-Hub-Signature-256 (HMAC-SHA256 do corpo, assinado pela Meta)."""
    esperada = "sha256=" + hmac.new(segredo.encode(), corpo_bruto, hashlib.sha256).hexdigest()
    return tokens_iguais(esperada, assinatura_recebida)
