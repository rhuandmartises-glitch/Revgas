"""Conversa interativa no terminal, pra você testar como se fosse o cliente de verdade.

Como usar, na raiz do projeto: python conversar.py
Digite normalmente, como mandaria uma mensagem de WhatsApp. Pra sair: "sair" (ou Ctrl+C).

Funciona com cadastro e com pedido de gás, com a mesma lógica usada no webhook de verdade —
só que sem precisar de WhatsApp, servidor ou credencial nenhuma.
"""
from __future__ import annotations

import asyncio

from revgas_atendimento.composicao_pedido import montar_atendimento_com_pedido_de_gas
from revgas_atendimento.config import Configuracao
from revgas_atendimento.modelos import Entrada

TELEFONE = "5500999990000"  # fixo nesta sessão: finge ser sempre o mesmo número de celular


async def conversar() -> None:
    # A mesma montagem usada pelo servidor: o que funciona aqui funciona no WhatsApp.
    # Consulta o CEP no ViaCEP de verdade (sem internet, pede o endereço digitado). Nada vai para o disco.
    atendimento = montar_atendimento_com_pedido_de_gas(Configuracao(consultar_cep_online=True))

    print("=== RevGás — conversa de teste ===")
    print("Dica: mande 'oi' pra começar o cadastro, ou 'gás'/'pedido' pra pedir um botijão.")
    print("Pra sair: 'sair'.\n")

    while True:
        try:
            texto = await asyncio.to_thread(input, "Você: ")
        except (EOFError, KeyboardInterrupt):
            print("\nAté mais!")
            break
        if texto.strip().lower() in {"sair", "exit", "quit"}:
            print("Até mais!")
            break
        resposta = await atendimento.atender(TELEFONE, Entrada(texto=texto))
        print(f"Bot: {resposta.texto}\n")


if __name__ == "__main__":
    asyncio.run(conversar())
