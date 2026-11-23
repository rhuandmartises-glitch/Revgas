"""Processa a inbox durável, preservando conversas e supervisionando falhas transitórias."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from .atendimento import ServicoDeAtendimento
from .modelos import Entrada, EntregaIncertaError
from .persistencia import BancoSQLite, CaixaDeMensagensSQLite
from .portas import WhatsAppGateway
from .whatsapp import montar_mensagem

logger = logging.getLogger(__name__)


class WorkerDeMensagens:
    def __init__(self, banco: BancoSQLite, caixa: CaixaDeMensagensSQLite,
                 atendimento: ServicoDeAtendimento, whatsapp: WhatsAppGateway) -> None:
        self.banco, self.caixa = banco, caixa
        self.atendimento, self.whatsapp = atendimento, whatsapp
        self.ativo = False

    async def executar_uma(self) -> bool:
        """Executa até um item; em falha do SQLite o supervisor assume a recuperação.

        O estado `uncertain` exige intervenção: não reenviar automaticamente uma
        resposta que possa ter sido aceita antes de falhar a confirmação local.
        """
        item = await self.caixa.reivindicar()
        if item is None:
            return False
        mid, telefone = item['id'], item['telefone']
        if item['status'] == 'pending':
            try:
                dados: dict[str, Any] = json.loads(item['entrada'])
                async with self.banco.transacao():
                    resposta = await self.atendimento.atender(
                        telefone, Entrada(texto=dados.get('texto'), botao_id=dados.get('botao_id'))
                    )
                    await self.caixa.preparar(mid, montar_mensagem(telefone, resposta))
            except Exception:
                logger.exception('Falha ao preparar resposta id=%s', mid)
                # Se este update falhar, o lease permite que a mensagem seja recuperada.
                await self.caixa.falhou(mid, 'pending')
                return True

        try:
            # A resposta foi gravada com a sessão; jamais reexecutar a regra de negócio.
            with self.banco.conexao() as con:
                registro = con.execute('SELECT resposta FROM mensagens WHERE id=?', (mid,)).fetchone()
            if registro is None or registro['resposta'] is None:
                raise RuntimeError('Resposta preparada não encontrada')
            await self.whatsapp.enviar(telefone, json.loads(registro['resposta']))
        except EntregaIncertaError:
            logger.exception('Envio externo sem confirmação id=%s; exige verificação humana', mid)
            await self.caixa.marcar_incerta(mid)
            return True
        except Exception:
            logger.exception('Falha ao enviar resposta id=%s', mid)
            await self.caixa.falhou(mid, 'ready')
            return True

        try:
            await self.caixa.enviado(mid)
        except Exception:
            # O envio EXTERNO pode ter sido aceito. Não tratar como falha de envio.
            logger.exception('Confirmação local falhou após envio id=%s; resultado incerto', mid)
            try:
                await self.caixa.marcar_incerta(mid)
            except Exception:
                # Persistência indisponível: o lease `sending` vencerá e será
                # convertido em `uncertain`, sem retransmissão automática.
                logger.exception('Não foi possível registrar envio incerto id=%s', mid)
            return True
        return True

    async def executar_continuamente(self, intervalo_s: float = 0.2) -> None:
        """Supervisiona falhas de banco/worker com backoff e aceita cancelamento."""
        falhas_consecutivas = 0
        self.ativo = True
        try:
            while True:
                try:
                    trabalhou = await self.executar_uma()
                    falhas_consecutivas = 0
                    if not trabalhou:
                        await asyncio.sleep(intervalo_s)
                except Exception:
                    falhas_consecutivas += 1
                    espera = min(30.0, max(intervalo_s, 0.1) * 2 ** min(falhas_consecutivas, 8))
                    logger.exception('Worker falhou, nova tentativa após %.2fs', espera)
                    await asyncio.sleep(espera)
        finally:
            self.ativo = False
