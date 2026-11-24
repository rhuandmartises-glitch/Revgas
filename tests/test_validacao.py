"""Validação do telefone (DDD) e do endereço (CEP). Rodar: python -m unittest -v tests.test_validacao"""
from __future__ import annotations

import json
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from revgas_atendimento.cep_viacep import ViaCep
from revgas_atendimento.endereco import (
    ColetaDeEndereco,
    ColetorDeEndereco,
    EnderecoDoCep,
    EtapaEndereco,
    extrair_cep,
    validar_endereco_digitado,
    validar_numero,
)
from revgas_atendimento.modelos import DadoInvalidoError, IntegracaoError
from revgas_atendimento.simulacoes import CepsEmMemoria
from revgas_atendimento.validacao import formatar_telefone, validar_telefone


class TesteTelefone(unittest.TestCase):
    def test_aceita_celular_e_fixo_escritos_de_varios_jeitos(self):
        casos = {
            "11988887777": "11988887777",
            "(11) 98888-7777": "11988887777",
            "+55 11 98888-7777": "11988887777",
            "011 98888-7777": "11988887777",
            "(21) 3333-4444": "2133334444",
            "55 (51) 99876-5432": "51998765432",  # DDD 55 (RS) com o código do país na frente
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(validar_telefone(texto), esperado)

    def test_recusa_com_mensagem_explicando_o_motivo(self):
        casos = {
            "98888-7777": "Faltou o DDD",
            "(20) 98888-7777": "DDD 20 não existe",
            "(10) 98888-7777": "DDD 10 não existe",
            "(11) 8888-7777": "sem o 9",
            "(11) 1888-7777": "fixo não parece válido",
            "(11) 88888-7777": "começar com 9",
            "(11) 99999-9999": "não parece real",
            "123": "incompleto",
        }
        for texto, trecho in casos.items():
            with self.subTest(texto=texto):
                with self.assertRaises(DadoInvalidoError) as contexto:
                    validar_telefone(texto)
                self.assertIn(trecho, str(contexto.exception))

    def test_formatacao_para_mostrar_ao_cliente(self):
        self.assertEqual(formatar_telefone("11988887777"), "(11) 98888-7777")
        self.assertEqual(formatar_telefone("2133334444"), "(21) 3333-4444")


class TesteCepENumero(unittest.TestCase):
    def test_extrai_cep_em_varios_formatos(self):
        for texto in ("01001-000", "01001000", "CEP: 01001.000", "mudou, o cep é 01001 000"):
            with self.subTest(texto=texto):
                self.assertEqual(extrair_cep(texto), "01001000")

    def test_nao_confunde_telefone_ou_numero_da_casa_com_cep(self):
        for texto in ("11988887777", "120", "Rua X, 1200"):
            with self.subTest(texto=texto):
                self.assertIsNone(extrair_cep(texto))

    def test_numero_e_complemento(self):
        casos = {
            "120": ("120", ""),
            "120 apto 3": ("120", "apto 3"),
            "45, casa 2": ("45", "casa 2"),
            "nº 1000 bloco B": ("1000", "bloco B"),
            "120a": ("120A", ""),
            "s/n": ("s/n", ""),
            "sem número, fundos": ("s/n", "fundos"),
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(validar_numero(texto), esperado)

    def test_numero_invalido(self):
        for texto in ("Rua X", "apto", "120 " + "x" * 80):
            with self.subTest(texto=texto[:20]):
                with self.assertRaises(DadoInvalidoError):
                    validar_numero(texto)

    def test_endereco_digitado_precisa_do_numero(self):
        self.assertEqual(validar_endereco_digitado("Rua A,  10 - Centro"), "Rua A, 10 - Centro")
        self.assertEqual(validar_endereco_digitado("Estrada Velha, s/n"), "Estrada Velha, s/n")
        with self.assertRaises(DadoInvalidoError):
            validar_endereco_digitado("Rua das Flores, Centro")


class TesteColetor(unittest.IsolatedAsyncioTestCase):
    async def test_cep_de_cidade_inteira_pede_rua_e_numero(self):
        cidade = EnderecoDoCep("13560970", "", "", "São Carlos", "SP")
        coletor = ColetorDeEndereco(CepsEmMemoria({"13560970": cidade}))
        passo = await coletor.receber(ColetaDeEndereco(), "13560-970")
        self.assertIn("São Carlos/SP, mas não indica a rua", passo.mensagem)
        pronto = await coletor.receber(passo.coleta, "Rua Episcopal, 700 - Centro")
        self.assertEqual(pronto.endereco, "Rua Episcopal, 700 - Centro, São Carlos/SP - CEP 13560-970")

    async def test_outro_cep_na_etapa_do_numero_refaz_a_consulta(self):
        coletor = ColetorDeEndereco(CepsEmMemoria())
        passo = await coletor.receber(ColetaDeEndereco(), "01001-000")
        self.assertIs(passo.coleta.etapa, EtapaEndereco.NUMERO)
        passo = await coletor.receber(passo.coleta, "01310-100")
        self.assertIn("Avenida Paulista", passo.mensagem)

    async def test_sem_consulta_confere_o_cep_e_pede_o_endereco(self):
        passo = await ColetorDeEndereco(None).receber(ColetaDeEndereco(), "01001000")
        self.assertIn("Anotei o CEP 01001-000", passo.mensagem)


class ViaCepFalso:
    """Imita o ViaCEP: responde por CEP com o JSON configurado (ou um status de erro)."""

    def __init__(self, respostas: dict[str, tuple[int, object]]) -> None:
        dono = self
        self.caminhos: list[str] = []

        class Manipulador(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                dono.caminhos.append(self.path)
                cep = self.path.strip("/").split("/")[-2]
                status, corpo = respostas.get(cep, (200, {"erro": "true"}))
                dados = json.dumps(corpo).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

            def log_message(self, *args) -> None:
                pass

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Manipulador)
        self.url = f"http://127.0.0.1:{self._httpd.server_address[1]}/ws"

    def __enter__(self) -> ViaCepFalso:
        threading.Thread(target=self._httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
        return self

    def __exit__(self, *args) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


class TesteAdaptadorViaCep(unittest.IsolatedAsyncioTestCase):
    async def test_cep_encontrado(self):
        resposta = {"cep": "01001-000", "logradouro": "Praça da Sé", "bairro": "Sé", "localidade": "São Paulo", "uf": "SP"}
        with ViaCepFalso({"01001000": (200, resposta)}) as servidor:
            achado = await ViaCep(servidor.url).consultar("01001000")
        self.assertEqual(achado, EnderecoDoCep("01001000", "Praça da Sé", "Sé", "São Paulo", "SP"))
        self.assertEqual(servidor.caminhos, ["/ws/01001000/json/"])

    async def test_cep_inexistente_ou_recusado_vira_none(self):
        with ViaCepFalso({"99999998": (400, {})}) as servidor:
            self.assertIsNone(await ViaCep(servidor.url).consultar("12345678"))  # {"erro": "true"}
            self.assertIsNone(await ViaCep(servidor.url).consultar("99999998"))  # HTTP 400

    async def test_formato_invalido_nem_consulta(self):
        self.assertIsNone(await ViaCep("http://127.0.0.1:9").consultar("123"))

    async def test_servico_fora_do_ar_vira_integracao_error(self):
        with socket.socket() as soquete:
            soquete.bind(("127.0.0.1", 0))
            porta_livre = soquete.getsockname()[1]
        with self.assertRaises(IntegracaoError):
            await ViaCep(f"http://127.0.0.1:{porta_livre}/ws", timeout_s=1).consultar("01001000")

    async def test_erro_500_vira_integracao_error(self):
        with ViaCepFalso({"01001000": (500, {})}) as servidor:
            with self.assertRaises(IntegracaoError):
                await ViaCep(servidor.url).consultar("01001000")


if __name__ == "__main__":
    unittest.main()
