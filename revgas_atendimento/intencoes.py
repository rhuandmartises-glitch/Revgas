"""O que o cliente quis dizer, em português do dia a dia, sem exigir uma palavra exata.

Todas as listas são comparadas sem acento, sem pontuação e em minúsculas (veja texto.py):
"Não sei!", "nao sei" e "NÃO SEI." viram a mesma coisa.

Dois tipos de lista:
- palavras: basta aparecer em qualquer lugar da mensagem ("quero *cancelar* o pedido").
- frases: a mensagem inteira (ou um trecho dela, quando dito) tem que ser a frase. Serve para
  palavras curtas que aparecem em outros contextos: "para" cancela sozinho, mas não em
  "troco para 100"; "não quero" cancela, mas "não quero troco" não.
"""
from __future__ import annotations

from .texto import comando, palavras

# ── Cancelar / desistir ─────────────────────────────────────────────────────
_CANCELAR_PALAVRAS = frozenset({
    "cancelar", "cancela", "cancele", "cancelo", "cancelamento", "cancelado",
    "desisto", "desistir", "desisti", "desiste",
})
_CANCELAR_FRASES = frozenset({
    "deixa pra la", "deixa para la", "deixa", "esquece", "esquece isso", "esqueca", "esquece tudo",
    "nao quero", "nao quero mais", "nao preciso mais", "nao vou querer", "nao precisa mais",
    "mudei de ideia", "para", "pare", "parar", "chega", "sair", "encerrar", "encerra",
    "pode parar", "pode cancelar", "deixa quieto", "nao quero nada",
})

# ── Não sei (o CEP) ─────────────────────────────────────────────────────────
_NAO_SEI_TRECHOS = (
    "nao sei", "sei nao", "nao lembro", "lembro nao", "nao faco ideia", "nem ideia", "sei la",
    "esqueci", "nao tenho", "tenho nao", "nao conheco", "nem sei", "nao to lembrando",
    "nao estou lembrando", "nao recordo", "sem cep", "nao sabe", "desconheco",
)
_NAO_SEI_FRASES = frozenset({"ns", "n sei", "nsei"})

# ── Sim / confirmação ───────────────────────────────────────────────────────
CONFIRMAR_PALAVRAS = frozenset({
    "sim", "s", "ss", "sss", "simm", "isso", "ok", "okay", "okey", "blz", "beleza", "certo", "certinho",
    "certissimo", "correto", "confirmo", "confirmar", "confirma", "confirmado", "pode", "claro", "perfeito",
    "exato", "exatamente", "positivo", "afirmativo", "fechado", "fechou", "bora", "show", "top", "otimo",
    "massa", "joia", "yes", "aham", "uhum", "manda", "certeza",
})
CONFIRMAR_TRECHOS = (
    "pode ser", "pode mandar", "pode confirmar", "manda ver", "ta certo", "esta certo", "ta bom",
    "esta bom", "tudo certo", "ta otimo", "isso ai", "isso mesmo", "com certeza", "e isso", "ta perfeito",
    "pode fechar", "pode enviar", "pode trazer", "pode vir",
)
_EMOJIS_DE_SIM = ("👍", "👌", "✅", "🙏", "🤝", "☑")

# ── Não / algo errado ───────────────────────────────────────────────────────
NEGAR_PALAVRAS = frozenset({
    "nao", "n", "nn", "negativo", "errado", "errada", "incorreto", "incorreta", "mudar", "mudou",
    "mudei", "muda", "trocar", "troca", "troquei", "outro", "outra", "alterar", "altera", "nops", "nope",
})

# ── Refazer do começo ───────────────────────────────────────────────────────
REFAZER_PALAVRAS = frozenset({"refazer", "refaz", "refaco", "corrigir", "recomecar", "recomeca", "reiniciar", "reinicia"})
_REFAZER_TRECHOS = ("do comeco", "do inicio", "do zero", "comecar de novo", "comeca de novo", "fazer de novo", "tudo de novo")

# ── Atualizar o cadastro ────────────────────────────────────────────────────
_ATUALIZAR_PALAVRAS = frozenset({
    "atualizar", "atualiza", "atualizacao", "alterar", "altera", "editar", "edita", "corrigir", "corrige",
    "mudar", "muda", "trocar", "troca", "modificar",
})

# ── Sem troco ───────────────────────────────────────────────────────────────
_SEM_TROCO_TRECHOS = (
    "sem troco", "nao precisa", "nao preciso", "nao vou precisar", "nao vai precisar", "trocado", "certinho", "dinheiro certo",
    "valor certo", "contado", "valor exato", "dinheiro exato", "nao quero troco", "precisa nao", "preciso nao",
)
_SEM_TROCO_FRASES = frozenset({"nao", "n", "nn", "negativo", "sem", "nada", "nenhum", "ta certo", "vai certinho"})


def _tem_trecho(texto_normalizado: str, trechos: tuple[str, ...]) -> bool:
    cercado = f" {texto_normalizado} "
    return any(f" {trecho} " in cercado for trecho in trechos)


def quer_cancelar(texto: str | None, so_frase_exata: bool = False) -> bool:
    """ "cancela", "quero cancelar o pedido", "desisto", "deixa pra lá", "não quero mais", "para".

    `so_frase_exata=True` ignora palavras soltas no meio da frase: use quando a resposta esperada
    é um nome (há sobrenomes como "Cancela")."""
    normalizado = comando(texto)
    if normalizado in _CANCELAR_FRASES:
        return True
    if so_frase_exata:
        return normalizado in _CANCELAR_PALAVRAS
    return bool(set(palavras(texto)) & _CANCELAR_PALAVRAS)


def nao_sabe(texto: str | None) -> bool:
    """ "não sei", "sei lá", "não lembro o CEP", "esqueci", "não tenho"."""
    normalizado = comando(texto)
    return normalizado in _NAO_SEI_FRASES or _tem_trecho(normalizado, _NAO_SEI_TRECHOS)


def concorda(texto: str | None) -> bool:
    """ "sim", "pode mandar", "tá certo", "fechado", "👍"."""
    if texto and any(emoji in texto for emoji in _EMOJIS_DE_SIM):
        return True
    return bool(set(palavras(texto)) & CONFIRMAR_PALAVRAS) or _tem_trecho(comando(texto), CONFIRMAR_TRECHOS)


def discorda(texto: str | None) -> bool:
    """ "não", "tá errado", "mudou", "quero trocar"."""
    return bool(set(palavras(texto)) & NEGAR_PALAVRAS)


def quer_refazer(texto: str | None) -> bool:
    """ "refazer", "corrigir", "começar de novo", "do zero"."""
    return bool(set(palavras(texto)) & REFAZER_PALAVRAS) or _tem_trecho(comando(texto), _REFAZER_TRECHOS)


def quer_atualizar_cadastro(texto: str | None) -> bool:
    """ "atualizar", "quero mudar meu endereço", "trocar meus dados", "corrigir meu nome"."""
    return bool(set(palavras(texto)) & _ATUALIZAR_PALAVRAS)


def dispensa_troco(texto: str | None) -> bool:
    """ "não", "sem troco", "não precisa", "vou dar certinho", "tenho trocado"."""
    normalizado = comando(texto)
    return normalizado in _SEM_TROCO_FRASES or _tem_trecho(normalizado, _SEM_TROCO_TRECHOS)
