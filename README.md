# RevGás — Protótipo de Atendimento

Código-fonte original do protótipo RevGás, extraído de `Luchianni.rar`. Esta publicação é destinada ao versionamento e à demonstração, não a uma operação comercial em produção.

## O que está implementado

- Fluxo de atendimento/cadastro pelo WhatsApp, com validações de dados e confirmação.
- Interfaces de integração e adaptador de mensagens da WhatsApp Cloud API.
- Webhook HTTP construído com FastAPI; valida assinatura e token de verificação.
- Simuladores em memória para cadastros, sessões e envio de mensagens.
- Demonstração local do fluxo de cadastro e testes automatizados.

**Cliente lembrado pelo número:** o servidor guarda cadastros e pedidos em `dados/revgas.sqlite3` (mude com `REVGAS_BANCO`). Quem já se cadastrou é reconhecido pelo número do WhatsApp em qualquer pedido futuro, mesmo depois de reiniciar: o bot cumprimenta pelo nome e vai direto à confirmação com o endereço do cadastro (o cliente pode mandar o CEP de outro endereço ali mesmo, ou mandar ATUALIZAR para refazer o cadastro).

**Forma de pagamento:** depois do endereço, o bot pergunta como o cliente vai pagar (**Pix, dinheiro, cartão de débito ou de crédito**, na entrega). Em dinheiro, pergunta o troco ("troco para 100" ou "não"). Só "cartão" faz o bot perguntar débito ou crédito. O pagamento aparece no resumo, na confirmação e fica gravado no pedido; na confirmação o cliente pode trocar ("prefiro pagar no Pix"). Para mudar o "na entrega", edite `MOMENTO_DO_PAGAMENTO` em `modelos_pedido.py`.

**Prazo de cancelamento:** a confirmação avisa "Se precisar cancelar, mande CANCELAR em até 5 minutos". Dentro do prazo, CANCELAR (ou "cancela meu pedido") cancela o último pedido e o status no banco vira `CANCELADO`; depois do prazo, o bot diz há quanto tempo foi confirmado e orienta a falar com a loja. Mude o prazo com `REVGAS_PRAZO_CANCELAMENTO_MIN` (0 desliga o cancelamento pelo WhatsApp).

**Telefone validado pelo DDD:** o telefone de contato precisa ter DDD que existe (lista da Anatel), celular com 11 dígitos começando com 9 ou fixo com 10 dígitos começando com 2 a 5. Cada erro tem uma mensagem própria ("Faltou o DDD", "O DDD 20 não existe", "Parece um celular sem o 9 na frente"…). Os resumos mostram o número formatado: (11) 98888-7777.

**Endereço validado pelo CEP:** o bot pede o CEP, consulta o **ViaCEP** (serviço público e gratuito, sem chave; só o CEP sai do servidor) e mostra a rua, o bairro e a cidade achados; o cliente manda só o número e o complemento ("120 apto 3", "s/n"). O endereço gravado fica completo: `Praça da Sé, 120, apto 3 - Sé, São Paulo/SP - CEP 01001-000`. Se o cliente responder NÃO SEI, se o ViaCEP estiver fora do ar ou se o CEP for da cidade toda, o bot pede o endereço digitado, que precisa ter o número da casa. Para não consultar a internet, defina `REVGAS_CEP_ONLINE=0` (aí só o formato do CEP é conferido).

**Limites:** conversas em andamento ficam em memória (15 min) e se perdem ao reiniciar. O banco tem dados pessoais (LGPD): está fora do git, mas faça backup e restrinja o acesso. Não há integração com ERP. Testes e demos (`conversar.py`, `demo_pedido.py`) usam só memória.

## Estrutura (`revgas_atendimento/`)

| Camada | Módulos |
|---|---|
| Conversa (regras de negócio) | `atendimento.py` (cadastro), `atendimento_pedido.py` (pedido de gás), `atendimento_integrado.py` (decide quem responde), `interpretacao.py`, `validacao.py`, `validacao_pedido.py`, `texto.py` |
| Modelos e contratos | `modelos.py`, `modelos_pedido.py`, `portas.py`, `portas_pedido.py` |
| Montagem (o que é real e o que é simulado) | `composicao.py`, `composicao_pedido.py`, `config.py`, `ambiente.py` |
| Entrada HTTP | `aplicacao.py` (todas as rotas), `api.py` (só cadastro), `api_pedido.py` (completo), `webhook.py`, `automacao.py`, `erros_http.py` |
| WhatsApp e infraestrutura | `whatsapp.py`, `whatsapp_cloud.py`, `processador.py`, `deduplicador.py`, `seguranca.py`, `simulacoes*.py` |
| Armazenamento | `persistencia_sqlite.py` (cadastros e pedidos em disco) |

Validação: `validacao.py` (nome, telefone/DDD), `endereco.py` (CEP, número, coleta do endereço) e `cep_viacep.py` (consulta ao ViaCEP).

Fora do pacote:
- `tests/`: testes automatizados, um arquivo por assunto (`test_atendimento.py`, `test_pedido.py`, `test_validacao.py`, `test_persistencia.py`…). Dados compartilhados em `tests/apoio.py`.
- `n8n/revgas_whatsapp.json`: fluxo para importar no n8n.
- Na raiz: demos (`conversar.py`, `demo_pedido.py`) e o teste de ponta a ponta contra o servidor rodando (`testar_webhook.py`).

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

As variáveis ficam no ambiente ou em um `.env` na raiz (veja `.env.example`; variáveis do ambiente têm prioridade). Há dois modos, use um por número de WhatsApp:

- **Webhook direto da Meta**: `WA_APP_SECRET` + `WA_VERIFY_TOKEN` (recebe e valida a assinatura) e, para responder de verdade, `WA_ACCESS_TOKEN` + `WA_PHONE_NUMBER_ID` (sem elas, as respostas só aparecem no terminal).
- **n8n**: só `N8N_API_KEY`. O n8n recebe e envia; o Python responde em `POST /mensagem`. Passo a passo em [README_N8N.md](README_N8N.md).

```bash
uvicorn revgas_atendimento.api_pedido:criar_app_com_pedido_de_gas --factory --host 127.0.0.1 --port 8000
```

Texto de exemplo esquecido no `.env` (`COLE_…`, `defina_…`) faz o servidor recusar a partida com uma mensagem dizendo qual variável falta, sem mostrar o valor. A documentação automática (`/docs`) fica desligada, porque o servidor é exposto pelo túnel.

## Testes

```bash
python -m unittest discover -v
```

Resultado atual: 166 testes passam. Um arquivo só: `python -m unittest -v tests.test_validacao`. Os testes não acessam a internet (o CEP usa `CepsEmMemoria`, e o adaptador do ViaCEP é testado contra um servidor falso local).

Com o servidor rodando, `python testar_webhook.py` faz um teste de ponta a ponta (rota `/saude`, verificação, assinatura e uma conversa completa).

## Segurança

O repositório deve conter somente exemplos fictícios de credenciais; nunca envie `.env`, tokens reais, chaves privadas, logs com dados pessoais ou arquivos do ambiente virtual. Se alguma credencial real tiver sido exposta, revogue ou substitua no serviço responsável.

## Próximas evoluções (não implementadas)

Persistência durável de dados, integração operacional com WhatsApp Business Platform, pedido expresso, IA conversacional, painel de pedidos, encaminhamento humano e acompanhamento de entregas. Planeje e teste essas mudanças em branches separadas.
