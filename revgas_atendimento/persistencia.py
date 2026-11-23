"""SQLite para cadastro, sessão e caixa de entrada/saída durável.

SQLite é adequado para uma demonstração ou instância única. As transações protegem
estado da conversa + resposta preparada de falhas intermediárias. Não registra PII nos logs.
"""
from __future__ import annotations

import contextvars
import json
import sqlite3
import time
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from collections.abc import Iterator, AsyncIterator, Mapping
from typing import Any

from .modelos import Cadastro, Etapa, Sessao
from .whatsapp import MensagemRecebida


class BancoSQLite:
    def __init__(self, caminho: str) -> None:
        self.caminho = caminho
        self._transacao_atual: contextvars.ContextVar[sqlite3.Connection | None] = contextvars.ContextVar(
            f"conexao_sqlite_{id(self)}", default=None
        )
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        with self.conexao() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS cadastros (
                    telefone TEXT PRIMARY KEY, nome TEXT NOT NULL, email TEXT NOT NULL,
                    endereco TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessoes (
                    telefone TEXT PRIMARY KEY, etapa TEXT NOT NULL, nome TEXT,
                    email TEXT, endereco TEXT, expira_em REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mensagens (
                    id TEXT PRIMARY KEY, telefone TEXT NOT NULL, entrada TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', resposta TEXT,
                    tentativas INTEGER NOT NULL DEFAULT 0,
                    disponivel_em REAL NOT NULL DEFAULT 0,
                    lease_ate REAL NOT NULL DEFAULT 0,
                    criada_em REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_mensagens_status ON mensagens(status, disponivel_em);
                CREATE INDEX IF NOT EXISTS idx_mensagens_telefone ON mensagens(telefone, criada_em);
            """)

    @contextmanager
    def conexao(self) -> Iterator[sqlite3.Connection]:
        atual = self._transacao_atual.get()
        if atual is not None:
            yield atual
        else:
            con = sqlite3.connect(self.caminho, timeout=15, isolation_level=None)
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA busy_timeout=15000")
            try:
                yield con
            finally:
                con.close()

    @asynccontextmanager
    async def transacao(self) -> AsyncIterator[sqlite3.Connection]:
        if self._transacao_atual.get() is not None:
            raise RuntimeError("Transações aninhadas não são suportadas")
        with self.conexao() as con:
            con.execute("BEGIN IMMEDIATE")
            token = self._transacao_atual.set(con)
            try:
                yield con
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise
            finally:
                self._transacao_atual.reset(token)


class CadastrosSQLite:
    def __init__(self, banco: BancoSQLite) -> None:
        self.banco = banco

    async def buscar_por_telefone(self, telefone: str) -> Cadastro | None:
        with self.banco.conexao() as con:
            item = con.execute("SELECT * FROM cadastros WHERE telefone=?", (telefone,)).fetchone()
        return Cadastro(item["telefone"], item["nome"], item["email"], item["endereco"]) if item else None

    async def salvar(self, cadastro: Cadastro) -> None:
        with self.banco.conexao() as con:
            con.execute(
                "INSERT INTO cadastros(telefone,nome,email,endereco) VALUES(?,?,?,?) "
                "ON CONFLICT(telefone) DO UPDATE SET nome=excluded.nome,email=excluded.email,endereco=excluded.endereco",
                (cadastro.telefone, cadastro.nome, cadastro.email, cadastro.endereco),
            )


class SessoesSQLite:
    def __init__(self, banco: BancoSQLite, ttl_s: float) -> None:
        self.banco, self.ttl_s = banco, ttl_s

    async def obter(self, telefone: str) -> Sessao | None:
        with self.banco.conexao() as con:
            item = con.execute("SELECT * FROM sessoes WHERE telefone=?", (telefone,)).fetchone()
            if item and item["expira_em"] <= time.time():
                con.execute("DELETE FROM sessoes WHERE telefone=?", (telefone,))
                return None
        return (Sessao(item["telefone"], Etapa(item["etapa"]), item["nome"], item["email"], item["endereco"])
                if item else None)

    async def salvar(self, sessao: Sessao) -> None:
        with self.banco.conexao() as con:
            con.execute(
                "INSERT INTO sessoes(telefone,etapa,nome,email,endereco,expira_em) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(telefone) DO UPDATE SET etapa=excluded.etapa,nome=excluded.nome,"
                "email=excluded.email,endereco=excluded.endereco,expira_em=excluded.expira_em",
                (sessao.telefone, sessao.etapa.value, sessao.nome, sessao.email, sessao.endereco,
                 time.time() + self.ttl_s),
            )

    async def remover(self, telefone: str) -> None:
        with self.banco.conexao() as con:
            con.execute("DELETE FROM sessoes WHERE telefone=?", (telefone,))


class CaixaDeMensagensSQLite:
    """Inbox idempotente, fila por telefone e outbox preparada antes do envio."""
    def __init__(self, banco: BancoSQLite, tentativas_maximas: int = 5) -> None:
        self.banco, self.tentativas_maximas = banco, tentativas_maximas

    async def registrar(self, mensagens: list[MensagemRecebida]) -> int:
        novas = 0
        async with self.banco.transacao() as con:
            for m in mensagens:
                entrada = json.dumps({"texto": m.entrada.texto, "botao_id": m.entrada.botao_id})
                cursor = con.execute(
                    "INSERT OR IGNORE INTO mensagens(id,telefone,entrada,status,criada_em) "
                    "VALUES(?,?,?,'pending',?)", (m.id, m.telefone, entrada, time.time())
                )
                novas += cursor.rowcount
        return novas

    async def reivindicar(self) -> sqlite3.Row | None:
        """Só processa a primeira mensagem não concluída de cada telefone."""
        agora = time.time()
        async with self.banco.transacao() as con:
            con.execute("UPDATE mensagens SET status='pending' WHERE status='processing' AND lease_ate<?", (agora,))
            con.execute("UPDATE mensagens SET status='ready' WHERE status='sending' AND lease_ate<?", (agora,))
            item = con.execute("""
                SELECT m.* FROM mensagens m
                WHERE m.status IN ('pending','ready') AND m.disponivel_em <= ?
                  AND NOT EXISTS (
                    SELECT 1 FROM mensagens older WHERE older.telefone=m.telefone
                    AND older.rowid < m.rowid AND older.status NOT IN ('sent','dead')
                  )
                ORDER BY m.rowid LIMIT 1
            """, (agora,)).fetchone()
            if item is None:
                return None
            proximo = 'processing' if item['status'] == 'pending' else 'sending'
            con.execute("UPDATE mensagens SET status=?,lease_ate=? WHERE id=?", (proximo, agora + 90, item['id']))
            return item

    async def preparar(self, identificador: str, resposta: Mapping[str, Any]) -> None:
        # Deve ser chamado dentro da mesma transação que altera sessão/cadastro.
        with self.banco.conexao() as con:
            con.execute("UPDATE mensagens SET resposta=?,status='sending',lease_ate=? WHERE id=? AND status='processing'",
                        (json.dumps(resposta, ensure_ascii=False), time.time() + 90, identificador))

    async def enviado(self, identificador: str) -> None:
        async with self.banco.transacao() as con:
            con.execute("UPDATE mensagens SET status='sent',lease_ate=0 WHERE id=? AND status='sending'", (identificador,))

    async def falhou(self, identificador: str, estado_anterior: str) -> None:
        """Após falha, não repete a regra de negócio se a resposta já foi preparada."""
        async with self.banco.transacao() as con:
            registro = con.execute("SELECT tentativas FROM mensagens WHERE id=?", (identificador,)).fetchone()
            if not registro:
                return
            tentativas = registro[0] + 1
            situacao = 'dead' if tentativas >= self.tentativas_maximas else estado_anterior
            atraso = min(300, 2 ** min(tentativas, 8)) if situacao != 'dead' else 0
            con.execute("UPDATE mensagens SET status=?,tentativas=?,disponivel_em=?,lease_ate=0 WHERE id=?",
                        (situacao, tentativas, time.time() + atraso, identificador))

    async def situacao(self, identificador: str) -> str | None:
        with self.banco.conexao() as con:
            linha = con.execute("SELECT status FROM mensagens WHERE id=?", (identificador,)).fetchone()
        return linha[0] if linha else None
