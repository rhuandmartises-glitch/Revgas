"""Caso de uso: conduz a conversa que coleta nome, telefone de contato e endereço (e nada além disso).

Ordem: nome -> telefone (com DDD válido) -> CEP -> número/complemento -> confirmação.
"""
from __future__ import annotations

from dataclasses import replace

from .endereco import PERGUNTA_CEP, ColetaDeEndereco, ColetorDeEndereco, extrair_cep, pergunta_da_coleta
from .interpretacao import Intencao, interpretar_confirmacao
from .modelos import (
    Cadastro,
    DadoInvalidoError,
    Entrada,
    ErroDeDominio,
    Etapa,
    Resposta,
    Sessao,
)
from .portas import ConsultaDeCep, RepositorioDeCadastros, RepositorioDeSessoes
from .intencoes import quer_atualizar_cadastro, quer_cancelar
from .validacao import formatar_telefone, validar_nome, validar_telefone

# A conversa não envia mais botões. Estes ids continuam aceitos só para não quebrar quem
# tocar em um botão de uma mensagem antiga, enviada antes desta versão.
BOTAO_CONFIRMAR = "CONFIRMAR"
BOTAO_CORRIGIR = "CORRIGIR"

_PERGUNTAS = {
    Etapa.NOME: "Qual é o seu nome completo?",
    Etapa.TELEFONE: "Qual é o seu telefone de contato, com DDD? Ex.: 11 98888-7777.",
    Etapa.ENDERECO: f"Agora o endereço. {PERGUNTA_CEP}",
}

# Texto sobre uso dos dados: revise com o jurídico/DPO da RevGás (LGPD) antes de publicar.
_AVISO_DE_USO = (
    "Vou pedir só 3 dados: nome, telefone de contato e endereço, usados apenas para o seu "
    "cadastro. Se quiser parar no meio, é só avisar."
)
MENSAGEM_BOAS_VINDAS = f"Olá! Eu sou o atendimento da RevGás. {_AVISO_DE_USO}\n\n{_PERGUNTAS[Etapa.NOME]}"
MENSAGEM_ATUALIZACAO = f"Vamos atualizar seus dados. {_AVISO_DE_USO}\n\n{_PERGUNTAS[Etapa.NOME]}"
MENSAGEM_CANCELADO = "Tudo bem, parei por aqui e não guardei nenhum dado. Quando quiser, é só mandar uma mensagem."
MENSAGEM_FALHA_TECNICA = "Tive um problema técnico e não consegui concluir agora. Tente de novo em alguns minutos."
MENSAGEM_TROCAR_ENDERECO = (
    "Sem problema! Me manda o CEP do endereço certo (ex.: 01001-000). Se não souber o CEP, me fala "
    "que eu pego o endereço de outro jeito. E se quiser começar tudo de novo, é só dizer."
)


