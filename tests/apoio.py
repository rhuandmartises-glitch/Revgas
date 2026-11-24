"""Dados e atalhos compartilhados pelos testes (sem testes aqui dentro)."""
from __future__ import annotations

TELEFONE = "5511999990000"  # número do WhatsApp que manda as mensagens
TTL = 900.0

# Telefone de contato válido (DDD 11, celular) e como aparece nos resumos.
TELEFONE_CONTATO = "11988887777"
TELEFONE_CONTATO_FORMATADO = "(11) 98888-7777"

# Endereço pelo CEP, com CepsEmMemoria: 01001-000 é a Praça da Sé.
FALAS_ENDERECO = ("01001-000", "120")
ENDERECO = "Praça da Sé, 120 - Sé, São Paulo/SP - CEP 01001-000"

# Outro endereço, para testes de troca: 01310-100 é a Avenida Paulista.
FALAS_OUTRO_ENDERECO = ("01310-100", "500")
OUTRO_ENDERECO = "Avenida Paulista, 500 - Bela Vista, São Paulo/SP - CEP 01310-100"

PAGAMENTO = "pix"  # resposta à pergunta da forma de pagamento

FALAS_CADASTRO = ("oi", "Maria da Silva", TELEFONE_CONTATO, *FALAS_ENDERECO, "sim")


class RelogioFalso:
    def __init__(self) -> None:
        self.agora = 0.0

    def __call__(self) -> float:
        return self.agora
