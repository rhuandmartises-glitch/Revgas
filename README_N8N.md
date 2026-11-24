# Ligando o bot ao WhatsApp pelo n8n

Neste modo, **o n8n recebe e envia** as mensagens do WhatsApp. O servidor Python só decide
o que responder, pela rota `POST /mensagem`. **Não precisa da chave secreta do app** (`WA_APP_SECRET`).

```
Cliente → WhatsApp → Meta → n8n (Webhook) → POST /mensagem (Python) → n8n → Graph API → Cliente
```

> Use **só um** modo por número. Se o webhook da Meta aponta para o n8n, ele não aponta para
> `/webhook/whatsapp` do Python (senão o cliente recebe respostas em dobro).

## O que você precisa
- **Conta no n8n Cloud** (n8n.io). Este computador não tem Node.js nem Docker para rodar o n8n localmente.
- Do painel da Meta (**WhatsApp → Configuração da API**): o **token de acesso** (`EAA…`) e o **Phone Number ID**.
  O seu celular cadastrado como destinatário do número de teste.
- O servidor Python rodando com um túnel (`cloudflared`), porque o n8n Cloud precisa alcançá-lo pela internet.

## 1. Servidor Python
No `.env`, só `N8N_API_KEY` é obrigatória neste modo (`WA_APP_SECRET`/`WA_VERIFY_TOKEN` ficam comentadas).

```powershell
.\.venv\Scripts\python.exe -m uvicorn revgas_atendimento.api_pedido:criar_app_com_pedido_de_gas --factory --port 8000
```
Em outra janela:
```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:8000
```
Anote o endereço `https://….trycloudflare.com`. Ele muda a cada vez que o túnel reinicia.

## 2. Importar o fluxo no n8n
1. No n8n: **Workflows → Import from File** → escolha `n8n/revgas_whatsapp.json`.
2. Crie duas credenciais do tipo **Header Auth** (Credentials → Add credential → "Header Auth"):
   - **RevGás bot**: Name `X-Api-Key`, Value = o valor de `N8N_API_KEY` do seu `.env`.
   - **WhatsApp Cloud API**: Name `Authorization`, Value = `Bearer ` + o token de acesso (`Bearer EAA…`).
3. Ajuste os nós (os textos em MAIÚSCULAS são para trocar):
   - **Token confere?**: troque `TROQUE_PELO_SEU_TOKEN_DE_VERIFICACAO` por um texto que você inventar.
   - **Pergunta ao bot RevGás**: troque `SEU-TUNEL` pelo endereço do túnel e escolha a credencial **RevGás bot**.
   - **Envia no WhatsApp**: troque `SEU_PHONE_NUMBER_ID` e escolha a credencial **WhatsApp Cloud API**.
4. Salve e **ative** o fluxo (botão *Active*). Copie a **Production URL** de um dos nós Webhook
   (os dois têm a mesma: `https://<sua-conta>.app.n8n.cloud/webhook/revgas-whatsapp`).

## 3. Cadastrar o webhook na Meta
**WhatsApp → Configuração → Webhook → Editar**:
- **URL de callback**: a Production URL do n8n.
- **Verificar token**: o mesmo texto do nó *Token confere?*.
- **Verificar e salvar**, depois **Assinar** o campo `messages`.

Mande "oi" do celular para o número de teste. Na aba **Executions** do n8n dá para ver cada mensagem
passando por cada nó.

## A rota `POST /mensagem`
**Cabeçalho:** `X-Api-Key: <N8N_API_KEY>`. **Corpo:**
```json
{ "telefone": "5511999990000", "texto": "quero gás", "id": "wamid.HBgN..." }
```
**Resposta 200:** `{ "resposta": "Opa, vamos pedir seu gás! ...", "duplicada": false }`.
Com `duplicada: true`, `resposta` vem `null` e nada deve ser enviado (a Meta reenviou a mesma mensagem).
**Erros:** 401 (chave errada), 422 (telefone inválido/corpo malformado), 503 (`N8N_API_KEY` não definida).

Teste sem o n8n (servidor na porta 8000):
```powershell
$chave = (Select-String -Path .env -Pattern '^N8N_API_KEY=(.*)').Matches[0].Groups[1].Value
$r = Invoke-WebRequest http://127.0.0.1:8000/mensagem -Method POST -UseBasicParsing -ContentType 'application/json; charset=utf-8' -Headers @{'X-Api-Key'=$chave} -Body ([Text.Encoding]::UTF8.GetBytes('{"telefone":"5511999990000","texto":"quero gás"}'))
[Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray())
```

## Segurança e limites deste modo
- **Sem a chave secreta do app, o n8n não confere a assinatura da Meta.** Quem descobrir a URL do
  webhook do n8n pode mandar mensagens falsas, e o bot responderia usando o seu token. Com o número
  de teste o estrago é limitado: a Meta só entrega para os até 5 destinatários cadastrados. **Antes de
  usar com clientes reais**, pegue a chave secreta e valide a assinatura (ou use o webhook direto do Python,
  que já valida).
- A rota `/mensagem` é protegida pela `N8N_API_KEY`. Não coloque essa chave no texto dos nós: use a credencial.
- Números do Brasil às vezes chegam da Meta **sem o 9 extra**. Se o envio der erro `131030`, cadastre o
  número na lista de destinatários no formato que aparece no campo `from` da execução.
- Cadastros e pedidos ficam em `dados/revgas.sqlite3` e o cliente é lembrado pelo número (o campo
  `telefone` que o n8n manda). Só a conversa em andamento fica em memória e se perde ao reiniciar.
