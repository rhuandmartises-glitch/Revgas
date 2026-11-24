"""Testes da conversa de cadastro. Rodar: python -m unittest -v tests.test_atendimento"""
from __future__ import annotations

import unittest

from revgas_atendimento.atendimento import (
    BOTAO_CONFIRMAR,
    BOTAO_CORRIGIR,
    MENSAGEM_FALHA_TECNICA,
    ServicoDeAtendimento,
)
from revgas_atendimento.modelos import (
    Botao,
    Cadastro,
    Entrada,
    Etapa,
    IntegracaoError,
    Resposta,
)
from revgas_atendimento.processador import ProcessadorWhatsApp
from revgas_atendimento.simulacoes import (
    CadastrosEmMemoria,
    CepsEmMemoria,
    SessoesEmMemoria,
    WhatsAppEmMemoria,
    evento_de_texto,
)
from tests.apoio import (
    ENDERECO,
    FALAS_ENDERECO,
    FALAS_OUTRO_ENDERECO,
    OUTRO_ENDERECO,
    TELEFONE,
    TELEFONE_CONTATO,
    TELEFONE_CONTATO_FORMATADO,
    TTL,
    RelogioFalso,
)


class CadastrosInstaveis(CadastrosEmMemoria):
    """Falha na primeira gravação, como um ERP fora do ar."""

    def __init__(self) -> None:
        super().__init__()
        self.falhas_restantes = 1

    async def salvar(self, cadastro: Cadastro) -> None:
        if self.falhas_restantes > 0:
            self.falhas_restantes -= 1
            raise IntegracaoError("ERP indisponível")
        await super().salvar(cadastro)


class Conversa:
    def __init__(self, cadastros: CadastrosEmMemoria | None = None) -> None:
        self.relogio = RelogioFalso()
        self.cadastros = cadastros or CadastrosEmMemoria()
        self.sessoes = SessoesEmMemoria(TTL, self.relogio)
        self.ceps = CepsEmMemoria()
        self.servico = ServicoDeAtendimento(self.cadastros, self.sessoes, self.ceps)

    async def texto(self, *textos: str) -> Resposta:
        resposta = None
        for texto in textos:
            resposta = await self.servico.atender(TELEFONE, Entrada(texto=texto))
        return resposta

    async def botao(self, botao_id: str) -> Resposta:
        return await self.servico.atender(TELEFONE, Entrada(botao_id=botao_id))

    async def ate_a_confirmacao(self) -> Resposta:
        return await self.texto("oi", "Maria da Silva", TELEFONE_CONTATO, *FALAS_ENDERECO)

    async def etapa(self) -> Etapa:
        return (await self.sessoes.obter(TELEFONE)).etapa


class TesteFluxoDeCadastro(unittest.IsolatedAsyncioTestCase):
    async def test_fluxo_completo_salva_dados_normalizados(self):
        conversa = Conversa()
        primeira = await conversa.texto("oi")
        self.assertIn("nome completo", primeira.texto)
        await conversa.texto("  maria   da silva ", "(11) 98888-7777")
        achado = await conversa.texto("01001000")
        self.assertIn("Achei: Praça da Sé - Sé, São Paulo/SP", achado.texto)
        resumo = await conversa.texto("120")
        self.assertEqual(resumo.botoes, ())  # sem botões: o cliente responde em texto
        self.assertIn("SIM", resumo.texto)
        self.assertIn(TELEFONE_CONTATO_FORMATADO, resumo.texto)

        await conversa.botao(BOTAO_CONFIRMAR)

        esperado = Cadastro(TELEFONE, "maria da silva", TELEFONE_CONTATO, ENDERECO)
        self.assertEqual(await conversa.cadastros.buscar_por_telefone(TELEFONE), esperado)
        self.assertIsNone(await conversa.sessoes.obter(TELEFONE))

    async def test_confirmar_digitando_sim_tambem_funciona(self):
        conversa = Conversa()
        await conversa.ate_a_confirmacao()
        await conversa.texto("Sim")
        self.assertIsNotNone(await conversa.cadastros.buscar_por_telefone(TELEFONE))

    async def test_telefone_invalido_nao_avanca_e_pede_de_novo(self):
        conversa = Conversa()
        await conversa.texto("oi", "Maria da Silva")
        resposta = await conversa.texto("123")
        self.assertIn("telefone", resposta.texto)
        self.assertEqual(await conversa.etapa(), Etapa.TELEFONE)

    async def test_nome_com_numero_e_rejeitado(self):
        conversa = Conversa()
        await conversa.texto("oi")
        resposta = await conversa.texto("Joao123")
        self.assertIn("nome", resposta.texto)
        self.assertEqual(await conversa.etapa(), Etapa.NOME)

    async def test_endereco_sem_cep_pede_o_cep(self):
        conversa = Conversa()
        await conversa.texto("oi", "Maria da Silva", TELEFONE_CONTATO)
        resposta = await conversa.texto("Rua A")
        self.assertIn("CEP", resposta.texto)
        self.assertEqual(await conversa.etapa(), Etapa.ENDERECO)

    async def test_mensagem_sem_texto_repete_a_pergunta_atual(self):
        conversa = Conversa()
        await conversa.texto("oi")
        resposta = await conversa.servico.atender(TELEFONE, Entrada())
        self.assertIn("nome completo", resposta.texto)

    async def test_mensagem_sem_texto_na_etapa_do_numero_repete_a_rua_achada(self):
        conversa = Conversa()
        await conversa.texto("oi", "Maria da Silva", TELEFONE_CONTATO, "01001-000")
        resposta = await conversa.servico.atender(TELEFONE, Entrada())
        self.assertIn("Praça da Sé", resposta.texto)


