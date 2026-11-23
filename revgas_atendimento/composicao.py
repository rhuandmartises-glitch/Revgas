"""Raiz de composição: único lugar que conhece as implementações concretas."""
from __future__ import annotations

import logging

from .atendimento import ServicoDeAtendimento
from .config import Configuracao
from .portas import WhatsAppGateway
from .processador import ProcessadorWhatsApp
from .simulacoes import CadastrosEmMemoria, SessoesEmMemoria, WhatsAppEmMemoria
from .webhook import ServicoDeWebhook
from .whatsapp_cloud import WhatsAppCloudApi

logger = logging.getLogger(__name__)


def montar_whatsapp(configuracao: Configuracao) -> WhatsAppGateway:
    credenciais = configuracao.credenciais_whatsapp
    if credenciais is None:
        logger.warning(
            "MODO CONSOLE: sem WA_ACCESS_TOKEN/WA_PHONE_NUMBER_ID, as respostas só aparecem "
            "neste terminal e nada é enviado ao WhatsApp."
        )
        return WhatsAppEmMemoria()
    return WhatsAppCloudApi(credenciais.token_acesso, credenciais.id_numero, credenciais.versao_api)


def montar_servico_de_webhook(configuracao: Configuracao) -> ServicoDeWebhook:
    """PRODUÇÃO: troque CadastrosEmMemoria pelo ERP RevGás e SessoesEmMemoria por Redis.
    Do jeito que está, os cadastros se perdem sempre que o servidor reinicia."""
    atendimento = ServicoDeAtendimento(
        CadastrosEmMemoria(), SessoesEmMemoria(configuracao.ttl_sessao_s)
    )
    processador = ProcessadorWhatsApp(atendimento, montar_whatsapp(configuracao))
    return ServicoDeWebhook(configuracao, processador)
