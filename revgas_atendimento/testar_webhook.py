"""Teste de ponta a ponta do servidor local, simulando a Meta (assina as requisições de verdade).

Como usar (o servidor precisa estar rodando em OUTRA janela do PowerShell, em modo console):
    python testar_webhook.py

Lê WA_APP_SECRET e WA_VERIFY_TOKEN do ambiente ou do arquivo .env (os MESMOS valores do servidor).
As respostas do bot aparecem na janela do servidor, não aqui.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

URL_BASE = os.getenv("URL_BASE", "http://127.0.0.1:8000")
TELEFONE_FICTICIO = os.getenv("TELEFONE_TESTE", "5500999990000")
PAUSA_ENTRE_MENSAGENS_S = 0.4  # o servidor processa em segundo plano


def carregar_env(caminho: Path = Path(".env")) -> None:
    if not caminho.is_file():
        return
    for linha in caminho.read_text(encoding="utf-8-sig").splitlines():
        chave, separador, valor = linha.strip().partition("=")
        if separador and chave and not chave.startswith("#"):
            os.environ.setdefault(chave.strip(), valor.strip().strip("\"'"))


def requisitar(metodo: str, caminho: str, corpo: bytes | None = None,
               cabecalhos: dict[str, str] | None = None) -> tuple[int, str]:
    requisicao = urllib.request.Request(
        URL_BASE + caminho, data=corpo, method=metodo, headers=cabecalhos or {}
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=10) as resposta:
            return resposta.status, resposta.read().decode("utf-8")
    except urllib.error.HTTPError as erro:
        return erro.code, erro.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as erro:
        sys.exit(f"\nNão consegui conectar em {URL_BASE} ({erro.reason}).\n"
                 "O servidor está rodando em outra janela? Veja o passo 'Subir o servidor'.")


def assinar(segredo: str, corpo: bytes) -> str:
    return "sha256=" + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()


def evento_da_meta(conteudo: dict) -> bytes:
    """Monta um webhook no mesmo formato que a Meta envia."""
    mensagem = {"from": TELEFONE_FICTICIO, "id": f"wamid.TESTE{time.time_ns()}",
                "timestamp": str(int(time.time())), **conteudo}
    corpo = {"object": "whatsapp_business_account", "entry": [{"id": "TESTE", "changes": [{
        "field": "messages", "value": {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "0", "phone_number_id": "0"},
            "contacts": [{"profile": {"name": "Cliente Teste"}, "wa_id": TELEFONE_FICTICIO}],
            "messages": [mensagem]}}]}]}
    return json.dumps(corpo).encode("utf-8")


def texto(corpo: str) -> dict:
    return {"type": "text", "text": {"body": corpo}}


def botao(botao_id: str) -> dict:
    return {"type": "interactive",
            "interactive": {"type": "button_reply", "button_reply": {"id": botao_id, "title": botao_id}}}


falhas = 0


def conferir(descricao: str, condicao: bool, detalhe: str = "") -> None:
    global falhas
    print(f"  [{'OK' if condicao else 'FALHOU'}] {descricao}" + ("" if condicao else f"  -> {detalhe}"))
    falhas += 0 if condicao else 1


def main() -> None:
    carregar_env()
    segredo, token = os.getenv("WA_APP_SECRET", ""), os.getenv("WA_VERIFY_TOKEN", "")
    if not segredo or not token:
        sys.exit("Defina WA_APP_SECRET e WA_VERIFY_TOKEN (no .env ou no ambiente), iguais aos do servidor.")

    print("1) Servidor no ar")
    status, _ = requisitar("GET", "/saude")
    conferir("GET /saude responde 200", status == 200, f"status {status}")

    print("2) Verificação do webhook (o que a Meta faz ao cadastrar a URL)")
    consulta = urllib.parse.urlencode({"hub.mode": "subscribe", "hub.verify_token": token, "hub.challenge": "12345"})
    status, corpo = requisitar("GET", f"/webhook/whatsapp?{consulta}")
    conferir("token correto devolve o desafio", status == 200 and corpo == "12345", f"status {status}, corpo {corpo!r}")
    consulta = urllib.parse.urlencode({"hub.mode": "subscribe", "hub.verify_token": "errado", "hub.challenge": "12345"})
    status, _ = requisitar("GET", f"/webhook/whatsapp?{consulta}")
    conferir("token errado é recusado (403)", status == 403, f"status {status}")

    print("3) Segurança do POST")
    cabecalho_json = {"Content-Type": "application/json"}
    corpo_valido = evento_da_meta(texto("oi"))
    status, _ = requisitar("POST", "/webhook/whatsapp", corpo_valido, cabecalho_json)
    conferir("sem assinatura é recusado (401)", status == 401, f"status {status}")
    status, _ = requisitar("POST", "/webhook/whatsapp", corpo_valido,
                           {**cabecalho_json, "X-Hub-Signature-256": assinar("segredo-errado", corpo_valido)})
    conferir("assinatura errada é recusada (401)", status == 401, f"status {status}")
    lixo = b"isto nao e json"
    status, _ = requisitar("POST", "/webhook/whatsapp", lixo,
                           {**cabecalho_json, "X-Hub-Signature-256": assinar(segredo, lixo)})
    conferir("JSON inválido com assinatura correta é recusado (400)", status == 400, f"status {status}")

    print("4) Conversa completa (confira as respostas do bot na janela do servidor)")
    roteiro = [("oi", texto("oi")), ("nome", texto("Maria da Silva")), ("e-mail inválido", texto("maria@@email")),
               ("e-mail", texto("maria@email.com")), ("endereço", texto("Rua das Flores, 120 - Centro")),
               ("toque em Confirmar", botao("CONFIRMAR"))]
    for rotulo, conteudo in roteiro:
        corpo_evento = evento_da_meta(conteudo)
        status, _ = requisitar("POST", "/webhook/whatsapp", corpo_evento,
                               {**cabecalho_json, "X-Hub-Signature-256": assinar(segredo, corpo_evento)})
        conferir(f"envio '{rotulo}' aceito (200)", status == 200, f"status {status}")
        time.sleep(PAUSA_ENTRE_MENSAGENS_S)

    print("\nSem falhas nas verificações HTTP." if not falhas else f"\n{falhas} verificação(ões) falharam.")
    print("Agora olhe a janela do servidor: deve haver 6 respostas 'Bot: ...', terminando em")
    print("'Pronto, Maria! Seu cadastro foi concluído.'")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