class TesteConfirmacaoDoCadastro(unittest.IsolatedAsyncioTestCase):
    async def test_mandar_cep_novo_troca_so_o_endereco(self):
        conversa = Conversa()
        await conversa.ate_a_confirmacao()
        achado = await conversa.texto(FALAS_OUTRO_ENDERECO[0])
        self.assertIn("Avenida Paulista", achado.texto)
        resumo = await conversa.texto(FALAS_OUTRO_ENDERECO[1])
        self.assertIn(OUTRO_ENDERECO, resumo.texto)

        await conversa.texto("sim")

        cadastro = await conversa.cadastros.buscar_por_telefone(TELEFONE)
        self.assertEqual(cadastro.endereco, OUTRO_ENDERECO)
        self.assertEqual((cadastro.nome, cadastro.telefone_contato), ("Maria da Silva", TELEFONE_CONTATO))

    async def test_endereco_sem_cep_na_confirmacao_pede_o_cep(self):
        conversa = Conversa()
        await conversa.ate_a_confirmacao()
        resposta = await conversa.texto("Avenida Brasil, 500 - Jardim América")
        self.assertIn("CEP do endereço certo", resposta.texto)
        self.assertEqual(await conversa.etapa(), Etapa.ENDERECO)

    async def test_nao_pede_o_cep_certo_sem_apagar_nada(self):
        conversa = Conversa()
        await conversa.ate_a_confirmacao()
        resposta = await conversa.texto("não")
        self.assertIn("CEP do endereço certo", resposta.texto)
        sessao = await conversa.sessoes.obter(TELEFONE)
        self.assertEqual((sessao.etapa, sessao.nome), (Etapa.ENDERECO, "Maria da Silva"))

    async def test_confirmar_em_frase_natural_nao_vira_endereco(self):
        conversa = Conversa()
        await conversa.ate_a_confirmacao()
        await conversa.texto("sim, pode confirmar")
        cadastro = await conversa.cadastros.buscar_por_telefone(TELEFONE)
        self.assertEqual(cadastro.endereco, ENDERECO)

    async def test_refazer_recomeca_do_nome(self):
        conversa = Conversa()
        await conversa.ate_a_confirmacao()
        resposta = await conversa.texto("refazer")
        self.assertIn("nome completo", resposta.texto)


