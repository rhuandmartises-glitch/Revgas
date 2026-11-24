"""Funções de segurança do webhook, independentes de framework (por isso fáceis de testar)."""
from __future__ import annotations

import hashlib
import hmac
import logging
import re

# Parâmetros de URL com segredo. A Meta manda o token de verificação na URL do GET do webhook,
# e o log de acesso do uvicorn grava a URL inteira.
_PARAMETRO_SECRETO = re.compile(r"((?:hub[._]verify_token)=)[^&\s\"]*", re.IGNORECASE)


def tokens_iguais(esperado: str, recebido: str) -> bool:
    """Comparação em tempo constante: o tempo de resposta não revela quantos caracteres batem."""
    return hmac.compare_digest(esperado.encode(), recebido.encode())


def assinatura_valida(segredo: str, corpo_bruto: bytes, assinatura_recebida: str) -> bool:
    """Confere o cabeçalho X-Hub-Signature-256 (HMAC-SHA256 do corpo, assinado pela Meta)."""
    esperada = "sha256=" + hmac.new(segredo.encode(), corpo_bruto, hashlib.sha256).hexdigest()
    return tokens_iguais(esperada, assinatura_recebida)


def ocultar_segredos(texto: str) -> str:
    return _PARAMETRO_SECRETO.sub(r"\1***", texto)


class FiltroDeSegredosNoLog(logging.Filter):
    """Troca o valor de hub.verify_token por *** antes de a linha de log ser gravada."""

    def filter(self, registro: logging.LogRecord) -> bool:
        if isinstance(registro.msg, str):
            registro.msg = ocultar_segredos(registro.msg)
        if isinstance(registro.args, tuple):
            registro.args = tuple(ocultar_segredos(a) if isinstance(a, str) else a for a in registro.args)
        return True


def proteger_logs_de_acesso(nome_do_logger: str = "uvicorn.access") -> None:
    """Instala o filtro uma vez só, mesmo se a aplicação for criada várias vezes (ex.: testes)."""
    alvo = logging.getLogger(nome_do_logger)
    if not any(isinstance(filtro, FiltroDeSegredosNoLog) for filtro in alvo.filters):
        alvo.addFilter(FiltroDeSegredosNoLog())
