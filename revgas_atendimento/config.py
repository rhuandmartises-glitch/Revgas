"""Configuração centralizada: lida uma vez, na inicialização, e injetada onde for preciso.

O servidor tem duas entradas, e cada uma tem as suas variáveis (defina ao menos uma):
- Webhook direto da Meta (/webhook/whatsapp): WA_APP_SECRET + WA_VERIFY_TOKEN.
- Automação, ex.: n8n (/mensagem): N8N_API_KEY.
O envio direto pela Cloud API (WA_ACCESS_TOKEN + WA_PHONE_NUMBER_ID) só é usado pelo webhook direto.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from .modelos import ConfiguracaoInvalidaError

VERSAO_API_PADRAO = "v26.0"
TTL_SESSAO_PADRAO_S = 900.0  # 15 min de inatividade e os dados parciais são descartados
CAMINHO_BANCO_PADRAO = "dados/revgas.sqlite3"  # relativo à pasta onde o servidor é iniciado
PRAZO_CANCELAMENTO_PADRAO_MIN = 5

# Textos de exemplo do .env.example/.env: tratados como "não preenchido", com erro claro.
_MARCAS_DE_EXEMPLO = ("COLE_", "defina_")


@dataclass(frozen=True)
class CredenciaisWhatsApp:
    """Credenciais da WhatsApp Cloud API. Opcionais: sem elas, o envio fica em modo console."""

    token_acesso: str = field(repr=False)  # repr=False: não vaza em logs/tracebacks
    id_numero: str
    versao_api: str = VERSAO_API_PADRAO


@dataclass(frozen=True)
class Configuracao:
    # Webhook direto da Meta. None = rota /webhook/whatsapp desativada.
    segredo_app_whatsapp: str | None = field(default=None, repr=False)
    token_verificacao_whatsapp: str | None = field(default=None, repr=False)
    ttl_sessao_s: float = TTL_SESSAO_PADRAO_S
    credenciais_whatsapp: CredenciaisWhatsApp | None = None
    # Chave que o n8n (ou outra automação) manda no cabeçalho X-Api-Key. None = /mensagem desativada.
    chave_api_automacao: str | None = field(default=None, repr=False)
    # Arquivo SQLite com cadastros e pedidos. None = só em memória (testes e demos): some ao reiniciar.
    caminho_banco: str | None = None
    # Consulta o CEP no ViaCEP (internet). False: confere só o formato e pede o endereço digitado.
    consultar_cep_online: bool = False
    # Quanto tempo depois de confirmar o cliente ainda cancela pelo WhatsApp. 0: não cancela por aqui.
    prazo_cancelamento_min: int = PRAZO_CANCELAMENTO_PADRAO_MIN

    @property
    def webhook_meta_ativo(self) -> bool:
        return bool(self.segredo_app_whatsapp and self.token_verificacao_whatsapp)

    @classmethod
    def do_ambiente(cls) -> Configuracao:
        segredo, token_verificacao = _ler_par("WA_APP_SECRET", "WA_VERIFY_TOKEN", "o webhook direto da Meta")
        chave_automacao = _ler("N8N_API_KEY")
        if not segredo and not chave_automacao:
            raise ConfiguracaoInvalidaError(
                "Nada para receber mensagens: defina WA_APP_SECRET e WA_VERIFY_TOKEN (webhook direto "
                "da Meta) e/ou N8N_API_KEY (rota /mensagem, para o n8n)."
            )
        return cls(
            segredo_app_whatsapp=segredo,
            token_verificacao_whatsapp=token_verificacao,
            credenciais_whatsapp=_ler_credenciais_whatsapp(),
            chave_api_automacao=chave_automacao,
            # O servidor sempre guarda em disco, para lembrar o cadastro de quem volta para pedir gás.
            caminho_banco=_ler("REVGAS_BANCO") or CAMINHO_BANCO_PADRAO,
            consultar_cep_online=(_ler("REVGAS_CEP_ONLINE") or "1").lower() not in {"0", "nao", "não", "false"},
            prazo_cancelamento_min=_ler_minutos("REVGAS_PRAZO_CANCELAMENTO_MIN", PRAZO_CANCELAMENTO_PADRAO_MIN),
        )


def _ler(nome: str) -> str | None:
    """Valor sem espaços nas pontas; None se vazio. Texto de exemplo vira erro, sem mostrar o valor."""
    valor = (os.getenv(nome) or "").strip()
    if not valor:
        return None
    if any(marca in valor for marca in _MARCAS_DE_EXEMPLO):
        raise ConfiguracaoInvalidaError(
            f"{nome} ainda está com o texto de exemplo: preencha com o valor real ou comente a linha."
        )
    return valor


def _ler_minutos(nome: str, padrao: int) -> int:
    texto = _ler(nome)
    if texto is None:
        return padrao
    if not texto.isdigit() or int(texto) > 24 * 60:
        raise ConfiguracaoInvalidaError(f"{nome} deve ser um número inteiro de minutos, de 0 a 1440.")
    return int(texto)


def _ler_par(nome_a: str, nome_b: str, finalidade: str) -> tuple[str | None, str | None]:
    """As duas ausentes: recurso desligado. Só uma definida: erro cedo, em vez de falhar no uso."""
    a, b = _ler(nome_a), _ler(nome_b)
    if bool(a) != bool(b):
        raise ConfiguracaoInvalidaError(
            f"Defina {nome_a} e {nome_b} juntas para {finalidade} (ou nenhuma das duas)."
        )
    return a, b


def _ler_credenciais_whatsapp() -> CredenciaisWhatsApp | None:
    token, id_numero = _ler_par("WA_ACCESS_TOKEN", "WA_PHONE_NUMBER_ID", "enviar pela Cloud API")
    if not token or not id_numero:
        return None
    return CredenciaisWhatsApp(token, id_numero, _ler("WA_API_VERSION") or VERSAO_API_PADRAO)
