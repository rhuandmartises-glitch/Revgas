"""Caso de uso: conduz a conversa que coleta nome, e-mail e endereço (e nada além disso)."""
from __future__ import annotations

from dataclasses import replace

from .modelos import (
    Botao,
    Cadastro,
    DadoInvalidoError,
    Entrada,
    ErroDeDominio,
    Etapa,
    Resposta,
    Sessao,
)
from .portas import RepositorioDeCadastros, RepositorioDeSessoes
from .validacao import validar_email, validar_endereco, validar_nome

BOTAO_CONFIRMAR = "CONFIRMAR"
BOTAO_CORRIGIR = "CORRIGIR"

_COMANDOS_CANCELAR = frozenset({"cancelar"})
_COMANDOS_ATUALIZAR = frozenset({"atualizar"})
_COMANDOS_CONFIRMAR = frozenset({"sim", "confirmar", "confirmo"})
_COMANDOS_CORRIGIR = frozenset({"não", "nao", "corrigir"})

_PERGUNTAS = {
    Etapa.NOME: "Qual é o seu nome completo?",
    Etapa.EMAIL: "Qual é o seu e-mail?",
    Etapa.ENDERECO: "Qual é o seu endereço? Envie rua, número e bairro.",
}

# Texto sobre uso dos dados: revise com o jurídico/DPO da RevGás (LGPD) antes de publicar.
_AVISO_DE_USO = (
    "Vou pedir só 3 dados: nome, e-mail e endereço, usados apenas para o seu cadastro. "
    "Para parar a qualquer momento, envie CANCELAR."
)
MENSAGEM_BOAS_VINDAS = f"Olá! Eu sou o atendimento da RevGás. {_AVISO_DE_USO}\n\n{_PERGUNTAS[Etapa.NOME]}"
MENSAGEM_ATUALIZACAO = f"Vamos atualizar seus dados. {_AVISO_DE_USO}\n\n{_PERGUNTAS[Etapa.NOME]}"
MENSAGEM_CANCELADO = "Tudo bem, cancelei e não guardei nenhum dado. Quando quiser, é só mandar uma mensagem."
MENSAGEM_FALHA_TECNICA = "Tive um problema técnico e não consegui concluir agora. Tente de novo em alguns minutos."


class ServicoDeAtendimento:
    def __init__(self, cadastros: RepositorioDeCadastros, sessoes: RepositorioDeSessoes) -> None:
        self._cadastros = cadastros
        self._sessoes = sessoes

    async def atender(self, telefone: str, entrada: Entrada) -> Resposta:
        sessao = await self._sessoes.obter(telefone)
        if sessao is None:
            return await self._iniciar(telefone, entrada)
        if _comando(entrada) in _COMANDOS_CANCELAR:
            await self._sessoes.remover(telefone)
            return Resposta(MENSAGEM_CANCELADO)
        if sessao.etapa is Etapa.CONFIRMACAO:
            return await self._tratar_confirmacao(sessao, entrada)
        return await self._tratar_dado(sessao, entrada)

    async def _iniciar(self, telefone: str, entrada: Entrada) -> Resposta:
        cadastro = await self._cadastros.buscar_por_telefone(telefone)
        if cadastro is not None and _comando(entrada) not in _COMANDOS_ATUALIZAR:
            return Resposta(
                f"Olá, {_primeiro_nome(cadastro.nome)}! Seu cadastro já está completo. "
                "Para atualizar seus dados, envie ATUALIZAR."
            )
        await self._sessoes.salvar(Sessao(telefone, Etapa.NOME))
        return Resposta(MENSAGEM_ATUALIZACAO if cadastro else MENSAGEM_BOAS_VINDAS)

    async def _tratar_dado(self, sessao: Sessao, entrada: Entrada) -> Resposta:
        if entrada.texto is None:  # botão antigo, imagem, áudio...: repete a pergunta
            return _resposta_da_etapa(sessao)
        try:
            proxima = _avancar(sessao, entrada.texto)
        except DadoInvalidoError as erro:
            return Resposta(str(erro))
        await self._sessoes.salvar(proxima)
        return _resposta_da_etapa(proxima)

    async def _tratar_confirmacao(self, sessao: Sessao, entrada: Entrada) -> Resposta:
        comando = _comando(entrada)
        if entrada.botao_id == BOTAO_CONFIRMAR or comando in _COMANDOS_CONFIRMAR:
            cadastro = _montar_cadastro(sessao)
            # Se a gravação falhar, a sessão continua: o cliente só precisa confirmar de novo.
            await self._cadastros.salvar(cadastro)
            await self._sessoes.remover(sessao.telefone)
            return Resposta(f"Pronto, {_primeiro_nome(cadastro.nome)}! Seu cadastro foi concluído. Obrigado!")
        if entrada.botao_id == BOTAO_CORRIGIR or comando in _COMANDOS_CORRIGIR:
            await self._sessoes.salvar(Sessao(sessao.telefone, Etapa.NOME))
            return Resposta(f"Sem problema, vamos refazer. {_PERGUNTAS[Etapa.NOME]}")
        return _resposta_da_etapa(sessao)


def _avancar(sessao: Sessao, texto: str) -> Sessao:
    match sessao.etapa:
        case Etapa.NOME:
            return replace(sessao, nome=validar_nome(texto), etapa=Etapa.EMAIL)
        case Etapa.EMAIL:
            return replace(sessao, email=validar_email(texto), etapa=Etapa.ENDERECO)
        case Etapa.ENDERECO:
            return replace(sessao, endereco=validar_endereco(texto), etapa=Etapa.CONFIRMACAO)
    raise ValueError(f"A etapa {sessao.etapa} não recebe texto livre.")


def _resposta_da_etapa(sessao: Sessao) -> Resposta:
    if sessao.etapa is Etapa.CONFIRMACAO:
        resumo = (
            f"Confere?\nNome: {sessao.nome}\nE-mail: {sessao.email}\nEndereço: {sessao.endereco}"
        )
        return Resposta(
            resumo, (Botao(BOTAO_CONFIRMAR, "Confirmar"), Botao(BOTAO_CORRIGIR, "Corrigir"))
        )
    return Resposta(_PERGUNTAS[sessao.etapa])


def _montar_cadastro(sessao: Sessao) -> Cadastro:
    if sessao.nome is None or sessao.email is None or sessao.endereco is None:
        raise ErroDeDominio("Sessão incompleta ao confirmar o cadastro.")
    return Cadastro(sessao.telefone, sessao.nome, sessao.email, sessao.endereco)


def _comando(entrada: Entrada) -> str:
    return " ".join((entrada.texto or "").lower().split())


def _primeiro_nome(nome: str) -> str:
    return nome.split()[0]
