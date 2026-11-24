#!/usr/bin/env bash
# Cria o ambiente virtual (.venv) e instala as dependências do projeto.
# Uso, na raiz do projeto:  bash configurar_ambiente.sh
set -e

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo
echo "Pronto. Para usar o ambiente nesta janela: source .venv/bin/activate"
echo "Para rodar os testes:                      python -m unittest discover -v"
echo "Para rodar a demo de cadastro:              python -m revgas_atendimento"
echo "Para rodar a demo de pedido de gás:         python demo_pedido.py"
