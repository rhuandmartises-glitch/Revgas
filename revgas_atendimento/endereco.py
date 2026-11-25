"""Coleta e validação do endereço pelo CEP, usada no cadastro, no pedido e na troca de endereço.

Conversa:
1. CEP  -> consulta (ViaCEP). Achou a rua: "Achei: Praça da Sé - Sé, São Paulo/SP. Qual é o número?"
2. NÚMERO (e complemento, se houver): "120 apto 3", "45, casa 2", "s/n".
Desvios:
- "não sei" o CEP, consulta fora do ar ou CEP da cidade toda (sem rua): pede o endereço digitado
  (rua, número e bairro), que precisa ter o número da casa.
- CEP inexistente ou com formato errado: pede de novo, lembrando que tudo bem não saber.
"Não sei" aceita as variações do dia a dia ("sei lá", "não lembro", "esqueci"): veja intencoes.py.

Tudo aqui é independente de WhatsApp e de banco: recebe texto, devolve a próxima mensagem.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from .intencoes import nao_sabe
from .modelos import DadoInvalidoError, IntegracaoError
from .texto import normalizar_espacos

if TYPE_CHECKING:
    from .portas import ConsultaDeCep

PERGUNTA_CEP = "Qual é o CEP? Ex.: 01001-000. Se não souber, sem problema, é só me falar."
PERGUNTA_ENDERECO_DIGITADO = "Me manda o endereço completo: rua, número e bairro."

_PADRAO_CEP = re.compile(r"(?<!\d)(\d{5})[-.\s]?(\d{3})(?!\d)")
_PADRAO_NUMERO = re.compile(
    r"^(?:n(?:[º°o]|umero)?\.?\s*)?(\d{1,6}[a-z]?)(?![\d])\s*[,.\-–]?\s*(.*)$", re.IGNORECASE
)
# Casa sem número: "s/n", "sn", "sem número", "não tem número", "não tem", "não possui".
_SEM_NUMERO = re.compile(
    r"^(?:s\s*/\s*n|sn|sem\s+n(?:u|ú)mero|n(?:a|ã)o\s+(?:tem|possui)(?:\s+n(?:u|ú)mero)?)\b\s*[,.\-–]?\s*(.*)$",
    re.IGNORECASE,
)
_SEM_NUMERO_NO_MEIO = re.compile(r"\bs\s*/\s*n\b|\bsem\s+n(?:u|ú)mero\b", re.IGNORECASE)
_TAMANHO_MAXIMO_COMPLEMENTO = 60


class EtapaEndereco(str, Enum):
    CEP = "CEP"
    NUMERO = "NUMERO"  # rua achada pelo CEP: falta o número
    DIGITADO = "DIGITADO"  # sem CEP utilizável: o cliente digita o endereço


@dataclass(frozen=True)
class EnderecoDoCep:
    """O que a consulta de CEP devolve. `logradouro` vem vazio em CEP de cidade inteira."""

    cep: str  # só os 8 dígitos
    logradouro: str = field(repr=False)
    bairro: str = field(repr=False)
    cidade: str
    uf: str


@dataclass(frozen=True)
class ColetaDeEndereco:
    """Estado da coleta, guardado dentro da sessão de cadastro ou de pedido."""

    etapa: EtapaEndereco = EtapaEndereco.CEP
    cep: str | None = field(default=None, repr=False)
    achado: EnderecoDoCep | None = field(default=None, repr=False)


@dataclass(frozen=True)
class PassoDaColeta:
    """Ou a coleta continua (`coleta` + `mensagem`), ou terminou (`endereco` pronto)."""

    mensagem: str = ""
    coleta: ColetaDeEndereco | None = None
    endereco: str | None = field(default=None, repr=False)


# ── Funções puras ───────────────────────────────────────────────────────────
def extrair_cep(texto: str | None) -> str | None:
    """Primeiro CEP do texto, só com os dígitos: "CEP 01001-000" -> "01001000"."""
    encontrado = _PADRAO_CEP.search(texto or "")
    return encontrado.group(1) + encontrado.group(2) if encontrado else None


def formatar_cep(cep: str) -> str:
    return f"{cep[:5]}-{cep[5:]}" if len(cep) == 8 else cep


def validar_numero(texto: str) -> tuple[str, str]:
    """Número da casa e complemento: "120 apto 3" -> ("120", "apto 3"); "s/n" -> ("s/n", "")."""
    limpo = normalizar_espacos(texto)
    sem_numero = _SEM_NUMERO.match(limpo)
    encontrado = sem_numero or _PADRAO_NUMERO.match(limpo)
    if encontrado is None:
        raise DadoInvalidoError(
            "Me manda o número da casa, ex.: 120. Se tiver complemento, pode mandar junto: 120 apto 3. "
            "Se a casa não tiver número, é só dizer."
        )
    numero = "s/n" if sem_numero else encontrado.group(1).upper()
    complemento = encontrado.group(1 if sem_numero else 2).strip(" ,.-–")
    if len(complemento) > _TAMANHO_MAXIMO_COMPLEMENTO:
        raise DadoInvalidoError("O complemento ficou muito longo. Pode resumir? Ex.: 120 apto 3 bloco B.")
    return numero, complemento


def validar_endereco_digitado(texto: str) -> str:
    """Endereço escrito pelo cliente, sem consulta de CEP: precisa ter rua e número."""
    endereco = normalizar_espacos(texto)
    if not (8 <= len(endereco) <= 200) or not any(c.isalpha() for c in endereco):
        raise DadoInvalidoError(f"Não entendi o endereço. {PERGUNTA_ENDERECO_DIGITADO}")
    if not any(c.isdigit() for c in endereco) and not _SEM_NUMERO_NO_MEIO.search(endereco):
        raise DadoInvalidoError("Faltou o número da casa. Me manda de novo com rua, número e bairro.")
    return endereco


def parece_endereco(texto: str | None) -> bool:
    """Texto que o cliente mandou como endereço novo (tem letras e um número, ou um CEP)."""
    if extrair_cep(texto):
        return True
    try:
        validar_endereco_digitado(texto or "")
    except DadoInvalidoError:
        return False
    return True


def pergunta_da_coleta(coleta: ColetaDeEndereco | None) -> str:
    """A pergunta da etapa atual (para repetir quando chega imagem, áudio etc.)."""
    if coleta is None or coleta.etapa is EtapaEndereco.CEP:
        return PERGUNTA_CEP
    if coleta.etapa is EtapaEndereco.NUMERO and coleta.achado:
        return f"Achei: {_descrever_rua(coleta.achado)}. Qual é o número? Se tiver complemento, manda junto (ex.: 120 apto 3)."
    return PERGUNTA_ENDERECO_DIGITADO


def _descrever_rua(achado: EnderecoDoCep) -> str:
    bairro = f" - {achado.bairro}" if achado.bairro else ""
    return f"{achado.logradouro}{bairro}, {achado.cidade}/{achado.uf}"


def _montar_do_cep(achado: EnderecoDoCep, numero: str, complemento: str) -> str:
    complemento = f", {complemento}" if complemento else ""
    bairro = f" - {achado.bairro}" if achado.bairro else ""
    return (
        f"{achado.logradouro}, {numero}{complemento}{bairro}, {achado.cidade}/{achado.uf}"
        f" - CEP {formatar_cep(achado.cep)}"
    )


def _montar_digitado(texto: str, coleta: ColetaDeEndereco) -> str:
    cidade = f", {coleta.achado.cidade}/{coleta.achado.uf}" if coleta.achado else ""
    cep = f" - CEP {formatar_cep(coleta.cep)}" if coleta.cep else ""
    return f"{texto}{cidade}{cep}"


# ── Conversa ────────────────────────────────────────────────────────────────
class ColetorDeEndereco:
    def __init__(self, consulta: ConsultaDeCep | None) -> None:
        self._consulta = consulta  # None: sem consulta online (pede o endereço digitado após o CEP)

    async def receber(self, coleta: ColetaDeEndereco | None, texto: str) -> PassoDaColeta:
        coleta = coleta or ColetaDeEndereco()
        try:
            if coleta.etapa is EtapaEndereco.CEP:
                return await self._receber_cep(texto)
            if extrair_cep(texto) and coleta.etapa is EtapaEndereco.NUMERO and _so_cep(texto):
                return await self._receber_cep(texto)  # mandou outro CEP no lugar do número
            if coleta.etapa is EtapaEndereco.NUMERO and coleta.achado:
                numero, complemento = validar_numero(texto)
                return PassoDaColeta(endereco=_montar_do_cep(coleta.achado, numero, complemento))
            return PassoDaColeta(endereco=_montar_digitado(validar_endereco_digitado(texto), coleta))
        except DadoInvalidoError as erro:
            return PassoDaColeta(str(erro), coleta)

    async def _receber_cep(self, texto: str) -> PassoDaColeta:
        if nao_sabe(texto):
            return PassoDaColeta(f"Sem problema! {PERGUNTA_ENDERECO_DIGITADO}", ColetaDeEndereco(EtapaEndereco.DIGITADO))
        cep = extrair_cep(texto)
        if cep is None or len(set(cep)) == 1:
            raise DadoInvalidoError(
                "Não reconheci o CEP. Ele tem 8 números, ex.: 01001-000. Se não souber, me fala."
            )
        digitado = ColetaDeEndereco(EtapaEndereco.DIGITADO, cep=cep)
        if self._consulta is None:
            return PassoDaColeta(f"Anotei o CEP {formatar_cep(cep)}. {PERGUNTA_ENDERECO_DIGITADO}", digitado)
        try:
            achado = await self._consulta.consultar(cep)
        except IntegracaoError:
            return PassoDaColeta(
                f"Não consegui consultar o CEP agora, mas tudo bem. {PERGUNTA_ENDERECO_DIGITADO}", digitado
            )
        if achado is None:
            raise DadoInvalidoError(
                f"Não encontrei o CEP {formatar_cep(cep)}. Confere e me manda de novo, ou me avisa se não souber."
            )
        if not achado.logradouro:  # CEP geral da cidade: não identifica a rua
            return PassoDaColeta(
                f"Esse CEP é de {achado.cidade}/{achado.uf}, mas não indica a rua. {PERGUNTA_ENDERECO_DIGITADO}",
                ColetaDeEndereco(EtapaEndereco.DIGITADO, cep=cep, achado=achado),
            )
        proxima = ColetaDeEndereco(EtapaEndereco.NUMERO, cep=cep, achado=achado)
        return PassoDaColeta(pergunta_da_coleta(proxima), proxima)


def _so_cep(texto: str) -> bool:
    """O texto é só um CEP (com ou sem "CEP" na frente), não "120 apto 3" nem um endereço."""
    return bool(re.fullmatch(r"\s*(?:cep\s*:?\s*)?\d{5}[-.\s]?\d{3}\s*", texto, re.IGNORECASE))