class TesteControleDoCliente(unittest.IsolatedAsyncioTestCase):
    async def test_cancelar_descarta_tudo_sem_gravar_nada(self):
        conversa = Conversa()
        await conversa.texto("oi", "Maria da Silva")
        resposta = await conversa.texto("CANCELAR")
        self.assertIn("não guardei nenhum dado", resposta.texto)
        self.assertIsNone(await conversa.sessoes.obter(TELEFONE))
        self.assertIsNone(await conversa.cadastros.buscar_por_telefone(TELEFONE))

    async def test_cancelar_tambem_vale_no_meio_do_endereco(self):
        conversa = Conversa()
        await conversa.texto("oi", "Maria da Silva", TELEFONE_CONTATO, "01001-000")
        resposta = await conversa.texto("cancelar")
        self.assertIn("não guardei nenhum dado", resposta.texto)

    async def test_corrigir_recomeca_do_nome_sem_dados_antigos(self):
        conversa = Conversa()
        await conversa.ate_a_confirmacao()
        await conversa.botao(BOTAO_CORRIGIR)
        sessao = await conversa.sessoes.obter(TELEFONE)
        self.assertEqual(sessao.etapa, Etapa.NOME)
        self.assertIsNone(sessao.nome)

    async def test_sessao_abandonada_expira_e_a_conversa_recomeca(self):
        conversa = Conversa()
        await conversa.texto("oi", "Maria da Silva")
        conversa.relogio.agora += TTL + 1

        resposta = await conversa.texto(TELEFONE_CONTATO)

        self.assertIn("nome completo", resposta.texto)
        sessao = await conversa.sessoes.obter(TELEFONE)
        self.assertEqual(sessao.etapa, Etapa.NOME)
        self.assertIsNone(sessao.nome)

    async def test_cliente_ja_cadastrado_so_reinicia_com_atualizar(self):
        cadastros = CadastrosEmMemoria()
        await cadastros.salvar(Cadastro(TELEFONE, "Maria da Silva", TELEFONE_CONTATO, ENDERECO))
        conversa = Conversa(cadastros)

        aviso = await conversa.texto("oi")
        self.assertIn("já está completo", aviso.texto)
        self.assertIsNone(await conversa.sessoes.obter(TELEFONE))

        inicio = await conversa.texto("atualizar")
        self.assertIn("atualizar seus dados", inicio.texto)
        self.assertEqual(await conversa.etapa(), Etapa.NOME)


class TesteFalhasEProcessador(unittest.IsolatedAsyncioTestCase):
    async def test_falha_do_erp_mantem_a_sessao_para_nova_tentativa(self):
        conversa = Conversa(CadastrosInstaveis())
        await conversa.ate_a_confirmacao()

        with self.assertRaises(IntegracaoError):
            await conversa.botao(BOTAO_CONFIRMAR)
        self.assertEqual(await conversa.etapa(), Etapa.CONFIRMACAO)

        await conversa.botao(BOTAO_CONFIRMAR)
        self.assertIsNotNone(await conversa.cadastros.buscar_por_telefone(TELEFONE))

    async def test_consulta_de_cep_fora_do_ar_pede_o_endereco_digitado(self):
        conversa = Conversa()
        conversa.ceps.fora_do_ar = True
        await conversa.texto("oi", "Maria da Silva", TELEFONE_CONTATO)
        resposta = await conversa.texto("01001-000")
        self.assertIn("Não consegui consultar o CEP", resposta.texto)
        resumo = await conversa.texto("Praça da Sé, 120 - Sé")
        self.assertIn("Praça da Sé, 120 - Sé - CEP 01001-000", resumo.texto)

    async def test_webhook_repetido_e_respondido_uma_unica_vez(self):
        whatsapp = WhatsAppEmMemoria(imprimir=False)
        conversa = Conversa()
        processador = ProcessadorWhatsApp(conversa.servico, whatsapp)
        evento = evento_de_texto(TELEFONE, "oi")

        await processador.processar(evento)
        await processador.processar(evento)

        self.assertEqual(len(whatsapp.enviadas), 1)

    async def test_erro_inesperado_gera_mensagem_amigavel(self):
        class ServicoQuebrado:
            async def atender(self, telefone: str, entrada: Entrada) -> Resposta:
                raise RuntimeError("falha qualquer")

        whatsapp = WhatsAppEmMemoria(imprimir=False)
        processador = ProcessadorWhatsApp(ServicoQuebrado(), whatsapp)

        with self.assertLogs("revgas_atendimento.processador", level="ERROR"):
            await processador.processar(evento_de_texto(TELEFONE, "oi"))

        _, mensagem = whatsapp.enviadas[-1]
        self.assertEqual(mensagem["text"]["body"], MENSAGEM_FALHA_TECNICA)

    def test_botao_com_titulo_acima_do_limite_do_whatsapp_e_rejeitado(self):
        with self.assertRaises(ValueError):
            Botao("X", "Um título bem comprido demais")


if __name__ == "__main__":
    unittest.main()
