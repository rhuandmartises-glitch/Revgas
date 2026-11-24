"""Raiz de composição: único lugar que conhece as implementações concretas."""
from __future__ import annotations

import logging

from .atendimento import ServicoDeAtendimento
from .config import Configuracao
from .cep_viacep import ViaCep
from .persistencia_sqlite import BancoSqlite, CadastrosSqlite
from .portas import Atendente, ConsultaDeCep, RepositorioDeCadastros, WhatsAppGateway
from .processador import ProcessadorWhatsApp
from .simulacoes import CadastrosEmMemoria, SessoesEmMemoria, WhatsAppEmMemoria
from .webhook import ServicoDeWebhook
from .whatsapp_cloud import WhatsAppCloudApi

logger = logging.getLogger(__name__)


def montar_whatsapp(configuracao: Configuracao) -> WhatsAppGateway:
    """Cloud API de verdade com WA_ACCESS_TOKEN + WA_PHONE_NUMBER_ID; senão, modo console."""
    credenciais = configuracao.credenciais_whatsapp
    if credenciais is None:
        if configuracao.webhook_meta_ativo:  # só avisa quando alguém realmente usaria o envio direto
            logger.warning(
                "MODO CONSOLE: sem WA_ACCESS_TOKEN/WA_PHONE_NUMBER_ID, as respostas do webhook direto "
                "só aparecem neste terminal e nada é enviado ao WhatsApp."
            )
        return WhatsAppEmMemoria()
    return WhatsAppCloudApi(credenciais.token_acesso, credenciais.id_numero, credenciais.versao_api)


def montar_banco(configuracao: Configuracao) -> BancoSqlite | None:
    return BancoSqlite(configuracao.caminho_banco) if configuracao.caminho_banco else None


def montar_cadastros(banco: BancoSqlite | None) -> RepositorioDeCadastros:
    """Com banco: o cadastro fica guardado pelo número do WhatsApp, mesmo depois de reiniciar."""
    return CadastrosSqlite(banco) if banco else CadastrosEmMemoria()


def montar_consulta_cep(configuracao: Configuracao) -> ConsultaDeCep | None:
    """ViaCEP de verdade no servidor; None (só confere o formato do CEP) em testes e demos."""
    return ViaCep() if configuracao.consultar_cep_online else None


def montar_atendimento_cadastro(configuracao: Configuracao) -> ServicoDeAtendimento:
    """As sessões (conversa em andamento) ficam em memória: duram 15 min. PRODUÇÃO: Redis."""
    cadastros = montar_cadastros(montar_banco(configuracao))
    return ServicoDeAtendimento(
        cadastros, SessoesEmMemoria(configuracao.ttl_sessao_s), montar_consulta_cep(configuracao)
    )


def montar_servico_de_webhook(
    configuracao: Configuracao, atendimento: Atendente | None = None
) -> ServicoDeWebhook:
    """Passe `atendimento` para compartilhar as conversas com outra rota (ex.: POST /mensagem)."""
    atendimento = atendimento or montar_atendimento_cadastro(configuracao)
    processador = ProcessadorWhatsApp(atendimento, montar_whatsapp(configuracao))
    return ServicoDeWebhook(configuracao, processador)
