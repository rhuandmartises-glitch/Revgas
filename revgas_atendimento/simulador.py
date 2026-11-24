"""Simulador visual no estilo WhatsApp: converse com o bot pelo navegador.

Uso, na raiz do projeto:
    python -m revgas_atendimento.simulador            # abre http://127.0.0.1:8001
    python -m revgas_atendimento.simulador --porta 8010 --sem-navegador

Usa a mesma montagem do servidor (montar_loja): o mesmo banco (dados/revgas.sqlite3), a mesma
consulta de CEP, o mesmo prazo de cancelamento. Um cliente cadastrado aqui é lembrado pelo
servidor do WhatsApp/n8n, e vice-versa. As respostas aparecem só no navegador: nada é enviado
ao WhatsApp de verdade.

Segurança: só atende este computador. Recusa pedidos que não venham de 127.0.0.1/::1, que
cheguem com outro Host (proteção contra DNS rebinding) ou que passaram por proxy/túnel
(cabeçalhos X-Forwarded-For, CF-Connecting-IP...). A página não recebe nenhuma chave nem token.
"""
from __future__ import annotations

import argparse
import logging
import sys
import threading
import webbrowser
from collections.abc import Awaitable, Callable, Mapping
from importlib import resources

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from .ambiente import variaveis_do_servidor
from .atendimento import MENSAGEM_FALHA_TECNICA
from .composicao_pedido import Loja, montar_loja
from .config import Configuracao
from .modelos import ConfiguracaoInvalidaError, Entrada
from .modelos_pedido import Pedido
from .seguranca import proteger_logs_de_acesso
from .validacao import formatar_telefone

logger = logging.getLogger(__name__)

HOST = "127.0.0.1"
PORTA_PADRAO = 8001
_HOSTS_LOCAIS = frozenset({"127.0.0.1", "::1", "localhost"})
_CABECALHOS_DE_PROXY = ("x-forwarded-for", "forwarded", "x-real-ip", "cf-connecting-ip", "x-forwarded-host")
_PEDIDOS_NO_PAINEL = 10

# Página estática: só arquivos deste pacote, sem CDN, sem script em linha.
_ARQUIVOS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/chat.css": ("chat.css", "text/css; charset=utf-8"),
    "/chat.js": ("chat.js", "text/javascript; charset=utf-8"),
}
_CABECALHOS_DE_SEGURANCA = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


class MensagemDoSimulador(BaseModel):
    telefone: str = Field(min_length=8, max_length=32)
    texto: str = Field(min_length=1, max_length=4096)


class ConsultaDeCliente(BaseModel):
    telefone: str = Field(min_length=8, max_length=32)


def requisicao_local(ip_cliente: str | None, cabecalhos: Mapping[str, str]) -> bool:
    """True só para o navegador deste computador, falando direto com o simulador."""
    if ip_cliente not in _HOSTS_LOCAIS:
        return False
    if any(nome in cabecalhos for nome in _CABECALHOS_DE_PROXY):
        return False
    host = cabecalhos.get("host", "")
    nome_do_host = host.rsplit(":", 1)[0] if not host.startswith("[") else host[1:].split("]", 1)[0]
    return nome_do_host in _HOSTS_LOCAIS


def telefone_do_whatsapp(texto: str) -> str | None:
    """Número como o WhatsApp manda (DDI + DDD + número). "11 99999-0001" ganha o 55 na frente."""
    digitos = "".join(c for c in texto if c.isdigit())
    if len(digitos) in (10, 11):
        digitos = "55" + digitos
    return digitos if 12 <= len(digitos) <= 13 else None


