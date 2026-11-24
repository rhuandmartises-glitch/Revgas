"""Demonstração local: python -m revgas_atendimento (sem WhatsApp, ERP ou chave de API)."""
from __future__ import annotations

import asyncio
from typing import Any

from .atendimento import BOTAO_CONFIRMAR, ServicoDeAtendimento
from .config import Configuracao
from .processador import ProcessadorWhatsApp
from .simulacoes import (
    CadastrosEmMemoria,
    CepsEmMemoria,
    SessoesEmMemoria,
    WhatsAppEmMemoria,
    evento_de_botao,
    evento_de_texto,
)

TELEFONE = "5511999990000"


async def executar_demonstracao() -> None:
    configuracao = Configuracao(segredo_app_whatsapp="demo", token_verificacao_whatsapp="demo")
    cadastros = CadastrosEmMemoria()
    # CEP sem internet (CepsEmMemoria): a demo funciona offline. O servidor usa o ViaCEP.
    atendimento = ServicoDeAtendimento(cadastros, SessoesEmMemoria(configuracao.ttl_sessao_s), CepsEmMemoria())
    processador = ProcessadorWhatsApp(atendimento, WhatsAppEmMemoria())

    falas = ["oi", "  maria   da silva ", "(20) 99999-8888", "11 99999-8888", "01001-000", "120 apto 3"]
    roteiro: list[tuple[str, dict[str, Any]]] = [(fala, evento_de_texto(TELEFONE, fala)) for fala in falas]
    roteiro.append(("[toca em Confirmar]", evento_de_botao(TELEFONE, BOTAO_CONFIRMAR)))
    for fala, evento in roteiro:
        print(f"\nCliente: {fala}")
        await processador.processar(evento)

    cadastro = await cadastros.buscar_por_telefone(TELEFONE)
    if cadastro is None:
        raise RuntimeError("O cadastro não foi salvo.")
    print("\n== Salvo no cadastro ==")
    print(f"Nome: {cadastro.nome}\nTelefone de contato: {cadastro.telefone_contato}\nEndereço: {cadastro.endereco}")


if __name__ == "__main__":
    asyncio.run(executar_demonstracao())
