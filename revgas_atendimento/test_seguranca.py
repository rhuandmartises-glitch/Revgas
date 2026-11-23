"""Testes das proteções de segredos e do webhook. Rodar: python -m unittest -v test_seguranca"""
from __future__ import annotations

import unittest

from revgas_atendimento.config import Configuracao
from revgas_atendimento.modelos import Cadastro
from revgas_atendimento.seguranca import assinatura_valida, tokens_iguais

SEGREDO = "segredo"
CORPO = b'{"a":1}'
# Valor de referência gerado de forma independente, com: openssl dgst -sha256 -hmac segredo
ASSINATURA_CORRETA = "sha256=d74ec81e38acd14dea41865e84bfb51d4ed99dd9042fc82a87534890ac2bb655"


class TesteAssinaturaDoWebhook(unittest.TestCase):
    def test_assinatura_correta_e_aceita(self):
        self.assertTrue(assinatura_valida(SEGREDO, CORPO, ASSINATURA_CORRETA))

    def test_corpo_adulterado_e_recusado(self):
        self.assertFalse(assinatura_valida(SEGREDO, b'{"a":2}', ASSINATURA_CORRETA))

    def test_segredo_errado_e_recusado(self):
        self.assertFalse(assinatura_valida("outro-segredo", CORPO, ASSINATURA_CORRETA))

    def test_cabecalho_ausente_ou_sem_prefixo_e_recusado(self):
        self.assertFalse(assinatura_valida(SEGREDO, CORPO, ""))
        self.assertFalse(assinatura_valida(SEGREDO, CORPO, ASSINATURA_CORRETA.removeprefix("sha256=")))

    def test_cabecalho_com_caracteres_nao_ascii_nao_quebra(self):
        self.assertFalse(assinatura_valida(SEGREDO, CORPO, "sha256=çãõ"))

    def test_comparacao_de_tokens(self):
        self.assertTrue(tokens_iguais("abc", "abc"))
        self.assertFalse(tokens_iguais("abc", "abd"))
        self.assertFalse(tokens_iguais("abc", ""))


class TesteVazamentoEmRepr(unittest.TestCase):
    def test_repr_da_configuracao_nao_mostra_segredos(self):
        texto = repr(Configuracao("segredo-super-secreto", "token-super-secreto"))
        self.assertNotIn("segredo-super-secreto", texto)
        self.assertNotIn("token-super-secreto", texto)

    def test_repr_do_cadastro_nao_mostra_dados_pessoais(self):
        texto = repr(Cadastro("5511999990000", "Maria da Silva", "maria@email.com", "Rua das Flores, 120"))
        for dado in ("5511999990000", "Maria", "maria@email.com", "Rua das Flores"):
            self.assertNotIn(dado, texto)


if __name__ == "__main__":
    unittest.main()
