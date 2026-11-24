"""Cadastros e pedidos gravados em SQLite: sobrevivem ao reinício do servidor.

O cadastro é guardado pelo número do WhatsApp (`telefone`). Quando o mesmo número volta e pede
gás, o pedido encontra o cadastro e só pede confirmação, sem perguntar o endereço de novo.

SQLite vem com o Python (sem dependência nova) e serve bem para um servidor só. PRODUÇÃO com
vários servidores: troque por PostgreSQL/ERP mantendo os mesmos métodos.

O arquivo do banco tem dados pessoais (LGPD): fica fora do git (.gitignore) e deve ter backup e
acesso restritos.
"""
from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .modelos import Cadastro, IntegracaoError
from .modelos_pedido import FormaPagamento, Pedido, StatusPedido, TipoBotijao

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS cadastros (
    telefone          TEXT PRIMARY KEY,   -- número do WhatsApp, identifica o cliente
    nome              TEXT NOT NULL,
    telefone_contato  TEXT NOT NULL,
    endereco          TEXT NOT NULL,
    atualizado_em     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pedidos (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    telefone          TEXT NOT NULL,
    tipo_botijao      TEXT NOT NULL,
    quantidade        INTEGER NOT NULL,
    endereco_entrega  TEXT NOT NULL,
    criado_em         TEXT NOT NULL      -- ISO 8601 em UTC; conta o prazo de cancelamento
);
CREATE INDEX IF NOT EXISTS pedidos_por_telefone ON pedidos (telefone);
"""

# Colunas acrescentadas depois da primeira versão: bancos já existentes ganham as colunas na
# próxima partida do servidor, sem perder nada (pedidos antigos ficam como CONFIRMADO, sem pagamento).
_COLUNAS_NOVAS_DE_PEDIDOS = {
    "forma_pagamento": "TEXT",
    "troco_para": "TEXT",  # decimal como texto ("100.00"): sem erro de arredondamento
    "status": "TEXT NOT NULL DEFAULT 'CONFIRMADO'",
    "cancelado_em": "TEXT",
}

_COLUNAS_PEDIDO = "id, telefone, tipo_botijao, quantidade, endereco_entrega, forma_pagamento, troco_para, status, criado_em"


class BancoSqlite:
    """Abre uma conexão por operação, em uma thread, para não travar o servidor assíncrono."""

    def __init__(self, caminho: str | Path) -> None:
        self._caminho = Path(caminho)
        self._caminho.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._conectar()) as conexao, conexao:
            conexao.executescript(_ESQUEMA)
            existentes = {linha[1] for linha in conexao.execute("PRAGMA table_info(pedidos)")}
            for coluna, tipo in _COLUNAS_NOVAS_DE_PEDIDOS.items():
                if coluna not in existentes:
                    conexao.execute(f"ALTER TABLE pedidos ADD COLUMN {coluna} {tipo}")

    def _conectar(self) -> sqlite3.Connection:
        return sqlite3.connect(self._caminho, timeout=10)

    async def executar(self, sql: str, parametros: tuple = ()) -> list[tuple]:
        return await asyncio.to_thread(self._executar, sql, parametros)

    def _executar(self, sql: str, parametros: tuple) -> list[tuple]:
        try:
            with closing(self._conectar()) as conexao, conexao:  # `with conexao`: commit ou rollback
                return conexao.execute(sql, parametros).fetchall()
        except sqlite3.Error as erro:
            # Só o tipo do erro: a mensagem do SQLite pode citar valores (dados pessoais).
            raise IntegracaoError(f"Falha no banco de dados ({type(erro).__name__}).") from erro


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CadastrosSqlite:
    def __init__(self, banco: BancoSqlite) -> None:
        self._banco = banco

    async def buscar_por_telefone(self, telefone: str) -> Cadastro | None:
        linhas = await self._banco.executar(
            "SELECT telefone, nome, telefone_contato, endereco FROM cadastros WHERE telefone = ?", (telefone,)
        )
        return Cadastro(*linhas[0]) if linhas else None

    async def salvar(self, cadastro: Cadastro) -> None:
        """Insere ou atualiza (o cliente pode mandar ATUALIZAR e refazer o cadastro)."""
        await self._banco.executar(
            "INSERT INTO cadastros (telefone, nome, telefone_contato, endereco, atualizado_em) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (telefone) DO UPDATE SET nome = excluded.nome, "
            "telefone_contato = excluded.telefone_contato, endereco = excluded.endereco, "
            "atualizado_em = excluded.atualizado_em",
            (cadastro.telefone, cadastro.nome, cadastro.telefone_contato, cadastro.endereco, _agora()),
        )


class PedidosSqlite:
    def __init__(self, banco: BancoSqlite) -> None:
        self._banco = banco

    async def salvar(self, pedido: Pedido) -> Pedido:
        criado_em = pedido.criado_em or datetime.now(timezone.utc)
        linhas = await self._banco.executar(
            "INSERT INTO pedidos (telefone, tipo_botijao, quantidade, endereco_entrega, forma_pagamento, "
            "troco_para, status, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
            (
                pedido.telefone,
                pedido.tipo_botijao.value,
                pedido.quantidade,
                pedido.endereco_entrega,
                pedido.forma_pagamento.value if pedido.forma_pagamento else None,
                str(pedido.troco_para) if pedido.troco_para is not None else None,
                pedido.status.value,
                criado_em.isoformat(timespec="seconds"),
            ),
        )
        return replace(pedido, id=linhas[0][0], criado_em=criado_em)

    async def listar_por_telefone(self, telefone: str) -> list[Pedido]:
        linhas = await self._banco.executar(
            f"SELECT {_COLUNAS_PEDIDO} FROM pedidos WHERE telefone = ? ORDER BY id", (telefone,)
        )
        return [_pedido_da_linha(linha) for linha in linhas]

    async def ultimo_por_telefone(self, telefone: str) -> Pedido | None:
        linhas = await self._banco.executar(
            f"SELECT {_COLUNAS_PEDIDO} FROM pedidos WHERE telefone = ? ORDER BY id DESC LIMIT 1", (telefone,)
        )
        return _pedido_da_linha(linhas[0]) if linhas else None

    async def cancelar(self, id_pedido: int) -> bool:
        """Só cancela quem ainda está CONFIRMADO: duas mensagens CANCELAR seguidas não se atrapalham."""
        linhas = await self._banco.executar(
            "UPDATE pedidos SET status = ?, cancelado_em = ? WHERE id = ? AND status = ? RETURNING id",
            (StatusPedido.CANCELADO.value, _agora(), id_pedido, StatusPedido.CONFIRMADO.value),
        )
        return bool(linhas)


def _pedido_da_linha(linha: tuple) -> Pedido:
    id_pedido, telefone, tipo, quantidade, endereco, forma, troco, status, criado_em = linha
    return Pedido(
        telefone,
        TipoBotijao(tipo),
        quantidade,
        endereco,
        forma_pagamento=FormaPagamento(forma) if forma else None,
        troco_para=Decimal(troco) if troco else None,
        status=StatusPedido(status or StatusPedido.CONFIRMADO.value),
        criado_em=_ler_data(criado_em),
        id=id_pedido,
    )


def _ler_data(texto: str | None) -> datetime | None:
    if not texto:
        return None
    data = datetime.fromisoformat(texto)
    return data if data.tzinfo else data.replace(tzinfo=timezone.utc)  # sem fuso: gravado em UTC
