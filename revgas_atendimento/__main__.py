"""Demonstração local: python -m revgas_atendimento (sem WhatsApp, ERP ou chave de API)."""
from __future__ import annotations

import asyncio
from typing import Any

from .atendimento import BOTAO_CONFIRMAR, ServicoDeAtendimento
from .config import Configuracao
from .processador import ProcessadorWhatsApp
from .simulacoes import (
    CadastrosEmMemoria,
    SessoesEmMemoria,
    WhatsAppEmMemoria,
    evento_de_botao,
    evento_de_texto,
)

TELEFONE = "5511999990000"


async def executar_demonstracao() -> None:
    configuracao = Configuracao(segredo_app_whatsapp="demo", token_verificacao_whatsapp="demo")
    cadastros = CadastrosEmMemoria()
    atendimento = ServicoDeAtendimento(cadastros, SessoesEmMemoria(configuracao.ttl_sessao_s))
    processador = ProcessadorWhatsApp(atendimento, WhatsAppEmMemoria())

    roteiro: list[tuple[str, dict[str, Any]]] = [
        ("oi", evento_de_texto(TELEFONE, "oi")),
        ("  maria   da silva ", evento_de_texto(TELEFONE, "  maria   da silva ")),
        ("maria@@email", evento_de_texto(TELEFONE, "maria@@email")),
        ("Maria@Email.com", evento_de_texto(TELEFONE, "Maria@Email.com")),
        ("Rua das Flores, 120 - Centro", evento_de_texto(TELEFONE, "Rua das Flores, 120 - Centro")),
        ("[toca em Confirmar]", evento_de_botao(TELEFONE, BOTAO_CONFIRMAR)),
    ]
    for fala, evento in roteiro:
        print(f"\nCliente: {fala}")
        await processador.processar(evento)

    cadastro = await cadastros.buscar_por_telefone(TELEFONE)
    if cadastro is None:
        raise RuntimeError("O cadastro não foi salvo.")
    print("\n== Salvo no cadastro ==")
    print(f"Nome: {cadastro.nome}\nE-mail: {cadastro.email}\nEndereço: {cadastro.endereco}")


if __name__ == "__main__":
    asyncio.run(executar_demonstracao())
