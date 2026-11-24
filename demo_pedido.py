"""Demonstração local do pedido de gás, já integrado ao cadastro (sem WhatsApp, ERP ou chave de API).

Como usar, na raiz do projeto: python demo_pedido.py
"""
from __future__ import annotations

import asyncio

from revgas_atendimento.atendimento import ServicoDeAtendimento
from revgas_atendimento.atendimento_integrado import ServicoDeAtendimentoIntegrado
from revgas_atendimento.atendimento_pedido import ServicoDePedido
from revgas_atendimento.config import Configuracao
from revgas_atendimento.processador import ProcessadorWhatsApp
from revgas_atendimento.simulacoes import (
    CadastrosEmMemoria,
    CepsEmMemoria,
    SessoesEmMemoria,
    WhatsAppEmMemoria,
    evento_de_texto,
)
from revgas_atendimento.simulacoes_pedido import PedidosEmMemoria

TELEFONE = "5511999990000"


async def executar_demonstracao() -> None:
    configuracao = Configuracao(segredo_app_whatsapp="demo", token_verificacao_whatsapp="demo")

    ceps = CepsEmMemoria()  # CEP sem internet: a demo funciona offline (o servidor usa o ViaCEP)
    sessoes_cadastro = SessoesEmMemoria(configuracao.ttl_sessao_s)
    cadastros = CadastrosEmMemoria()
    atendimento_cadastro = ServicoDeAtendimento(cadastros, sessoes_cadastro, ceps)

    pedidos = PedidosEmMemoria()
    servico_pedido = ServicoDePedido(pedidos, SessoesEmMemoria(configuracao.ttl_sessao_s), cadastros, ceps)

    atendimento = ServicoDeAtendimentoIntegrado(atendimento_cadastro, sessoes_cadastro, servico_pedido)
    processador = ProcessadorWhatsApp(atendimento, WhatsAppEmMemoria())

    roteiro = [
        # Primeiro o cadastro...
        "oi",
        "Maria da Silva",
        "(11) 98888-7777",
        "01001-000",  # CEP: o bot acha a rua e só pergunta o número
        "120",
        "sim",
        # ...depois o pedido: como já tem cadastro, não pergunta o endereço; pergunta o pagamento.
        "quero pedir gás",
        "um botijão P13, o pequeno mesmo",
        "2",
        "dinheiro",
        "troco para 100",
        # Na confirmação, muda o endereço pelo CEP e depois troca o pagamento para Pix.
        "01310-100",
        "1000 apto 52",
        "prefiro pagar no pix",
        "sim, pode confirmar",
        # Dentro do prazo de cancelamento (5 min), desiste.
        "cancelar",
    ]
    for fala in roteiro:
        print(f"\nCliente: {fala}")
        await processador.processar(evento_de_texto(TELEFONE, fala))

    pedidos_do_cliente = await pedidos.listar_por_telefone(TELEFONE)
    if not pedidos_do_cliente:
        raise RuntimeError("O pedido não foi salvo.")
    print("\n== Pedidos registrados ==")
    for pedido in pedidos_do_cliente:
        print(
            f"#{pedido.id} {pedido.quantidade}x {pedido.tipo_botijao.descricao} -> {pedido.endereco_entrega}"
            f" | {pedido.descricao_pagamento} | {pedido.status.value}"
        )


if __name__ == "__main__":
    asyncio.run(executar_demonstracao())
