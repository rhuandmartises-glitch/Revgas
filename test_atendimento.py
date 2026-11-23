"""Testes da conversa de cadastro. Rodar: python -m unittest -v test_atendimento"""
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
    SessoesEmMemoria,
    WhatsAppEmMemoria,
    evento_de_texto,
)

TELEFONE = "5511999990000"
TTL = 900.0


class RelogioFalso:
    def __init__(self) -> None:
        self.agora = 0.0

    def __call__(self) -> float:
        return self.agora


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
        self.servico = ServicoDeAtendimento(self.cadastros, self.sessoes)

    async def texto(self, texto: str) -> Resposta:
        return await self.servico.atender(TELEFONE, Entrada(texto=texto))

    async def botao(self, botao_id: str) -> Resposta:
        return await self.servico.atender(TELEFONE, Entrada(botao_id=botao_id))

    async def ate_a_confirmacao(self) -> Resposta:
        await self.texto("oi")
        await self.texto("Maria da Silva")
        await self.texto("maria@email.com")
        return await self.texto("Rua das Flores, 120 - Centro")


class TesteFluxoDeCadastro(unittest.IsolatedAsyncioTestCase):
    async def test_fluxo_completo_salva_dados_normalizados(self):
        conversa = Conversa()
        primeira = await conversa.texto("oi")
        self.assertIn("nome completo", primeira.texto)
        await conversa.texto("  maria   da silva ")
        await conversa.texto("Maria@Email.com")
        resumo = await conversa.texto("Rua das  Flores, 120 - Centro")
        self.assertEqual([b.id for b in resumo.botoes], [BOTAO_CONFIRMAR, BOTAO_CORRIGIR])

        await conversa.botao(BOTAO_CONFIRMAR)

        esperado = Cadastro(TELEFONE, "maria da silva", "maria@email.com", "Rua das Flores, 120 - Centro")
        self.assertEqual(await conversa.cadastros.buscar_por_telefone(TELEFONE), esperado)
        self.assertIsNone(await conversa.sessoes.obter(TELEFONE))

    async def test_confirmar_digitando_sim_tambem_funciona(self):
        conversa = Conversa()
        await conversa.ate_a_confirmacao()
        await conversa.texto("Sim")
        self.assertIsNotNone(await conversa.cadastros.buscar_por_telefone(TELEFONE))

    async def test_email_invalido_nao_avanca_e_pede_de_novo(self):
        conversa = Conversa()
        await conversa.texto("oi")
        await conversa.texto("Maria da Silva")
        resposta = await conversa.texto("isso nao e email")
        self.assertIn("e-mail", resposta.texto)
        self.assertEqual((await conversa.sessoes.obter(TELEFONE)).etapa, Etapa.EMAIL)

    async def test_nome_com_numero_e_rejeitado(self):
        conversa = Conversa()
        await conversa.texto("oi")
        resposta = await conversa.texto("Joao123")
        self.assertIn("nome", resposta.texto)
        self.assertEqual((await conversa.sessoes.obter(TELEFONE)).etapa, Etapa.NOME)

    async def test_endereco_curto_demais_e_rejeitado(self):
        conversa = Conversa()
        await conversa.texto("oi")
        await conversa.texto("Maria da Silva")
        await conversa.texto("maria@email.com")
        resposta = await conversa.texto("Rua A")
        self.assertIn("endereço", resposta.texto)
        self.assertEqual((await conversa.sessoes.obter(TELEFONE)).etapa, Etapa.ENDERECO)

    async def test_mensagem_sem_texto_repete_a_pergunta_atual(self):
        conversa = Conversa()
        await conversa.texto("oi")
        resposta = await conversa.servico.atender(TELEFONE, Entrada())
        self.assertIn("nome completo", resposta.texto)


class TesteControleDoCliente(unittest.IsolatedAsyncioTestCase):
    async def test_cancelar_descarta_tudo_sem_gravar_nada(self):
        conversa = Conversa()
        await conversa.texto("oi")
        await conversa.texto("Maria da Silva")
        resposta = await conversa.texto("CANCELAR")
        self.assertIn("não guardei nenhum dado", resposta.texto)
        self.assertIsNone(await conversa.sessoes.obter(TELEFONE))
        self.assertIsNone(await conversa.cadastros.buscar_por_telefone(TELEFONE))

    async def test_corrigir_recomeca_do_nome_sem_dados_antigos(self):
        conversa = Conversa()
        await conversa.ate_a_confirmacao()
        await conversa.botao(BOTAO_CORRIGIR)
        sessao = await conversa.sessoes.obter(TELEFONE)
        self.assertEqual(sessao.etapa, Etapa.NOME)
        self.assertIsNone(sessao.nome)

    async def test_sessao_abandonada_expira_e_a_conversa_recomeca(self):
        conversa = Conversa()
        await conversa.texto("oi")
        await conversa.texto("Maria da Silva")
        conversa.relogio.agora += TTL + 1

        resposta = await conversa.texto("maria@email.com")

        self.assertIn("nome completo", resposta.texto)
        sessao = await conversa.sessoes.obter(TELEFONE)
        self.assertEqual(sessao.etapa, Etapa.NOME)
        self.assertIsNone(sessao.nome)

    async def test_cliente_ja_cadastrado_so_reinicia_com_atualizar(self):
        cadastros = CadastrosEmMemoria()
        await cadastros.salvar(Cadastro(TELEFONE, "Maria da Silva", "m@x.com", "Rua das Flores, 120"))
        conversa = Conversa(cadastros)

        aviso = await conversa.texto("oi")
        self.assertIn("já está completo", aviso.texto)
        self.assertIsNone(await conversa.sessoes.obter(TELEFONE))

        inicio = await conversa.texto("atualizar")
        self.assertIn("atualizar seus dados", inicio.texto)
        self.assertEqual((await conversa.sessoes.obter(TELEFONE)).etapa, Etapa.NOME)


class TesteFalhasEProcessador(unittest.IsolatedAsyncioTestCase):
    async def test_falha_do_erp_mantem_a_sessao_para_nova_tentativa(self):
        conversa = Conversa(CadastrosInstaveis())
        await conversa.ate_a_confirmacao()

        with self.assertRaises(IntegracaoError):
            await conversa.botao(BOTAO_CONFIRMAR)
        self.assertEqual((await conversa.sessoes.obter(TELEFONE)).etapa, Etapa.CONFIRMACAO)

        await conversa.botao(BOTAO_CONFIRMAR)
        self.assertIsNotNone(await conversa.cadastros.buscar_por_telefone(TELEFONE))

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
