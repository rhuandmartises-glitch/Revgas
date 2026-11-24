"""Consulta de CEP pelo ViaCEP (viacep.com.br): serviço público e gratuito, sem chave nem cadastro.

Só o CEP sai do servidor, nunca nome ou telefone. Usa só a biblioteca padrão (urllib) em uma
thread, como o adaptador do WhatsApp.
"""
from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request

from .endereco import EnderecoDoCep
from .modelos import IntegracaoError

URL_BASE_PADRAO = "https://viacep.com.br/ws"


class ViaCep:
    def __init__(self, url_base: str = URL_BASE_PADRAO, timeout_s: float = 5.0) -> None:
        self._url_base = url_base.rstrip("/")
        self._timeout_s = timeout_s

    async def consultar(self, cep: str) -> EnderecoDoCep | None:
        if len(cep) != 8 or not cep.isdigit():
            return None
        return await asyncio.to_thread(self._consultar_sincrono, cep)

    def _consultar_sincrono(self, cep: str) -> EnderecoDoCep | None:
        requisicao = urllib.request.Request(
            f"{self._url_base}/{cep}/json/",
            headers={"Accept": "application/json", "User-Agent": "revgas-atendimento"},
        )
        try:
            with urllib.request.urlopen(requisicao, timeout=self._timeout_s) as resposta:
                dados = json.loads(resposta.read().decode("utf-8"))
        except urllib.error.HTTPError as erro:
            if erro.code == 400:  # formato de CEP recusado pelo ViaCEP
                return None
            raise IntegracaoError(f"ViaCEP respondeu HTTP {erro.code}.") from erro
        except (urllib.error.URLError, TimeoutError, ValueError) as erro:
            raise IntegracaoError(f"Falha ao consultar o CEP ({type(erro).__name__}).") from erro

        if not isinstance(dados, dict) or str(dados.get("erro", "")).lower() == "true":
            return None  # CEP com formato certo, mas que não existe
        return EnderecoDoCep(
            cep="".join(c for c in str(dados.get("cep", cep)) if c.isdigit()) or cep,
            logradouro=str(dados.get("logradouro") or "").strip(),
            bairro=str(dados.get("bairro") or "").strip(),
            cidade=str(dados.get("localidade") or "").strip(),
            uf=str(dados.get("uf") or "").strip(),
        )
