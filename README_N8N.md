# Bot no WhatsApp pelo n8n

Neste modo, o n8n recebe e envia as mensagens do WhatsApp. O servidor Python só decide o que responder, pela rota `POST /mensagem`. A chave secreta do app (`WA_APP_SECRET`) não é necessária.

```
Cliente → WhatsApp → Meta → n8n (Webhook) → POST /mensagem (Python) → n8n → Graph API → Cliente
```

> Use um modo só por número. Se o webhook da Meta aponta para o n8n, ele não pode apontar também para `/webhook/whatsapp` do Python, ou o cliente recebe cada resposta duas vezes.

O n8n pode rodar neste computador ou no n8n Cloud. Os dois caminhos estão abaixo.

## n8n neste computador

Precisa do Node.js 24. O Node 26 ainda não tem prontas as peças nativas que o n8n usa.

```powershell
winget install OpenJS.NodeJS.24
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\instalar_n8n.ps1
```

Para usar, abra três janelas e deixe as três abertas:

1. Bot Python: `.\.venv\Scripts\python.exe -m uvicorn revgas_atendimento.api_pedido:criar_app_com_pedido_de_gas --factory --host 127.0.0.1 --port 8000`
2. Túnel para o n8n (porta 5678): `& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:5678`
3. n8n: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\abrir_n8n.ps1 -Tunel https://<endereço-do-túnel>`

Depois abra `http://localhost:5678`. Neste modo, o n8n chama o bot direto em `http://127.0.0.1:8000/mensagem`, sem túnel para o Python. Só o n8n fica exposto, e só pelo túnel.

Na primeira vez, crie a conta de dono assim que o n8n abrir. Enquanto ela não existe, qualquer pessoa com o endereço do túnel vê a tela de criação.

O endereço do túnel muda a cada reinício. Quando mudar, rode o passo 3 de novo com o endereço novo e atualize a URL de callback na Meta.

Para importar o fluxo, siga a seção "Montar o fluxo" abaixo. No nó "Pergunta ao bot RevGás", use `http://127.0.0.1:8000/mensagem` como URL.

## n8n Cloud

Você vai precisar de:
- Uma conta no n8n Cloud (n8n.io).
- O token de acesso (`EAA…`) e o Phone Number ID, do painel da Meta (WhatsApp → Configuração da API). Seu celular precisa estar cadastrado como destinatário do número de teste.
- O servidor Python com um túnel (`cloudflared`), porque o n8n Cloud precisa alcançá-lo pela internet.

No `.env`, só a `N8N_API_KEY` é obrigatória neste modo. `WA_APP_SECRET` e `WA_VERIFY_TOKEN` ficam comentadas.

```powershell
.\.venv\Scripts\python.exe -m uvicorn revgas_atendimento.api_pedido:criar_app_com_pedido_de_gas --factory --port 8000
```

Em outra janela:

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:8000
```

Anote o endereço `https://….trycloudflare.com`. Ele muda toda vez que o túnel reinicia.

## Montar o fluxo

1. No n8n, vá em Workflows → Import from File e escolha `n8n/revgas_whatsapp.json`.
2. Crie duas credenciais do tipo "Header Auth" (Credentials → Add credential → "Header Auth"):
   - RevGás bot: Name `X-Api-Key`, Value = o valor de `N8N_API_KEY` do seu `.env`.
   - WhatsApp Cloud API: Name `Authorization`, Value = `Bearer ` seguido do token de acesso (`Bearer EAA…`).
3. Ajuste os nós. Os textos em maiúsculas são para trocar:
   - "Token confere?": troque `TROQUE_PELO_SEU_TOKEN_DE_VERIFICACAO` por um texto que você inventar.
   - "Pergunta ao bot RevGás": troque `SEU-TUNEL` pelo endereço do túnel e escolha a credencial RevGás bot.
   - "Envia no WhatsApp": troque `SEU_PHONE_NUMBER_ID` e escolha a credencial WhatsApp Cloud API.
4. Salve e ative o fluxo (botão Active). Copie a Production URL de um dos nós Webhook. Os dois têm a mesma, que termina em `/webhook/revgas-whatsapp`.

## Cadastrar o webhook na Meta

Em WhatsApp → Configuração → Webhook → Editar:
- URL de callback: a Production URL do n8n.
- Verificar token: o mesmo texto do nó "Token confere?".
- Clique em Verificar e salvar e depois assine o campo `messages`.

Mande "oi" do celular para o número de teste. A aba Executions do n8n mostra cada mensagem passando pelos nós.

## A rota `POST /mensagem`

Cabeçalho: `X-Api-Key: <N8N_API_KEY>`. Corpo:

```json
{ "telefone": "5511999990000", "texto": "quero gás", "id": "wamid.HBgN..." }
```

Resposta 200: `{ "resposta": "Opa, vamos pedir seu gás! ...", "duplicada": false }`. Quando `duplicada` vem `true`, `resposta` vem `null` e nada deve ser enviado: a Meta reenviou uma mensagem já respondida.

Erros: 401 (chave errada), 422 (telefone inválido ou corpo malformado), 503 (`N8N_API_KEY` não definida).

Teste sem o n8n, com o servidor na porta 8000:

```powershell
$chave = (Select-String -Path .env -Pattern '^N8N_API_KEY=(.*)').Matches[0].Groups[1].Value
$r = Invoke-WebRequest http://127.0.0.1:8000/mensagem -Method POST -UseBasicParsing -ContentType 'application/json; charset=utf-8' -Headers @{'X-Api-Key'=$chave} -Body ([Text.Encoding]::UTF8.GetBytes('{"telefone":"5511999990000","texto":"quero gás"}'))
[Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray())
```

## Segurança e limites

- Sem a chave secreta do app, o n8n não confere a assinatura da Meta. Quem descobrir a URL do webhook pode mandar mensagens falsas, e o bot responderia usando o seu token. Com o número de teste o risco é pequeno, porque a Meta só entrega para até 5 destinatários cadastrados. Antes de atender clientes reais, pegue a chave secreta e confira a assinatura, ou use o webhook direto do Python, que já confere.
- A rota `/mensagem` é protegida pela `N8N_API_KEY`. Guarde essa chave numa credencial do n8n, não no texto dos nós.
- Números do Brasil às vezes chegam da Meta sem o 9 extra. Se o envio der erro `131030`, cadastre o número na lista de destinatários no formato que aparece no campo `from` da execução.
- Cadastros e pedidos ficam em `dados/revgas.sqlite3`, e o cliente é lembrado pelo `telefone` que o n8n manda. Só a conversa em andamento fica em memória e se perde quando o servidor reinicia.
