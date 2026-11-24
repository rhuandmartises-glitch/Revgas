"""Segredos nunca aparecem em texto, e o .env não vaza para o ambiente do processo.
Rodar: python -m unittest -v tests.test_segredos"""
from __future__ import annotations

import logging
import os
import pickle
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from revgas_atendimento.ambiente import ler_arquivo_env, variaveis_do_servidor
from revgas_atendimento.config import Configuracao, CredenciaisWhatsApp
from revgas_atendimento.segredo import Segredo
from revgas_atendimento.whatsapp_cloud import WhatsAppCloudApi

VALOR = "EAAB-valor-que-nao-pode-vazar"


class TesteSegredo(unittest.TestCase):
    def test_nao_aparece_em_nenhuma_forma_de_texto(self):
        segredo = Segredo(VALOR)
        for texto in (str(segredo), repr(segredo), f"{segredo}", f"{segredo!r}", "%s" % segredo, f"{segredo:>40}"):
            with self.subTest(texto=texto):
                self.assertNotIn(VALOR, texto)
        self.assertEqual(segredo.revelar(), VALOR)

    def test_nao_aparece_no_log(self):
        with self.assertLogs("teste.segredo", level="INFO") as capturado:
            logging.getLogger("teste.segredo").info("config: %s %r", Segredo(VALOR), Segredo(VALOR))
        self.assertNotIn(VALOR, "\n".join(capturado.output))

    def test_comparacao_e_bloqueio_de_pickle(self):
        self.assertTrue(Segredo(VALOR).confere(VALOR))
        self.assertFalse(Segredo(VALOR).confere("outro"))
        self.assertEqual(Segredo(VALOR), Segredo(VALOR))
        with self.assertRaises(TypeError):
            pickle.dumps(Segredo(VALOR))
        with self.assertRaises(ValueError):
            Segredo("")

    def test_configuracao_inteira_nao_mostra_nenhum_segredo(self):
        configuracao = Configuracao(
            VALOR + "1", VALOR + "2",
            credenciais_whatsapp=CredenciaisWhatsApp(VALOR + "3", "123"),
            chave_api_automacao=VALOR + "4",
        )
        for texto in (repr(configuracao), str(configuracao), f"{configuracao}"):
            self.assertNotIn(VALOR, texto)
        self.assertIsInstance(configuracao.chave_api_automacao, Segredo)

    def test_cliente_do_whatsapp_logado_nao_mostra_o_token(self):
        cliente = WhatsAppCloudApi(VALOR, "123", "v26.0")
        self.assertNotIn(VALOR, repr(vars(cliente)))


class TesteArquivoEnvSemVazarParaOProcesso(unittest.TestCase):
    def setUp(self) -> None:
        self._pasta = tempfile.TemporaryDirectory()
        self.caminho = Path(self._pasta.name) / ".env"
        self.caminho.write_text(f"N8N_API_KEY={VALOR}\nREVGAS_BANCO=do-arquivo.db\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._pasta.cleanup()

    def test_le_o_arquivo_sem_mexer_em_os_environ(self):
        with patch.dict(os.environ, {}, clear=True):
            configuracao = Configuracao.do_ambiente(variaveis_do_servidor(self.caminho))
            self.assertNotIn("N8N_API_KEY", os.environ)  # nada copiado para o processo
        self.assertTrue(configuracao.chave_api_automacao.confere(VALOR))

    def test_variavel_do_sistema_ganha_do_arquivo(self):
        with patch.dict(os.environ, {"REVGAS_BANCO": "do-sistema.db"}, clear=True):
            self.assertEqual(variaveis_do_servidor(self.caminho)["REVGAS_BANCO"], "do-sistema.db")
        self.assertEqual(ler_arquivo_env(self.caminho)["REVGAS_BANCO"], "do-arquivo.db")


if __name__ == "__main__":
    unittest.main()
