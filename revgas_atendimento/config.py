"""Configuração centralizada: lida uma vez, na inicialização, e injetada onde for preciso.

O servidor tem duas entradas, e cada uma tem as suas variáveis (defina ao menos uma):
- Webhook direto da Meta (/webhook/whatsapp): WA_APP_SECRET + WA_VERIFY_TOKEN.
- Automação, ex.: n8n (/mensagem): N8N_API_KEY.
O envio direto pela Cloud API (WA_ACCESS_TOKEN + WA_PHONE_NUMBER_ID) só é usado pelo webhook direto.

Tokens e chaves viram `Segredo`: nunca aparecem em log, print ou traceback (veja segredo.py).
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from .modelos import ConfiguracaoInvalidaError
from .segredo import Segredo

VERSAO_API_PADRAO = "v26.0"
TTL_SESSAO_PADRAO_S = 900.0  # 15 min de inatividade e os dados parciais são descartados
CAMINHO_BANCO_PADRAO = "dados/revgas.sqlite3"  # relativo à pasta onde o servidor é iniciado
PRAZO_CANCELAMENTO_PADRAO_MIN = 5
PRAZO_CANCELAMENTO_MAXIMO_MIN = 24 * 60

# Textos de exemplo do .env.example/.env: tratados como "não preenchido", com erro claro.
_MARCAS_DE_EXEMPLO = ("COLE_", "defina_")
_VALORES_DESLIGADO = frozenset({"0", "nao", "não", "false", "off"})


@dataclass(frozen=True)
class CredenciaisWhatsApp:
    """Credenciais da WhatsApp Cloud API. Opcionais: sem elas, o envio fica em modo console."""

    token_acesso: Segredo
    id_numero: str
    versao_api: str = VERSAO_API_PADRAO

    def __post_init__(self) -> None:
        object.__setattr__(self, "token_acesso", Segredo.de(self.token_acesso))


@dataclass(frozen=True)
class Configuracao:
    # Webhook direto da Meta. None = rota /webhook/whatsapp desativada.
    segredo_app_whatsapp: Segredo | None = None
    token_verificacao_whatsapp: Segredo | None = None
    ttl_sessao_s: float = TTL_SESSAO_PADRAO_S
    credenciais_whatsapp: CredenciaisWhatsApp | None = None
    # Chave que o n8n (ou outra automação) manda no cabeçalho X-Api-Key. None = /mensagem desativada.
    chave_api_automacao: Segredo | None = None
    # Arquivo SQLite com cadastros e pedidos. None = só em memória (testes e demos): some ao reiniciar.
    caminho_banco: str | None = None
    # Consulta o CEP no ViaCEP (internet). False: confere só o formato e pede o endereço digitado.
    consultar_cep_online: bool = False
    # Quanto tempo depois de confirmar o cliente ainda cancela pelo WhatsApp. 0: não cancela por aqui.
    prazo_cancelamento_min: int = PRAZO_CANCELAMENTO_PADRAO_MIN

    def __post_init__(self) -> None:
        # Quem monta à mão (testes, demos) pode passar texto: vira Segredo do mesmo jeito.
        for nome in ("segredo_app_whatsapp", "token_verificacao_whatsapp", "chave_api_automacao"):
            object.__setattr__(self, nome, Segredo.de(getattr(self, nome)))

    @property
    def webhook_meta_ativo(self) -> bool:
        return self.segredo_app_whatsapp is not None and self.token_verificacao_whatsapp is not None

    @classmethod
    def do_ambiente(cls, variaveis: Mapping[str, str] | None = None, exigir_canal: bool = True) -> Configuracao:
        """Lê de `variaveis` (padrão: as do sistema). `exigir_canal=False` serve para o simulador
        local, que não recebe mensagens da Meta nem do n8n."""
        leitor = _Leitor(os.environ if variaveis is None else variaveis)
        segredo, token_verificacao = leitor.par("WA_APP_SECRET", "WA_VERIFY_TOKEN", "o webhook direto da Meta")
        chave_automacao = leitor.texto("N8N_API_KEY")
        if exigir_canal and not segredo and not chave_automacao:
            raise ConfiguracaoInvalidaError(
                "Nada para receber mensagens: defina WA_APP_SECRET e WA_VERIFY_TOKEN (webhook direto "
                "da Meta) e/ou N8N_API_KEY (rota /mensagem, para o n8n)."
            )
        token, id_numero = leitor.par("WA_ACCESS_TOKEN", "WA_PHONE_NUMBER_ID", "enviar pela Cloud API")
        credenciais = (
            CredenciaisWhatsApp(Segredo(token), id_numero, leitor.texto("WA_API_VERSION") or VERSAO_API_PADRAO)
            if token and id_numero
            else None
        )
        return cls(
            segredo_app_whatsapp=Segredo.de(segredo),
            token_verificacao_whatsapp=Segredo.de(token_verificacao),
            credenciais_whatsapp=credenciais,
            chave_api_automacao=Segredo.de(chave_automacao),
            # O servidor sempre guarda em disco, para lembrar o cadastro de quem volta para pedir gás.
            caminho_banco=leitor.texto("REVGAS_BANCO") or CAMINHO_BANCO_PADRAO,
            consultar_cep_online=(leitor.texto("REVGAS_CEP_ONLINE") or "1").lower() not in _VALORES_DESLIGADO,
            prazo_cancelamento_min=leitor.minutos("REVGAS_PRAZO_CANCELAMENTO_MIN", PRAZO_CANCELAMENTO_PADRAO_MIN),
        )


class _Leitor:
    """Lê variáveis com as mesmas regras para todas. As mensagens de erro citam o nome, nunca o valor."""

    def __init__(self, variaveis: Mapping[str, str]) -> None:
        self._variaveis = variaveis

    def texto(self, nome: str) -> str | None:
        """Valor sem espaços nas pontas; None se vazio. Texto de exemplo vira erro."""
        valor = (self._variaveis.get(nome) or "").strip()
        if not valor:
            return None
        if any(marca in valor for marca in _MARCAS_DE_EXEMPLO):
            raise ConfiguracaoInvalidaError(
                f"{nome} ainda está com o texto de exemplo: preencha com o valor real ou comente a linha."
            )
        return valor

    def minutos(self, nome: str, padrao: int) -> int:
        texto = self.texto(nome)
        if texto is None:
            return padrao
        if not texto.isdigit() or int(texto) > PRAZO_CANCELAMENTO_MAXIMO_MIN:
            raise ConfiguracaoInvalidaError(
                f"{nome} deve ser um número inteiro de minutos, de 0 a {PRAZO_CANCELAMENTO_MAXIMO_MIN}."
            )
        return int(texto)

    def par(self, nome_a: str, nome_b: str, finalidade: str) -> tuple[str | None, str | None]:
        """As duas ausentes: recurso desligado. Só uma definida: erro cedo, em vez de falhar no uso."""
        a, b = self.texto(nome_a), self.texto(nome_b)
        if bool(a) != bool(b):
            raise ConfiguracaoInvalidaError(
                f"Defina {nome_a} e {nome_b} juntas para {finalidade} (ou nenhuma das duas)."
            )
        return a, b