class ServicoDeAtendimento:
    def __init__(
        self,
        cadastros: RepositorioDeCadastros,
        sessoes: RepositorioDeSessoes[Sessao],
        consulta_cep: ConsultaDeCep | None = None,
    ) -> None:
        self._cadastros = cadastros
        self._sessoes = sessoes
        self._coletor = ColetorDeEndereco(consulta_cep)  # sem consulta: pede o endereço digitado após o CEP

    async def atender(self, telefone: str, entrada: Entrada) -> Resposta:
        sessao = await self._sessoes.obter(telefone)
        if sessao is None:
            return await self._iniciar(telefone, entrada)
        # Na etapa do nome, só a frase inteira cancela: há sobrenomes como "Cancela".
        if quer_cancelar(entrada.texto, so_frase_exata=sessao.etapa is Etapa.NOME):
            await self._sessoes.remover(telefone)
            return Resposta(MENSAGEM_CANCELADO)
        if sessao.etapa is Etapa.CONFIRMACAO:
            return await self._tratar_confirmacao(sessao, entrada)
        return await self._tratar_dado(sessao, entrada)

    async def _iniciar(self, telefone: str, entrada: Entrada) -> Resposta:
        cadastro = await self._cadastros.buscar_por_telefone(telefone)
        if cadastro is not None and not quer_atualizar_cadastro(entrada.texto):
            return Resposta(
                f"Olá, {_primeiro_nome(cadastro.nome)}! Seu cadastro já está completo. "
                "Se quiser pedir gás, é só me dizer. E se precisar mudar algum dado, me avisa."
            )
        await self._sessoes.salvar(Sessao(telefone, Etapa.NOME))
        return Resposta(MENSAGEM_ATUALIZACAO if cadastro else MENSAGEM_BOAS_VINDAS)

    async def _tratar_dado(self, sessao: Sessao, entrada: Entrada) -> Resposta:
        if entrada.texto is None:  # botão antigo, imagem, áudio...: repete a pergunta
            return _resposta_da_etapa(sessao)
        if sessao.etapa is Etapa.ENDERECO:
            return await self._tratar_endereco(sessao, entrada.texto)
        try:
            proxima = _avancar(sessao, entrada.texto)
        except DadoInvalidoError as erro:
            return Resposta(str(erro))
        await self._sessoes.salvar(proxima)
        return _resposta_da_etapa(proxima)

    async def _tratar_endereco(self, sessao: Sessao, texto: str) -> Resposta:
        passo = await self._coletor.receber(sessao.coleta, texto)
        if passo.endereco is None:  # ainda falta algo (número, CEP certo...)
            await self._sessoes.salvar(replace(sessao, coleta=passo.coleta))
            return Resposta(passo.mensagem)
        pronta = replace(sessao, endereco=passo.endereco, coleta=None, etapa=Etapa.CONFIRMACAO)
        await self._sessoes.salvar(pronta)
        return Resposta(_resumo(pronta))

    async def _tratar_confirmacao(self, sessao: Sessao, entrada: Entrada) -> Resposta:
        """O cliente só confirma. Se o endereço estiver errado, ele manda o CEP novo direto aqui,
        sem precisar repetir nome e telefone."""
        intencao = interpretar_confirmacao(entrada.texto)
        if entrada.botao_id == BOTAO_CONFIRMAR or intencao is Intencao.CONFIRMAR:
            cadastro = _montar_cadastro(sessao)
            # Se a gravação falhar, a sessão continua: o cliente só precisa confirmar de novo.
            await self._cadastros.salvar(cadastro)
            await self._sessoes.remover(sessao.telefone)
            return Resposta(f"Pronto, {_primeiro_nome(cadastro.nome)}! Seu cadastro foi concluído. Obrigado!")
        if entrada.botao_id == BOTAO_CORRIGIR or intencao is Intencao.REFAZER:
            await self._sessoes.salvar(Sessao(sessao.telefone, Etapa.NOME))
            return Resposta(f"Sem problema, vamos refazer. {_PERGUNTAS[Etapa.NOME]}")
        if intencao in (Intencao.NOVO_ENDERECO, Intencao.NEGAR):
            trocando = replace(sessao, etapa=Etapa.ENDERECO, coleta=ColetaDeEndereco())
            if extrair_cep(entrada.texto):  # já mandou o CEP novo: consulta direto
                return await self._tratar_endereco(trocando, entrada.texto or "")
            await self._sessoes.salvar(trocando)
            return Resposta(MENSAGEM_TROCAR_ENDERECO)
        return _resposta_da_etapa(sessao)


def _avancar(sessao: Sessao, texto: str) -> Sessao:
    match sessao.etapa:
        case Etapa.NOME:
            return replace(sessao, nome=validar_nome(texto), etapa=Etapa.TELEFONE)
        case Etapa.TELEFONE:
            return replace(
                sessao, telefone_contato=validar_telefone(texto), etapa=Etapa.ENDERECO, coleta=ColetaDeEndereco()
            )
    raise ValueError(f"A etapa {sessao.etapa} não recebe texto livre.")


def _resposta_da_etapa(sessao: Sessao) -> Resposta:
    if sessao.etapa is Etapa.CONFIRMACAO:
        return Resposta(_resumo(sessao))
    if sessao.etapa is Etapa.ENDERECO and sessao.coleta and sessao.coleta.achado:
        return Resposta(pergunta_da_coleta(sessao.coleta))
    return Resposta(_PERGUNTAS[sessao.etapa])


def _resumo(sessao: Sessao) -> str:
    return (
        f"Confere seus dados?\nNome: {sessao.nome}\nTelefone: {formatar_telefone(sessao.telefone_contato or '')}\n"
        f"Endereço: {sessao.endereco}\n\n"
        "Está tudo certo? Se o endereço mudou, me manda o CEP novo que eu atualizo."
    )


def _montar_cadastro(sessao: Sessao) -> Cadastro:
    if sessao.nome is None or sessao.telefone_contato is None or sessao.endereco is None:
        raise ErroDeDominio("Sessão incompleta ao confirmar o cadastro.")
    return Cadastro(sessao.telefone, sessao.nome, sessao.telefone_contato, sessao.endereco)


def _primeiro_nome(nome: str) -> str:
    return nome.split()[0]
