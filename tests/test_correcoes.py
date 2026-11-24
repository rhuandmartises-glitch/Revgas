"""Testes de regressão dos erros corrigidos na revisão. Rodar: python -m unittest -v tests.test_correcoes"""
from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch

from fastapi.routing import APIRoute

from revgas_atendimento.api import criar_app
from revgas_atendimento.api_pedido import criar_app_com_pedido_de_gas
from revgas_atendimento.composicao import montar_servico_de_webhook
from revgas_atendimento.composicao_pedido import montar_servico_de_webhook_com_pedido_de_gas
from revgas_atendimento.simulacoes import WhatsAppEmMemoria
from revgas_atendimento.whatsapp_cloud import WhatsAppCloudApi
from revgas_atendimento.atendimento import ServicoDeAtendimento
from revgas_atendimento.atendimento_integrado import ServicoDeAtendimentoIntegrado
from revgas_atendimento.atendimento_pedido import ServicoDePedido, eh_pedido_de_gas
from revgas_atendimento.config import Configuracao, CredenciaisWhatsApp
from revgas_atendimento.interpretacao import Intencao, interpretar_confirmacao
from revgas_atendimento.modelos import Entrada
from revgas_atendimento.simulacoes import CadastrosEmMemoria, CepsEmMemoria, SessoesEmMemoria
from revgas_atendimento.simulacoes_pedido import PedidosEmMemoria
from revgas_atendimento.validacao_pedido import validar_quantidade

from tests.apoio import ENDERECO, FALAS_ENDERECO, TELEFONE


class TesteGatilhoEComandosComPontuacao(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        cadastros = CadastrosEmMemoria()
        sessoes = SessoesEmMemoria(900.0)
        self.pedidos = PedidosEmMemoria()
        self.servico_pedido = ServicoDePedido(self.pedidos, SessoesEmMemoria(900.0), cadastros)
        self.sessoes_cadastro = sessoes
        self.integrado = ServicoDeAtendimentoIntegrado(
            ServicoDeAtendimento(cadastros, sessoes), sessoes, self.servico_pedido
        )

    async def texto(self, texto: str):
        return await self.integrado.atender(TELEFONE, Entrada(texto=texto))

    def test_gatilho_de_pedido_aceita_pontuacao(self):
        for frase in ("gás?", "Quero gás!", "gás, por favor", "novo pedido."):
            with self.subTest(frase=frase):
                self.assertTrue(eh_pedido_de_gas(Entrada(texto=frase)))

    def test_gatilho_nao_dispara_em_palavra_parecida(self):
        self.assertFalse(eh_pedido_de_gas(Entrada(texto="gasolina")))

    async def test_cancelar_pedido_com_ponto(self):
        await self.texto("gás")
        resposta = await self.texto("Cancelar.")
        self.assertIn("cancelei", resposta.texto.lower())
        self.assertFalse(await self.servico_pedido.tem_sessao_ativa(TELEFONE))

    async def test_cancelar_cadastro_com_exclamacao(self):
        await self.texto("oi")
        resposta = await self.texto("cancelar!")
        self.assertIn("não guardei nenhum dado", resposta.texto)
        self.assertIsNone(await self.sessoes_cadastro.obter(TELEFONE))


class TesteConfirmacaoComNumeros(unittest.IsolatedAsyncioTestCase):
    def test_sim_com_numero_confirma(self):
        for frase in ("sim, os 2", "Sim, confirmo os 2 botijões", "ok, entrega até as 18h"):
            with self.subTest(frase=frase):
                self.assertIs(interpretar_confirmacao(frase), Intencao.CONFIRMAR)

    def test_nao_com_endereco_vira_negar(self):
        self.assertIs(interpretar_confirmacao("não, o endereço é Rua X, 12 - Centro"), Intencao.NEGAR)

    def test_endereco_puro_ou_cep_vira_endereco_novo(self):
        for frase in ("Rua Nova, 50 - Centro", "01001-000", "mudou, o CEP é 01001000"):
            with self.subTest(frase=frase):
                self.assertIs(interpretar_confirmacao(frase), Intencao.NOVO_ENDERECO)

    async def test_pedido_confirmado_com_sim_os_2_grava_o_endereco_certo(self):
        pedidos = PedidosEmMemoria()
        servico = ServicoDePedido(pedidos, SessoesEmMemoria(900.0), consulta_cep=CepsEmMemoria())
        for fala in ("gás", "p13", "2", *FALAS_ENDERECO, "pix", "sim, os 2"):
            await servico.atender(TELEFONE, Entrada(texto=fala))
        registrados = await pedidos.listar_por_telefone(TELEFONE)
        self.assertEqual(len(registrados), 1)
        self.assertEqual(registrados[0].endereco_entrega, ENDERECO)


class TesteQuantidade(unittest.TestCase):
    def test_usa_o_primeiro_numero_da_frase(self):
        self.assertEqual(validar_quantidade("2 botijões, um pra casa"), 2)
        self.assertEqual(validar_quantidade("um só, mas talvez 3 depois"), 1)

    def test_aceita_2x_e_ignora_codigo_do_botijao(self):
        self.assertEqual(validar_quantidade("2x"), 2)
        self.assertEqual(validar_quantidade("do p13, 3 por favor"), 3)


class TesteConfiguracaoEApi(unittest.TestCase):
    def test_credenciais_completas_sao_lidas_com_versao_padrao(self):
        ambiente = {"WA_APP_SECRET": "s", "WA_VERIFY_TOKEN": "t", "WA_ACCESS_TOKEN": "tok", "WA_PHONE_NUMBER_ID": "1"}
        with patch.dict(os.environ, ambiente, clear=True):
            credenciais = Configuracao.do_ambiente().credenciais_whatsapp
        self.assertEqual(credenciais, CredenciaisWhatsApp("tok", "1", "v26.0"))

    def test_repr_das_credenciais_nao_mostra_o_token(self):
        self.assertNotIn("token-secreto", repr(CredenciaisWhatsApp("token-secreto", "1")))

    def test_servidores_usam_a_api_real_quando_ha_credenciais(self):
        com = Configuracao("s", "t", credenciais_whatsapp=CredenciaisWhatsApp("tok", "123"))
        for servico in (montar_servico_de_webhook(com), montar_servico_de_webhook_com_pedido_de_gas(com)):
            self.assertIsInstance(servico._processador._whatsapp, WhatsAppCloudApi)

    def test_servidores_ficam_no_console_sem_credenciais(self):
        with self.assertLogs("revgas_atendimento.composicao", level="WARNING"):
            servico = montar_servico_de_webhook(Configuracao("s", "t"))
        self.assertIsInstance(servico._processador._whatsapp, WhatsAppEmMemoria)

    def test_rotas_nas_duas_apis_e_documentacao_desligada(self):
        # Sem TestClient (exige httpx, que não está no requirements): olha as rotas registradas.
        configuracao = Configuracao("segredo", "token")
        for fabrica in (criar_app, criar_app_com_pedido_de_gas):
            with self.subTest(app=fabrica.__name__):
                app = fabrica(configuracao)
                rotas = {rota.path: rota for rota in app.routes if isinstance(rota, APIRoute)}
                self.assertEqual(set(rotas), {"/saude", "/webhook/whatsapp", "/mensagem"})
                self.assertEqual(asyncio.run(rotas["/saude"].endpoint()), {"status": "ok"})
                self.assertIsNone(app.openapi_url)  # sem /docs nem /openapi.json expostos no túnel


if __name__ == "__main__":
    unittest.main()
