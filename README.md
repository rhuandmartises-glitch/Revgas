# RevGás: protótipo de atendimento

Bot de WhatsApp da RevGás para cadastro de clientes e pedido de botijão de gás. É um protótipo para versionar e demonstrar, não um sistema pronto para operar a loja. O código veio de `Luchianni.rar`.

## O que o bot faz

- Cadastra o cliente: nome, telefone de contato e endereço.
- Recebe pedidos de botijão (P13, P20 ou P45, de 1 a 6 unidades), com forma de pagamento e confirmação.
- Lembra o cliente pelo número do WhatsApp. Quem já tem cadastro não precisa informar o endereço de novo.
- Recebe mensagens direto da Meta (webhook) ou por meio do n8n.

### Cliente lembrado pelo número

Cadastros e pedidos ficam em `dados/revgas.sqlite3` (mude com `REVGAS_BANCO`). Quando um número já cadastrado pede gás, o bot cumprimenta pelo nome e usa o endereço do cadastro, mesmo depois de o servidor reiniciar. Na confirmação, o cliente pode mandar o CEP de outro endereço. Para refazer o cadastro, basta dizer que quer mudar os dados ("quero mudar meu endereço", "atualizar").

### Sem palavras obrigatórias

O bot não pede para o cliente digitar uma palavra exata. Ele entende os jeitos comuns de dizer a mesma coisa, sem depender de acento, maiúscula ou pontuação:

| O cliente quer | Exemplos que funcionam |
|---|---|
| Confirmar | "sim", "pode mandar", "tá certo", "fechado", "beleza", "isso mesmo", "👍" |
| Dizer que está errado | "não", "tá errado", "mudou", "quero trocar" |
| Desistir | "cancela", "desisto", "deixa pra lá", "não quero mais", "mudei de ideia", "para" |
| Não sabe o CEP | "não sei", "sei lá", "não lembro", "esqueci", "não tenho" |
| Recomeçar | "refazer", "começar de novo", "do zero", "corrigir" |
| Mudar o cadastro | "atualizar", "quero mudar meu endereço", "trocar meus dados" |
| Dispensar o troco | "não", "não precisa", "sem troco", "vou dar certinho", "tenho trocado" |
| Casa sem número | "s/n", "sem número", "não tem número" |
| Começar um pedido | "gás", "quero um botijão", "bujão", "quero pedir" |

As listas ficam em `revgas_atendimento/intencoes.py`. Para ensinar um jeito novo, é só acrescentar a palavra ou a frase ali. Na etapa do nome, só a frase inteira cancela, porque há sobrenomes como "Cancela".

### Telefone

O telefone de contato precisa ter um DDD que existe (lista da Anatel). Celular tem 11 dígitos e começa com 9 depois do DDD. Fixo tem 10 dígitos e começa com 2, 3, 4 ou 5. Cada erro tem uma mensagem própria, como "Faltou o DDD" ou "O DDD 20 não existe". Nos resumos, o número aparece formatado: (11) 98888-7777.

### Endereço

O bot pede o CEP e consulta o ViaCEP, que é público, gratuito e não exige chave. Só o CEP sai do servidor. Com a rua achada, o cliente manda o número e o complemento ("120 apto 3", "s/n"). O endereço é gravado completo, por exemplo `Praça da Sé, 120, apto 3 - Sé, São Paulo/SP - CEP 01001-000`.

Se o cliente não souber o CEP, se o ViaCEP estiver fora do ar ou se o CEP for de uma cidade inteira, o bot pede o endereço digitado, e ele precisa ter o número da casa. Com `REVGAS_CEP_ONLINE=0`, o bot não consulta a internet e confere só o formato do CEP.

### Pagamento

Depois do endereço, o bot pergunta como o cliente vai pagar na entrega: Pix, dinheiro, cartão de débito ou de crédito. Em dinheiro, pergunta o troco ("troco para 100" ou "não"). Se o cliente disser só "cartão", o bot pergunta se é débito ou crédito. Na confirmação, dá para trocar a forma ("prefiro pagar no Pix"). O texto "na entrega" fica em `MOMENTO_DO_PAGAMENTO`, no `modelos_pedido.py`.

### Cancelamento

A confirmação avisa: "Se mudar de ideia, dá para cancelar por aqui em até 5 minutos". Dentro do prazo, qualquer jeito de desistir ("cancela", "desisti", "não quero mais") cancela o último pedido, e o status no banco passa a `CANCELADO`. Depois do prazo, o bot diz há quanto tempo o pedido foi confirmado e pede para o cliente falar com a loja. O prazo fica em `REVGAS_PRAZO_CANCELAMENTO_MIN` (0 desliga o cancelamento pelo WhatsApp).

### Limites

- A conversa em andamento fica em memória por 15 minutos e se perde quando o servidor reinicia. O que já foi confirmado fica no banco.
- O banco guarda nome, telefone e endereço de clientes (LGPD). Ele fica fora do git, mas precisa de backup e de acesso restrito.
- Não há integração com ERP.
- Testes e demos (`conversar.py`, `demo_pedido.py`) usam só memória.

## Simulador (chat parecido com o WhatsApp)

```powershell
.\.venv\Scripts\python.exe -m revgas_atendimento.simulador
```

