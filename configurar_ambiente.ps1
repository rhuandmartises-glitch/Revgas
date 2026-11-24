# Cria o ambiente virtual (.venv) e instala as dependências do projeto.
# Uso, na raiz do projeto:  .\configurar_ambiente.ps1
$ErrorActionPreference = "Stop"

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

Write-Host ""
Write-Host "Pronto. Para usar o ambiente nesta janela: .\.venv\Scripts\Activate.ps1"
Write-Host "Para rodar os testes:                      python -m unittest discover -v"
Write-Host "Para rodar a demo de cadastro:              python -m revgas_atendimento"
Write-Host "Para rodar a demo de pedido de gás:         python demo_pedido.py"