def criar_simulador(configuracao: Configuracao | None = None) -> FastAPI:
    if configuracao is None:
        configuracao = Configuracao.do_ambiente(variaveis_do_servidor(), exigir_canal=False)
    loja = montar_loja(configuracao)
    proteger_logs_de_acesso()
    app = FastAPI(title="RevGás - Simulador", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def so_este_computador(
        requisicao: Request, proximo: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        ip = requisicao.client.host if requisicao.client else None
        if not requisicao_local(ip, requisicao.headers):
            return PlainTextResponse("O simulador só funciona neste computador.", status_code=403)
        resposta = await proximo(requisicao)
        resposta.headers.update(_CABECALHOS_DE_SEGURANCA)
        return resposta

    for caminho, (arquivo, tipo) in _ARQUIVOS.items():
        app.add_api_route(caminho, _servir(arquivo, tipo), methods=["GET"], include_in_schema=False)

    @app.get("/api/info")
    async def info() -> dict[str, object]:
        """O que está ligado (sem nenhum segredo): aparece no rodapé do painel."""
        return {
            "prazo_cancelamento_min": configuracao.prazo_cancelamento_min,
            "cep_online": configuracao.consultar_cep_online,
            "banco": "SQLite" if configuracao.caminho_banco else "memória (some ao fechar)",
        }

    @app.post("/api/mensagem")
    async def mensagem(corpo: MensagemDoSimulador) -> JSONResponse:
        telefone = telefone_do_whatsapp(corpo.telefone)
        if telefone is None:
            return JSONResponse({"detail": "Número do cliente inválido."}, status_code=422)
        return JSONResponse({"resposta": await _atender(loja, telefone, corpo.texto)})

    @app.post("/api/cliente")
    async def cliente(corpo: ConsultaDeCliente) -> JSONResponse:
        """POST (não GET com o número na URL): o telefone não fica no log de acesso."""
        telefone = telefone_do_whatsapp(corpo.telefone)
        if telefone is None:
            return JSONResponse({"detail": "Número do cliente inválido."}, status_code=422)
        return JSONResponse(await _dados_do_cliente(loja, telefone))

    return app


def _servir(arquivo: str, tipo: str) -> Callable[[], Awaitable[Response]]:
    """Lê o arquivo uma vez, na partida (reinicie o simulador para ver mudanças na página)."""
    conteudo = (resources.files(__package__) / "simulador_web" / arquivo).read_bytes()

    async def rota() -> Response:
        return Response(conteudo, media_type=tipo)

    return rota


async def _atender(loja: Loja, telefone: str, texto: str) -> str:
    try:
        return (await loja.atendimento.atender(telefone, Entrada(texto=texto))).texto
    except Exception:  # mesma fronteira do servidor: o cliente sempre recebe uma resposta
        logger.exception("Falha ao atender a mensagem do simulador")
        return MENSAGEM_FALHA_TECNICA


async def _dados_do_cliente(loja: Loja, telefone: str) -> dict[str, object]:
    cadastro = await loja.cadastros.buscar_por_telefone(telefone)
    pedidos = (await loja.pedidos.listar_por_telefone(telefone))[-_PEDIDOS_NO_PAINEL:]
    return {
        "cadastro": None if cadastro is None else {
            "nome": cadastro.nome,
            "telefone_contato": formatar_telefone(cadastro.telefone_contato),
            "endereco": cadastro.endereco,
        },
        "pedidos": [_pedido_para_o_painel(p) for p in reversed(pedidos)],
    }


def _pedido_para_o_painel(pedido: Pedido) -> dict[str, object]:
    return {
        "id": pedido.id,
        "itens": f"{pedido.quantidade}x {pedido.tipo_botijao.descricao}",
        "endereco": pedido.endereco_entrega,
        "pagamento": pedido.descricao_pagamento,
        "status": pedido.status.value,
        "criado_em": pedido.criado_em.isoformat() if pedido.criado_em else None,
    }


def main(argumentos: list[str] | None = None) -> int:
    leitor = argparse.ArgumentParser(description="Simulador visual do atendimento RevGás (estilo WhatsApp).")
    leitor.add_argument("--porta", type=int, default=PORTA_PADRAO)
    leitor.add_argument("--sem-navegador", action="store_true", help="não abre o navegador sozinho")
    opcoes = leitor.parse_args(argumentos)

    try:
        app = criar_simulador()
    except ConfiguracaoInvalidaError as erro:
        print(f"Configuração inválida: {erro}", file=sys.stderr)
        return 1

    import uvicorn  # só aqui: importar o módulo (ex.: nos testes) não exige o servidor

    endereco = f"http://{HOST}:{opcoes.porta}"
    print(f"Simulador RevGás em {endereco} (Ctrl+C para sair)")
    if not opcoes.sem_navegador:
        threading.Timer(1.5, webbrowser.open, args=(endereco,)).start()
    uvicorn.run(app, host=HOST, port=opcoes.porta, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
