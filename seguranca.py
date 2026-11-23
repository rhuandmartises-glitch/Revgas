"""Funções de segurança do webhook, independentes de framework (por isso fáceis de testar)."""
from __future__ import annotations

import hashlib
import hmac


def tokens_iguais(esperado: str, recebido: str) -> bool:
    """Comparação em tempo constante: o tempo de resposta não revela quantos caracteres batem."""
    return hmac.compare_digest(esperado.encode(), recebido.encode())


def assinatura_valida(segredo: str, corpo_bruto: bytes, assinatura_recebida: str) -> bool:
    """Confere o cabeçalho X-Hub-Signature-256 (HMAC-SHA256 do corpo, assinado pela Meta)."""
    esperada = "sha256=" + hmac.new(segredo.encode(), corpo_bruto, hashlib.sha256).hexdigest()
    return tokens_iguais(esperada, assinatura_recebida)
