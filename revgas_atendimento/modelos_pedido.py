"""Entidades do pedido de botijão de gás. Reaproveita os erros de domínio de modelos.py."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum

from .endereco import ColetaDeEndereco

LIMITE_DE_BOTIJOES_POR_PEDIDO = 6

# Onde o pagamento acontece. Ajuste aqui se a RevGás passar a cobrar antes (ex.: Pix antecipado).
MOMENTO_DO_PAGAMENTO = "na entrega"


class TipoBotijao(str, Enum):
    P13 = "P13"  # 13 kg, uso residencial comum
    P20 = "P20"  # 20 kg
    P45 = "P45"  # 45 kg, uso comercial

    @property
    def descricao(self) -> str:
        return {
            TipoBotijao.P13: "P13 (13 kg)",
            TipoBotijao.P20: "P20 (20 kg)",
            TipoBotijao.P45: "P45 (45 kg)",
        }[self]


class FormaPagamento(str, Enum):
    PIX = "PIX"
    DINHEIRO = "DINHEIRO"
    DEBITO = "DEBITO"
    CREDITO = "CREDITO"

    @property
    def descricao(self) -> str:
        return {
            FormaPagamento.PIX: "Pix",
            FormaPagamento.DINHEIRO: "Dinheiro",
            FormaPagamento.DEBITO: "Cartão de débito",
            FormaPagamento.CREDITO: "Cartão de crédito",
        }[self]


class StatusPedido(str, Enum):
    CONFIRMADO = "CONFIRMADO"
    CANCELADO = "CANCELADO"


class EtapaPedido(str, Enum):
    TIPO_BOTIJAO = "TIPO_BOTIJAO"
    QUANTIDADE = "QUANTIDADE"
    ENDERECO = "ENDERECO"
    PAGAMENTO = "PAGAMENTO"
    TROCO = "TROCO"  # só quando paga em dinheiro
    CONFIRMACAO = "CONFIRMACAO"


def descrever_pagamento(forma: FormaPagamento | None, troco_para: Decimal | None) -> str:
    """ "Dinheiro, na entrega (troco para R$ 100,00)" / "Pix, na entrega"."""
    if forma is None:
        return "não informado"
    texto = f"{forma.descricao}, {MOMENTO_DO_PAGAMENTO}"
    if forma is FormaPagamento.DINHEIRO:
        texto += f" (troco para {formatar_reais(troco_para)})" if troco_para else " (sem troco)"
    return texto


def formatar_reais(valor: Decimal) -> str:
    inteiro, centavos = f"{valor:.2f}".split(".")
    return f"R$ {int(inteiro):,}".replace(",", ".") + f",{centavos}"


@dataclass(frozen=True)
class Pedido:
    """Pedido confirmado pelo cliente, pronto para ser enviado ao ERP/empresa de entrega."""

    telefone: str = field(repr=False)
    tipo_botijao: TipoBotijao
    quantidade: int
    endereco_entrega: str = field(repr=False)
    forma_pagamento: FormaPagamento | None = None
    troco_para: Decimal | None = None
    status: StatusPedido = StatusPedido.CONFIRMADO
    criado_em: datetime | None = None  # com fuso horário (UTC); define o prazo de cancelamento
    id: int | None = None  # preenchido pelo repositório ao salvar

    @property
    def descricao_pagamento(self) -> str:
        return descrever_pagamento(self.forma_pagamento, self.troco_para)


@dataclass(frozen=True)
class SessaoPedido:
    """Progresso de um pedido em andamento. Descartada ao concluir, cancelar ou expirar.

    Tem o mesmo formato (atributo `telefone`) que a classe Sessao de modelos.py, o que permite
    reaproveitar SessoesEmMemoria (de simulacoes.py) para guardar sessões de pedido também.
    """

    telefone: str = field(repr=False)
    etapa: EtapaPedido
    tipo_botijao: TipoBotijao | None = None
    quantidade: int | None = None
    endereco_entrega: str | None = field(default=None, repr=False)
    # Preenchidos a partir do cadastro, quando o cliente já é cadastrado: só aparecem no resumo
    # para ele conferir, sem precisar digitar tudo de novo.
    nome_cliente: str | None = field(default=None, repr=False)
    telefone_contato: str | None = field(default=None, repr=False)
    coleta: ColetaDeEndereco | None = field(default=None, repr=False)  # CEP/número em andamento
    forma_pagamento: FormaPagamento | None = None
    troco_para: Decimal | None = None