Abre `http://127.0.0.1:8001` no navegador. É uma tela de chat ligada ao mesmo atendimento do servidor: mesmo banco, mesma consulta de CEP, mesmo prazo de cancelamento. Dá para criar vários clientes (cada um é um número de WhatsApp), usar respostas rápidas e ver, no painel "No sistema", o cadastro e os pedidos gravados para o número. Funciona no celular e no tema escuro, e nada é enviado ao WhatsApp. Opções: `--porta 8010` e `--sem-navegador`.

O simulador só atende o próprio computador. Ele recusa pedidos de outras máquinas, pedidos que passaram por proxy ou túnel e endereços que não sejam 127.0.0.1 ou localhost. A página não recebe chave nem token.

## Segredos

- Tokens e chaves ficam só no `.env`, que está fora do git. Dentro do programa, eles são do tipo `Segredo` (`segredo.py`) e aparecem como `***` em log, print, traceback e f-string. O valor real só sai com `.revelar()`, em dois pontos: a conferência da assinatura da Meta e o cabeçalho de envio da Cloud API.
- O servidor lê o `.env` direto para a configuração. Os valores não vão para as variáveis de ambiente do processo, então programas iniciados por ele não herdam os tokens.
- No log de acesso, o token de verificação da Meta aparece como `***`. As rotas `/docs` e `/openapi.json` ficam desligadas.
- Não cole tokens em código, README, fluxo do n8n ou chat. Se algum vazar, gere outro no painel da Meta.

## Estrutura (`revgas_atendimento/`)

| Parte | Módulos |
|---|---|
| Conversa | `atendimento.py` (cadastro), `atendimento_pedido.py` (pedido de gás), `atendimento_integrado.py` (escolhe quem responde), `interpretacao.py`, `texto.py` |
| Validação | `validacao.py` (nome, telefone e DDD), `validacao_pedido.py` (botijão, quantidade, pagamento, troco), `endereco.py` (CEP, número, coleta do endereço), `cep_viacep.py` (consulta ao ViaCEP) |
| Modelos e contratos | `modelos.py`, `modelos_pedido.py`, `portas.py`, `portas_pedido.py` |
| Montagem | `composicao.py`, `composicao_pedido.py` (`montar_loja`), `config.py`, `ambiente.py`, `segredo.py` |
| Simulador | `simulador.py` e `simulador_web/` (HTML, CSS e JS, sem dependências externas) |
| Entrada HTTP | `aplicacao.py` (todas as rotas), `api.py` (só cadastro), `api_pedido.py` (completo), `webhook.py`, `automacao.py`, `erros_http.py` |
| WhatsApp e infraestrutura | `whatsapp.py`, `whatsapp_cloud.py`, `processador.py`, `deduplicador.py`, `seguranca.py`, `simulacoes.py`, `simulacoes_pedido.py` |
| Armazenamento | `persistencia_sqlite.py` |

Fora do pacote:
- `tests/`: testes automatizados, um arquivo por assunto. Os dados em comum ficam em `tests/apoio.py`.
- `n8n/revgas_whatsapp.json`: fluxo para importar no n8n.
- `scripts/`: instalação e abertura do n8n local, e a troca para o Node.js 24.
- Na raiz: as demos `conversar.py` e `demo_pedido.py`, e o `testar_webhook.py`, que testa um servidor rodando de ponta a ponta.

## Instalar

Precisa do Python 3.11 ou mais novo. Na raiz do projeto:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m revgas_atendimento
```

O último comando roda uma demonstração do cadastro no terminal.

## Servidor

As variáveis ficam no ambiente do sistema ou num `.env` na raiz (veja o `.env.example`). Se a mesma variável estiver nos dois lugares, vale a do sistema. Há dois modos, e cada número de WhatsApp usa um só:

- Webhook direto da Meta: `WA_APP_SECRET` e `WA_VERIFY_TOKEN` para receber e conferir a assinatura. Para responder de verdade, também `WA_ACCESS_TOKEN` e `WA_PHONE_NUMBER_ID`. Sem essas duas, as respostas só aparecem no terminal.
- n8n: só `N8N_API_KEY`. O n8n recebe e envia as mensagens, e o Python responde em `POST /mensagem`. O passo a passo está no [README_N8N.md](README_N8N.md).

```bash
uvicorn revgas_atendimento.api_pedido:criar_app_com_pedido_de_gas --factory --host 127.0.0.1 --port 8000
```

Se o `.env` ainda tiver texto de exemplo (`COLE_…`, `defina_…`), o servidor não sobe e diz qual variável falta, sem mostrar o valor.

## Testes

```bash
python -m unittest discover -v
```

São 199 testes. Para rodar um arquivo só: `python -m unittest -v tests.test_validacao`. Os testes não acessam a internet: o CEP usa `CepsEmMemoria`, e o adaptador do ViaCEP é testado contra um servidor falso local.

Com o servidor rodando, `python testar_webhook.py` confere a rota `/saude`, a verificação da Meta, a assinatura e uma conversa completa.

## Segurança

O repositório só pode ter credenciais de exemplo. Não envie `.env`, tokens, chaves privadas, logs com dados de clientes nem o ambiente virtual. Se uma credencial real vazar, revogue ou troque no serviço que a emitiu.

## Ainda não implementado

Integração com a WhatsApp Business Platform em produção, pedido expresso, IA conversacional, painel de pedidos, encaminhamento para um atendente, acompanhamento da entrega e integração com ERP. Faça e teste essas mudanças em branches separadas.
