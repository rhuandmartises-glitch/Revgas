"""Worker durável: um evento por conversa, com respostas materializadas antes do envio."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from .atendimento import ServicoDeAtendimento
from .modelos import Entrada
from .persistencia import BancoSQLite, CaixaDeMensagensSQLite
from .portas import WhatsAppGateway
from .whatsapp import montar_mensagem

logger = logging.getLogger(__name__)


class WorkerDeMensagens:
    def __init__(self, banco: BancoSQLite, caixa: CaixaDeMensagensSQLite,
                 atendimento: ServicoDeAtendimento, whatsapp: WhatsAppGateway) -> None:
        self.banco, self.caixa = banco, caixa
        self.atendimento, self.whatsapp = atendimento, whatsapp

    async def executar_uma(self) -> bool:
        item = await self.caixa.reivindicar()
        if item is None:
            return False
        mid, telefone = item['id'], item['telefone']
        if item['status'] == 'pending':
            try:
                dados: dict[str, Any] = json.loads(item['entrada'])
                # Transação única: estado da conversa e resposta preparada são atômicos.
                async with self.banco.transacao():
                    resposta = await self.atendimento.atender(
                        telefone, Entrada(texto=dados.get('texto'), botao_id=dados.get('botao_id'))
                    )
                    await self.caixa.preparar(mid, montar_mensagem(telefone, resposta))
            except Exception:
                logger.exception('Falha ao preparar resposta de mensagem id=%s', mid)
                await self.caixa.falhou(mid, 'pending')
                return True
        # O item já está preparado; em falha da API NÃO reexecutar atendimento.
        try:
            async with self.banco.transacao() as con:
                resposta = con.execute('SELECT resposta FROM mensagens WHERE id=?', (mid,)).fetchone()[0]
                con.execute("UPDATE mensagens SET status='sending',lease_ate=strftime('%s','now')+90 WHERE id=?", (mid,))
            await self.whatsapp.enviar(telefone, json.loads(resposta))
        except Exception:
            logger.exception('Falha de envio para mensagem id=%s', mid)
            await self.caixa.falhou(mid, 'ready')
            return True
        await self.caixa.enviado(mid)
        return True

    async def executar_continuamente(self, intervalo_s: float = .2) -> None:
        while True:
            if not await self.executar_uma():
                await asyncio.sleep(intervalo_s)
