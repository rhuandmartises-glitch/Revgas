"""Raiz de composição do atendimento completo: cadastro + pedido de gás."""
from __future__ import annotations

from datetime import timedelta

from .atendimento import ServicoDeAtendimento
from .atendimento_integrado import ServicoDeAtendimentoIntegrado
from .atendimento_pedido import ServicoDePedido
from .composicao import montar_banco, montar_cadastros, montar_consulta_cep, montar_servico_de_webhook
from .config import Configuracao
from .persistencia_sqlite import PedidosSqlite
from .simulacoes import SessoesEmMemoria
from .simulacoes_pedido import PedidosEmMemoria
from .webhook import ServicoDeWebhook


def montar_atendimento_com_pedido_de_gas(configuracao: Configuracao) -> ServicoDeAtendimentoIntegrado:
    """Cadastro + pedido de gás, sem nada de WhatsApp: usado pelo webhook e pela rota do n8n.

    Com `caminho_banco`, cadastros e pedidos ficam no SQLite: quem já se cadastrou é lembrado pelo
    número do WhatsApp em qualquer pedido futuro, mesmo depois de reiniciar o servidor.
    Cadastro e pedido usam cada um a sua própria instância de sessão, então não se misturam
    mesmo compartilhando o mesmo telefone como chave.
    """
    banco = montar_banco(configuracao)
    cadastros = montar_cadastros(banco)  # o mesmo repositório nos dois fluxos: o pedido lê o cadastro
    pedidos = PedidosSqlite(banco) if banco else PedidosEmMemoria()

    consulta_cep = montar_consulta_cep(configuracao)  # a mesma consulta para cadastro e pedido

    sessoes_cadastro = SessoesEmMemoria(configuracao.ttl_sessao_s)
    atendimento_cadastro = ServicoDeAtendimento(cadastros, sessoes_cadastro, consulta_cep)

    sessoes_pedido = SessoesEmMemoria(configuracao.ttl_sessao_s)
    servico_pedido = ServicoDePedido(
        pedidos,
        sessoes_pedido,
        cadastros,
        consulta_cep,
        prazo_cancelamento=timedelta(minutes=configuracao.prazo_cancelamento_min),
    )

    return ServicoDeAtendimentoIntegrado(atendimento_cadastro, sessoes_cadastro, servico_pedido)


def montar_servico_de_webhook_com_pedido_de_gas(
    configuracao: Configuracao, atendimento: ServicoDeAtendimentoIntegrado | None = None
) -> ServicoDeWebhook:
    return montar_servico_de_webhook(
        configuracao, atendimento or montar_atendimento_com_pedido_de_gas(configuracao)
    )
