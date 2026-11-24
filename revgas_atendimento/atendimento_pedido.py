"""Caso de uso: conduz a conversa que faz um pedido de botijão de gás.

Ordem: botijão -> quantidade -> endereço (pelo CEP; pulado se o cliente tem cadastro) ->
forma de pagamento -> troco (só em dinheiro) -> confirmação.

Conversa só em texto livre, sem botões: o cliente responde como responderia a um atendente, e o
serviço entende as variações mais comuns (abreviações, sinônimos, com ou sem acento).

Depois de confirmado, o pedido pode ser cancelado pelo próprio cliente (mensagem CANCELAR) dentro
do prazo de cancelamento. Passado o prazo, o bot orienta a falar com a loja.

O ponto de entrada público é `ServicoDePedido.atender`, com a mesma assinatura de
`ServicoDeAtendimento.atender`, exceto que devolve None quando a mensagem não tem nada a ver
com pedido de gás — é esse None que permite a quem orquestra os dois fluxos (veja
atendimento_integrado.py) decidir cair de volta no atendimento de cadastro de sempre.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from .endereco import PERGUNTA_CEP, ColetaDeEndereco, ColetorDeEndereco, extrair_cep, pergunta_da_coleta
from .interpretacao import Intencao, interpretar_confirmacao
from .modelos import Cadastro, DadoInvalidoError, Entrada, ErroDeDominio, Resposta
from .modelos_pedido import (
    EtapaPedido,
    FormaPagamento,
    Pedido,
    SessaoPedido,
    StatusPedido,
    descrever_pagamento,
)
from .portas import ConsultaDeCep, RepositorioDeCadastros, RepositorioDeSessoes
from .portas_pedido import RepositorioDePedidos
from .texto import comando, palavras
from .validacao import formatar_telefone
from .validacao_pedido import (
    PERGUNTA_PAGAMENTO,
    PERGUNTA_TROCO,
    detectar_forma_pagamento,
    validar_forma_pagamento,
    validar_quantidade,
    validar_tipo_botijao,
    validar_troco,
)

PRAZO_CANCELAMENTO_PADRAO = timedelta(minutes=5)

_PALAVRAS_CANCELAR = frozenset({"cancelar", "cancela", "cancele", "cancelo", "cancelamento"})
_COMANDOS_DESISTIR = frozenset({"deixa pra la", "deixa para la", "esquece"})  # só no meio do pedido
_PALAVRAS_GATILHO = frozenset({"gas", "pedido"})  # comparadas já sem acento (ver texto.palavras)

MENSAGEM_PERGUNTA_TIPO = (
    "Qual botijão você precisa: P13 (13kg, o mais comum em casa), P20 (20kg) ou "
    "P45 (45kg, uso comercial)?"
)
MENSAGEM_PERGUNTA_QUANTIDADE = "Perfeito! E quantos botijões desse você vai querer?"
MENSAGEM_PERGUNTA_ENDERECO = f"Combinado! Agora o endereço de entrega. {PERGUNTA_CEP}"
MENSAGEM_TROCAR_ENDERECO = (
    "Sem problema! Me manda o CEP do endereço certo da entrega (ex.: 01001-000). "
    "Se não souber, responda NÃO SEI. Se quiser refazer o pedido do começo, digite REFAZER."
)
MENSAGEM_CANCELADO = "Sem problema, cancelei seu pedido. Quando quiser pedir gás de novo, é só me chamar."
MENSAGEM_SEM_PEDIDO_PARA_CANCELAR = (
    "Não encontrei nenhum pedido seu para cancelar. Se quiser pedir gás, é só mandar GÁS."
)


def eh_pedido_de_gas(entrada: Entrada) -> bool:
    """Reconhece a intenção de iniciar um pedido (ex.: "gás", "quero pedir gás", "novo pedido").

    Usado tanto por ServicoDePedido quanto por quem orquestra os fluxos (atendimento_integrado.py).
    """
    return bool(set(palavras(entrada.texto)) & _PALAVRAS_GATILHO)


def eh_cancelamento(entrada: Entrada) -> bool:
    """ "cancelar", "cancela meu pedido", "quero cancelar o pedido"."""
    return bool(set(palavras(entrada.texto)) & _PALAVRAS_CANCELAR)


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


class ServicoDePedido:
    """Só expõe duas operações para quem está fora deste módulo: `atender` (a conversa em si) e
    `tem_sessao_ativa` (uma checagem booleana, usada por quem decide entre cadastro e pedido).
    O estado da sessão (`SessaoPedido`) nunca sai daqui — só o texto da resposta."""

    def __init__(
        self,
        pedidos: RepositorioDePedidos,
        sessoes: RepositorioDeSessoes[SessaoPedido],
        cadastros: RepositorioDeCadastros | None = None,
        consulta_cep: ConsultaDeCep | None = None,
        prazo_cancelamento: timedelta = PRAZO_CANCELAMENTO_PADRAO,
        relogio: Callable[[], datetime] = _agora_utc,
    ) -> None:
        self._pedidos = pedidos
        self._sessoes = sessoes  # guarda SessaoPedido; reaproveita RepositorioDeSessoes/SessoesEmMemoria
        self._cadastros = cadastros  # opcional: sem ele, o pedido sempre pergunta o endereço
        self._coletor = ColetorDeEndereco(consulta_cep)  # sem consulta: pede o endereço digitado
        self._prazo_cancelamento = prazo_cancelamento  # zero: o cliente não cancela pelo WhatsApp
        self._relogio = relogio  # injetável nos testes; sempre com fuso horário

    async def tem_sessao_ativa(self, telefone: str) -> bool:
        return await self._sessoes.obter(telefone) is not None

    async def atender(self, telefone: str, entrada: Entrada) -> Resposta | None:
        """Devolve None quando a mensagem não é um pedido de gás em andamento nem um gatilho
        para começar um: quem chamou deve então tratar a mensagem como quiser (ex.: cadastro)."""
        sessao = await self._sessoes.obter(telefone)
        if sessao is not None:
            return await self._continuar(telefone, entrada, sessao)
        if eh_cancelamento(entrada):  # antes do gatilho: "cancelar pedido" tem a palavra "pedido"
            return await self._cancelar_confirmado(telefone)
        if eh_pedido_de_gas(entrada):
            return await self._iniciar(telefone)
        return None

    async def _iniciar(self, telefone: str) -> Resposta:
        await self._sessoes.salvar(SessaoPedido(telefone, EtapaPedido.TIPO_BOTIJAO))
        cadastro = await self._buscar_cadastro(telefone)
        if cadastro is not None:  # cliente que volta: mostra que foi reconhecido
            return Resposta(
                f"Oi de novo, {cadastro.nome.split()[0]}! Já tenho seu cadastro, então é rapidinho. "
                f"{MENSAGEM_PERGUNTA_TIPO}"
            )
        return Resposta(f"Opa, vamos pedir seu gás! {MENSAGEM_PERGUNTA_TIPO}")

    async def _continuar(self, telefone: str, entrada: Entrada, sessao: SessaoPedido) -> Resposta:
        if eh_cancelamento(entrada) or comando(entrada.texto) in _COMANDOS_DESISTIR:
            await self._sessoes.remover(telefone)
            return Resposta(MENSAGEM_CANCELADO)
        if sessao.etapa is EtapaPedido.CONFIRMACAO:
            return await self._tratar_confirmacao(sessao, entrada)
        return await self._tratar_dado(sessao, entrada)

    # ── Etapas antes da confirmação ─────────────────────────────────────────
    async def _tratar_dado(self, sessao: SessaoPedido, entrada: Entrada) -> Resposta:
        if entrada.texto is None:  # botão, imagem, áudio...: repete a pergunta da etapa atual
            return _resposta_da_etapa(sessao)
        if sessao.etapa is EtapaPedido.ENDERECO:
            return await self._tratar_endereco(sessao, entrada.texto)
        try:
            proxima = await self._avancar(sessao, entrada.texto)
        except DadoInvalidoError as erro:
            return Resposta(str(erro))
        await self._sessoes.salvar(proxima)
        if proxima.etapa is EtapaPedido.ENDERECO:
            return Resposta(MENSAGEM_PERGUNTA_ENDERECO)
        if proxima.etapa is EtapaPedido.PAGAMENTO and sessao.etapa is EtapaPedido.QUANTIDADE:
            # Cliente cadastrado: pulou o endereço; mostra onde vai entregar antes de perguntar o pagamento.
            return Resposta(f"Anotado! Vou entregar em: {proxima.endereco_entrega}.\n\n{PERGUNTA_PAGAMENTO}")
        return _resposta_da_etapa(proxima)

    async def _avancar(self, sessao: SessaoPedido, texto: str) -> SessaoPedido:
        match sessao.etapa:
            case EtapaPedido.TIPO_BOTIJAO:
                return replace(sessao, tipo_botijao=validar_tipo_botijao(texto), etapa=EtapaPedido.QUANTIDADE)
            case EtapaPedido.QUANTIDADE:
                return await self._depois_da_quantidade(replace(sessao, quantidade=validar_quantidade(texto)))
            case EtapaPedido.PAGAMENTO:
                return _com_pagamento(sessao, validar_forma_pagamento(texto))
            case EtapaPedido.TROCO:
                return replace(sessao, troco_para=validar_troco(texto), etapa=EtapaPedido.CONFIRMACAO)
        raise ValueError(f"A etapa {sessao.etapa} não recebe texto livre.")

    async def _tratar_endereco(self, sessao: SessaoPedido, texto: str) -> Resposta:
        passo = await self._coletor.receber(sessao.coleta, texto)
        if passo.endereco is None:  # ainda falta algo (número, CEP certo...)
            await self._sessoes.salvar(replace(sessao, coleta=passo.coleta))
            return Resposta(passo.mensagem)
        # Troca de endereço na confirmação volta para a confirmação; no primeiro pedido, segue para o pagamento.
        proxima_etapa = EtapaPedido.CONFIRMACAO if sessao.forma_pagamento else EtapaPedido.PAGAMENTO
        pronta = replace(sessao, endereco_entrega=passo.endereco, coleta=None, etapa=proxima_etapa)
        await self._sessoes.salvar(pronta)
        return _resposta_da_etapa(pronta)

    async def _depois_da_quantidade(self, sessao: SessaoPedido) -> SessaoPedido:
        """Cliente cadastrado pula o endereço e vai para o pagamento, com os dados do cadastro."""
        cadastro = await self._buscar_cadastro(sessao.telefone)
        if cadastro is None:
            return replace(sessao, etapa=EtapaPedido.ENDERECO, coleta=ColetaDeEndereco())
        return replace(
            sessao,
            endereco_entrega=cadastro.endereco,
            nome_cliente=cadastro.nome,
            telefone_contato=cadastro.telefone_contato,
            etapa=EtapaPedido.PAGAMENTO,
        )

    # ── Confirmação ─────────────────────────────────────────────────────────
    async def _tratar_confirmacao(self, sessao: SessaoPedido, entrada: Entrada) -> Resposta:
        # Trocar a forma de pagamento aqui mesmo: "prefiro pagar no pix".
        nova_forma = detectar_forma_pagamento(entrada.texto)
        if nova_forma is not None and nova_forma is not sessao.forma_pagamento and not extrair_cep(entrada.texto):
            atualizada = _com_pagamento(sessao, nova_forma)
            await self._sessoes.salvar(atualizada)
            if atualizada.etapa is EtapaPedido.TROCO:
                return Resposta(f"Troquei para dinheiro. {PERGUNTA_TROCO}")
            return Resposta(f"Troquei a forma de pagamento! {_resumo(atualizada)}")

        intencao = interpretar_confirmacao(entrada.texto)
        if intencao is Intencao.CONFIRMAR:
            return await self._confirmar(sessao)
        if intencao is Intencao.REFAZER:
            await self._sessoes.salvar(SessaoPedido(sessao.telefone, EtapaPedido.TIPO_BOTIJAO))
            return Resposta(f"Sem problema, vamos refazer. {MENSAGEM_PERGUNTA_TIPO}")
        if intencao in (Intencao.NOVO_ENDERECO, Intencao.NEGAR):
            trocando = replace(sessao, etapa=EtapaPedido.ENDERECO, coleta=ColetaDeEndereco())
            if extrair_cep(entrada.texto):  # já mandou o CEP novo: consulta direto
                return await self._tratar_endereco(trocando, entrada.texto or "")
            await self._sessoes.salvar(trocando)
            return Resposta(MENSAGEM_TROCAR_ENDERECO)
        return _resposta_da_etapa(sessao)

    async def _confirmar(self, sessao: SessaoPedido) -> Resposta:
        # Se a gravação falhar, a sessão continua: o cliente só precisa confirmar de novo.
        pedido = await self._pedidos.salvar(_montar_pedido(sessao, self._relogio()))
        await self._sessoes.remover(sessao.telefone)
        aviso_cancelamento = (
            f" Se precisar cancelar, mande CANCELAR em até {_minutos(self._prazo_cancelamento)}."
            if self._prazo_cancelamento > timedelta(0)
            else ""
        )
        return Resposta(
            f"Prontinho! Seu pedido de {pedido.quantidade}x {pedido.tipo_botijao.descricao} está "
            f"confirmado, entrega em {pedido.endereco_entrega}. Pagamento: {pedido.descricao_pagamento}."
            f"{aviso_cancelamento} Obrigado por comprar com a RevGás!"
        )

    # ── Cancelamento depois de confirmado ───────────────────────────────────
    async def _cancelar_confirmado(self, telefone: str) -> Resposta:
        pedido = await self._pedidos.ultimo_por_telefone(telefone)
        if pedido is None or pedido.status is not StatusPedido.CONFIRMADO or pedido.criado_em is None:
            return Resposta(MENSAGEM_SEM_PEDIDO_PARA_CANCELAR)
        decorrido = self._relogio() - pedido.criado_em
        if decorrido > self._prazo_cancelamento:
            prazo = (
                f"o prazo para cancelar por aqui é de {_minutos(self._prazo_cancelamento)}"
                if self._prazo_cancelamento > timedelta(0)
                else "o cancelamento não é feito por aqui"
            )
            return Resposta(
                f"Seu último pedido foi confirmado há {_minutos(decorrido)}, e {prazo}: ele já pode "
                "estar a caminho. Para cancelar agora, fale com a loja RevGás."
            )
        if pedido.id is None or not await self._pedidos.cancelar(pedido.id):
            return Resposta(MENSAGEM_SEM_PEDIDO_PARA_CANCELAR)  # cancelado em paralelo, por exemplo
        return Resposta(
            f"Pedido cancelado: {pedido.quantidade}x {pedido.tipo_botijao.descricao}, que ia para "
            f"{pedido.endereco_entrega}. Se quiser pedir de novo, é só mandar GÁS."
        )

    async def _buscar_cadastro(self, telefone: str) -> Cadastro | None:
        return await self._cadastros.buscar_por_telefone(telefone) if self._cadastros else None


def _com_pagamento(sessao: SessaoPedido, forma: FormaPagamento) -> SessaoPedido:
    """Dinheiro pergunta o troco; as outras formas vão direto para a confirmação."""
    if forma is FormaPagamento.DINHEIRO:
        return replace(sessao, forma_pagamento=forma, troco_para=None, etapa=EtapaPedido.TROCO)
    return replace(sessao, forma_pagamento=forma, troco_para=None, etapa=EtapaPedido.CONFIRMACAO)


def _minutos(intervalo: timedelta) -> str:
    minutos = int(intervalo.total_seconds() // 60)
    if minutos < 1:
        return "menos de 1 minuto"
    return "1 minuto" if minutos == 1 else f"{minutos} minutos"


def _resposta_da_etapa(sessao: SessaoPedido) -> Resposta:
    match sessao.etapa:
        case EtapaPedido.QUANTIDADE:
            return Resposta(MENSAGEM_PERGUNTA_QUANTIDADE)
        case EtapaPedido.ENDERECO:
            return Resposta(pergunta_da_coleta(sessao.coleta))
        case EtapaPedido.PAGAMENTO:
            return Resposta(PERGUNTA_PAGAMENTO)
        case EtapaPedido.TROCO:
            return Resposta(PERGUNTA_TROCO)
        case EtapaPedido.CONFIRMACAO:
            return Resposta(_resumo(sessao))
    return Resposta(MENSAGEM_PERGUNTA_TIPO)


def _resumo(sessao: SessaoPedido) -> str:
    linhas = ["Só pra confirmar seu pedido:", f"{sessao.quantidade}x {sessao.tipo_botijao.descricao}"]
    if sessao.nome_cliente:
        linhas.append(f"Nome: {sessao.nome_cliente}")
    if sessao.telefone_contato:
        linhas.append(f"Telefone: {formatar_telefone(sessao.telefone_contato)}")
    linhas.append(f"Endereço de entrega: {sessao.endereco_entrega}")
    linhas.append(f"Pagamento: {descrever_pagamento(sessao.forma_pagamento, sessao.troco_para)}")
    return (
        "\n".join(linhas)
        + "\n\nTá tudo certo? É só responder SIM. Se o endereço mudou, me manda o CEP novo; "
        "para trocar o pagamento, é só dizer a forma (ex.: Pix)."
    )


def _montar_pedido(sessao: SessaoPedido, agora: datetime) -> Pedido:
    if (
        sessao.tipo_botijao is None
        or sessao.quantidade is None
        or sessao.endereco_entrega is None
        or sessao.forma_pagamento is None
    ):
        raise ErroDeDominio("Sessão de pedido incompleta ao confirmar.")
    return Pedido(
        sessao.telefone,
        sessao.tipo_botijao,
        sessao.quantidade,
        sessao.endereco_entrega,
        forma_pagamento=sessao.forma_pagamento,
        troco_para=sessao.troco_para,
        criado_em=agora,
    )
