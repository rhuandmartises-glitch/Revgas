"""Formato do WhatsApp Cloud API: leitura do webhook e montagem das mensagens de saída."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .modelos import Entrada, Resposta


@dataclass(frozen=True)
class MensagemRecebida:
    id: str
    telefone: str
    entrada: Entrada


def extrair_mensagem(corpo_webhook: Mapping[str, Any]) -> MensagemRecebida | None:
    """Lê a primeira mensagem do webhook. Retorna None para eventos sem mensagem (ex.: status de leitura).

    Tipos não suportados (imagem, áudio...) viram uma Entrada vazia: o fluxo repete a pergunta.
    """
    try:
        bruta = corpo_webhook["entry"][0]["changes"][0]["value"]["messages"][0]
        tipo = bruta["type"]
        if tipo == "text":
            entrada = Entrada(texto=bruta["text"]["body"])
        elif tipo == "interactive":
            entrada = Entrada(botao_id=bruta["interactive"]["button_reply"]["id"])
        else:
            entrada = Entrada()
        return MensagemRecebida(id=bruta["id"], telefone=bruta["from"], entrada=entrada)
    except (KeyError, IndexError, TypeError):
        return None


def montar_mensagem(telefone: str, resposta: Resposta) -> dict[str, Any]:
    base = {"messaging_product": "whatsapp", "to": telefone}
    if not resposta.botoes:
        return {**base, "type": "text", "text": {"body": resposta.texto}}
    return {
        **base,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": resposta.texto},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": b.id, "title": b.titulo}} for b in resposta.botoes
                ]
            },
        },
    }


def extrair_mensagens(corpo_webhook: Any) -> list[MensagemRecebida]:
    """Recebe todos os eventos de mensagens no payload, sem descartar mensagens em lote."""
    if not isinstance(corpo_webhook, dict):
        return []
    resultado = []
    for entry in corpo_webhook.get('entry', []):
        if not isinstance(entry, dict):
            continue
        for change in entry.get('changes', []):
            if not isinstance(change, dict):
                continue
            value = change.get('value', {})
            if not isinstance(value, dict):
                continue
            for mensagem in value.get('messages', []):
                # Reutiliza o parser histórico sem duplicar as regras de decodificação.
                isolado = {'entry': [{'changes': [{'value': {'messages': [mensagem]}}]}]}
                extraida = extrair_mensagem(isolado)
                if extraida is not None:
                    resultado.append(extraida)
    return resultado
