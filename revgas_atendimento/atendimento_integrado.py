"""Orquestra atendimento de cadastro e pedido de gás, sem alterar nenhum dos dois fluxos originais.

Decide, mensagem a mensagem, qual dos dois serviços deve responder:
1. Se já existe um pedido em andamento para o telefone, o pedido continua.
2. Senão, se já existe um cadastro em andamento, o cadastro continua (comportamento de sempre:
   digitar "gás" no meio do cadastro não rouba a conversa).
3. Senão, se a mensagem pede um pedido de gás (ex.: "gás", "pedido"), o pedido começa.
4. Senão, cai no atendimento de cadastro de sempre (saudação, "cadastro já está completo", etc.).
"""
from __future__ import annotations

from .atendimento import ServicoDeAtendimento
from .atendimento_pedido import ServicoDePedido
from .modelos import Entrada, ErroDeDominio, Resposta, Sessao
from .portas import RepositorioDeSessoes


class ServicoDeAtendimentoIntegrado:
    """Mesma interface pública de ServicoDeAtendimento (método `atender`), por isso dá para
    usar no lugar dele em ProcessadorWhatsApp sem precisar mudar processador.py.

    Só troca informação com ServicoDePedido por meio de `tem_sessao_ativa` (um booleano) e
    `atender` (que devolve a resposta pronta ou None): o estado interno do pedido nunca sai
    de dentro de atendimento_pedido.py."""

    def __init__(
        self,
        atendimento_cadastro: ServicoDeAtendimento,
        sessoes_cadastro: RepositorioDeSessoes[Sessao],
        servico_pedido: ServicoDePedido,
    ) -> None:
        self._atendimento_cadastro = atendimento_cadastro
        self._sessoes_cadastro = sessoes_cadastro
        self._servico_pedido = servico_pedido

    async def atender(self, telefone: str, entrada: Entrada) -> Resposta:
        if await self._servico_pedido.tem_sessao_ativa(telefone):
            resposta = await self._servico_pedido.atender(telefone, entrada)
            if resposta is None:  # não acontece: com sessão ativa o pedido sempre responde
                raise ErroDeDominio("Pedido com sessão ativa não respondeu.")
            return resposta

        if await self._sessoes_cadastro.obter(telefone) is not None:
            return await self._atendimento_cadastro.atender(telefone, entrada)

        resposta_pedido = await self._servico_pedido.atender(telefone, entrada)
        if resposta_pedido is not None:
            return resposta_pedido

        return await self._atendimento_cadastro.atender(telefone, entrada)
