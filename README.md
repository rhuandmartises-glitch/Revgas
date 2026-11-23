# RevGás — Protótipo de Atendimento

Código-fonte original do protótipo RevGás, extraído de `Luchianni.rar`. Esta publicação é destinada ao versionamento e à demonstração, não a uma operação comercial em produção.

## O que está implementado

- Fluxo de atendimento/cadastro pelo WhatsApp, com validações de dados e confirmação.
- Interfaces de integração e adaptador de mensagens da WhatsApp Cloud API.
- Webhook HTTP construído com FastAPI; valida assinatura e token de verificação.
- Simuladores em memória para cadastros, sessões e envio de mensagens.
- Demonstração local do fluxo de cadastro e testes automatizados.

**Limites importantes:** a montagem padrão de `revgas_atendimento/api.py` usa simuladores e **não envia respostas reais pelo WhatsApp**; os dados em memória são perdidos após reiniciar. O código entregue não constitui um sistema de pedidos de gás e entregas já implementado. Há um erro conhecido de importação em `revgas_atendimento/test_webhook.py` (`CredenciaisWhatsApp` ausente de `config.py`).

## Estrutura

- `revgas_atendimento/`: núcleo de atendimento, modelos, validações, webhook, API HTTP, adaptadores WhatsApp, simulações e testes.
- `ambiente.py`, `composicao.py`, `seguranca.py`: arquivos presentes na raiz do original, mantidos sem refatoração.
- `test_atendimento.py`, `test_seguranca.py`: testes adicionais do protótipo.
- `requirements.txt`: dependências declaradas (`fastapi`, `uvicorn[standard]`).

## Executar localmente

Requer Python 3.11+ (versão utilizada no ambiente virtual do arquivo original). Em terminal na raiz:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m revgas_atendimento
```

## Ambiente HTTP de demonstração

Configure `WA_APP_SECRET` e `WA_VERIFY_TOKEN` conforme `.env.example` (o Python não carrega `.env` automaticamente sem biblioteca adicional). Em seguida, é possível iniciar uma aplicação de desenvolvimento, por exemplo:

```bash
uvicorn revgas_atendimento.api:criar_app --factory --host 127.0.0.1 --port 8000
```

Esse servidor **não é uma integração operacional** com a Meta: seu adaptador padrão de saída é `WhatsAppEmMemoria`. Não exponha o servidor na internet nem use credenciais reais sem revisar implantação, armazenamento, tratamento de eventos e permissões.

## Testes

```bash
python -m unittest discover -v
```

Resultado observado durante a preparação: 36 testes passaram; um módulo (`revgas_atendimento.test_webhook`) não carregou devido à importação de `CredenciaisWhatsApp`. Nenhuma correção funcional foi aplicada nesta publicação.

## Segurança

O repositório deve conter somente exemplos fictícios de credenciais; nunca envie `.env`, tokens reais, chaves privadas, logs com dados pessoais ou arquivos do ambiente virtual. Se alguma credencial real tiver sido exposta, revogue ou substitua no serviço responsável.

## Próximas evoluções (não implementadas)

Persistência durável de dados, integração operacional com WhatsApp Business Platform, pedido expresso, IA conversacional, painel de pedidos, encaminhamento humano e acompanhamento de entregas. Planeje e teste essas mudanças em branches separadas.
