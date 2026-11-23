"""Única raiz de composição de adaptadores para CLI, HTTP e webhook."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from .atendimento import ServicoDeAtendimento
from .config import Configuracao
from .persistencia import BancoSQLite, CadastrosSQLite, CaixaDeMensagensSQLite, SessoesSQLite
from .portas import WhatsAppGateway
from .processador import ProcessadorWhatsApp
from .simulacoes import WhatsAppEmMemoria
from .webhook import ServicoDeWebhook
from .whatsapp_cloud import WhatsAppCloudApi
from .worker import WorkerDeMensagens

logger = logging.getLogger(__name__)


def montar_whatsapp(configuracao: Configuracao) -> WhatsAppGateway:
    credenciais = configuracao.credenciais_whatsapp
    if credenciais is None:
        logger.warning('MODO SIMULAÇÃO: WhatsApp sem credenciais; nenhuma mensagem real será enviada.')
        return WhatsAppEmMemoria()
    return WhatsAppCloudApi(credenciais.token_acesso, credenciais.id_numero, credenciais.versao_api)


@dataclass
class Componentes:
    banco: BancoSQLite
    caixa: CaixaDeMensagensSQLite
    atendimento: ServicoDeAtendimento
    whatsapp: WhatsAppGateway
    worker: WorkerDeMensagens
    processador: ProcessadorWhatsApp


def montar_componentes(configuracao: Configuracao) -> Componentes:
    banco = BancoSQLite(configuracao.caminho_banco)
    caixa = CaixaDeMensagensSQLite(banco, configuracao.tentativas_maximas)
    atendimento = ServicoDeAtendimento(CadastrosSQLite(banco), SessoesSQLite(banco, configuracao.ttl_sessao_s))
    whatsapp = montar_whatsapp(configuracao)
    return Componentes(banco, caixa, atendimento, whatsapp,
                       WorkerDeMensagens(banco, caixa, atendimento, whatsapp),
                       ProcessadorWhatsApp(atendimento, whatsapp))


def montar_servico_de_webhook(configuracao: Configuracao) -> ServicoDeWebhook:
    componentes = montar_componentes(configuracao)
    return ServicoDeWebhook(configuracao, componentes.processador, caixa=componentes.caixa)
