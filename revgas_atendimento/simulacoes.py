"""Adaptadores em memória: permitem rodar a demo e os testes sem sistemas externos."""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Mapping
from typing import Any

from .modelos import Cadastro, Sessao


class CadastrosEmMemoria:
    """Em produção: chamadas ao ERP RevGás (POST/PUT de cliente)."""

    def __init__(self) -> None:
        self._por_telefone: dict[str, Cadastro] = {}

    async def buscar_por_telefone(self, telefone: str) -> Cadastro | None:
        return self._por_telefone.get(telefone)

    async def salvar(self, cadastro: Cadastro) -> None:
        self._por_telefone[cadastro.telefone] = cadastro


class SessoesEmMemoria:
    """Em produção: Redis com SETEX. Aqui a validade é renovada a cada gravação."""

    def __init__(self, ttl_s: float, relogio: Callable[[], float] = time.monotonic) -> None:
        self._ttl_s = ttl_s
        self._relogio = relogio
        self._dados: dict[str, tuple[Sessao, float]] = {}

    async def obter(self, telefone: str) -> Sessao | None:
        self._descartar_expiradas()
        item = self._dados.get(telefone)
        return item[0] if item else None

    async def salvar(self, sessao: Sessao) -> None:
        self._descartar_expiradas()
        self._dados[sessao.telefone] = (sessao, self._relogio() + self._ttl_s)

    async def remover(self, telefone: str) -> None:
        self._dados.pop(telefone, None)

    def _descartar_expiradas(self) -> None:
        agora = self._relogio()
        vencidas = [telefone for telefone, (_, validade) in self._dados.items() if validade <= agora]
        for telefone in vencidas:
            del self._dados[telefone]


class WhatsAppEmMemoria:
    """Guarda (e opcionalmente imprime) o que seria enviado. Não fala com o WhatsApp de verdade."""

    def __init__(self, imprimir: bool = True) -> None:
        self._imprimir = imprimir
        self.enviadas: list[tuple[str, Mapping[str, Any]]] = []

    async def enviar(self, telefone: str, mensagem: Mapping[str, Any]) -> None:
        self.enviadas.append((telefone, mensagem))
        if self._imprimir:
            print(f"Bot: {_resumir(mensagem)}")


def _resumir(mensagem: Mapping[str, Any]) -> str:
    if mensagem["type"] == "text":
        return str(mensagem["text"]["body"]).replace("\n", "\n     ")
    interativo = mensagem["interactive"]
    botoes = " ".join(f"[{b['reply']['title']}]" for b in interativo["action"]["buttons"])
    return f"{interativo['body']['text']}".replace("\n", "\n     ") + f"\n     {botoes}"


# ── Payloads de webhook para simulação ──────────────────────────────────────
def _evento(telefone: str, conteudo: dict[str, Any]) -> dict[str, Any]:
    mensagem = {"id": f"wamid.{uuid.uuid4().hex}", "from": telefone, **conteudo}
    return {"entry": [{"changes": [{"value": {"messages": [mensagem]}}]}]}


def evento_de_texto(telefone: str, texto: str) -> dict[str, Any]:
    return _evento(telefone, {"type": "text", "text": {"body": texto}})


def evento_de_botao(telefone: str, botao_id: str) -> dict[str, Any]:
    return _evento(telefone, {"type": "interactive", "interactive": {"button_reply": {"id": botao_id}}})
