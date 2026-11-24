# Pedido de gás — adição ao protótipo RevGás

Esta função foi adicionada **sem alterar nenhum arquivo já existente do projeto**. Tudo é novo,
em módulos separados, que se conectam aos originais só por import.

## Arquivos novos

Dentro de `revgas_atendimento/`:
- `modelos_pedido.py` — `Pedido`, `SessaoPedido`, `TipoBotijao` (P13/P20/P45), `EtapaPedido`.
- `portas_pedido.py` — contrato `RepositorioDePedidos`.
- `validacao_pedido.py` — valida tipo de botijão e quantidade (reaproveita `validar_endereco` de `validacao.py`).
- `simulacoes_pedido.py` — `PedidosEmMemoria`, repositório de pedidos em memória (para demo/testes).
- `atendimento_pedido.py` — `ServicoDePedido`: a conversa do pedido em si (pergunta botijão → quantidade → endereço → confirmação).
- `atendimento_integrado.py` — `ServicoDeAtendimentoIntegrado`: decide, a cada mensagem, se quem responde é o cadastro ou o pedido.
- `composicao_pedido.py` — monta tudo (`montar_servico_de_webhook_com_pedido_de_gas`), nos mesmos moldes de `composicao.py`.
- `api_pedido.py` — app FastAPI alternativo (`criar_app_com_pedido_de_gas`), nos mesmos moldes de `api.py`.

Fora do pacote:
- `tests/test_pedido.py` — testes do pedido e da integração com o cadastro.
- `demo_pedido.py` (na raiz) — demonstração local, sem WhatsApp/ERP.

## Como funciona a conversa

A conversa é **só em texto livre, sem nenhum botão** — pra soar como uma conversa de verdade
com um atendente, não um menu de opções. O cliente pode pedir gás a qualquer momento enviando
uma mensagem com a palavra **"gás"** (ou "pedido", com ou sem acento). O bot então pergunta,
nessa ordem:

1. **Tipo de botijão** — o cliente escreve como quiser: "P13", "13kg", "o pequeno", "residencial"
   (tudo isso vira P13); "P20", "médio"; "P45", "o grande", "comercial". Funciona mesmo dentro de
   uma frase inteira, tipo "quero um botijão P13, o pequeno mesmo".
2. **Quantidade** — de 1 a 6 botijões, em número ("2") ou por extenso ("duas, por favor").
3. **Endereço de entrega** — pelo CEP, como no cadastro: o bot acha a rua e pergunta só o
   número e o complemento. Sem CEP ("não sei"), aceita o endereço digitado com número.
4. **Forma de pagamento** — Pix, dinheiro, cartão de débito ou de crédito, na entrega. Em
   dinheiro, o bot pergunta o troco ("troco para 100" ou "não").
5. **Confirmação** — um resumo do pedido (com o pagamento), e o cliente responde com algo como
   "sim", "pode mandar", "confirmo" ou "não, tá errado" / "quero mudar". Para trocar o
   pagamento, basta dizer a forma nova ("prefiro pagar no Pix").

### Cancelar depois de confirmar

A confirmação avisa o prazo: "Se precisar cancelar, mande CANCELAR em até 5 minutos". Dentro
do prazo, CANCELAR cancela o último pedido (status `CANCELADO` no banco). Depois do prazo, o
bot explica que o pedido já pode estar a caminho e orienta a falar com a loja. O prazo é
configurável em `REVGAS_PRAZO_CANCELAMENTO_MIN` (0 desliga).

### Cliente já cadastrado: só confirma

Se o cliente já tem cadastro, o pedido **não pergunta o endereço de novo**. Depois do botijão e
da quantidade, o bot mostra nome, telefone e endereço do cadastro e o cliente só responde
"sim". Se o endereço mudou, ele manda o CEP novo ali mesmo (ex.: "01310-100"), informa o
número e o bot mostra o resumo atualizado para confirmar. Responder "não" faz o bot pedir o CEP
do endereço certo; "REFAZER" recomeça o pedido do zero.

O mesmo vale no fim do cadastro: o resumo mostra nome, telefone e endereço; o cliente confirma
com "sim" ou manda um CEP novo para trocar só o endereço. Nenhuma das duas conversas usa
botões.

Antes de confirmar, a qualquer momento o cliente pode enviar algo como `CANCELAR` (ou "deixa pra
lá", "esquece") para descartar o pedido em andamento.

Se o cliente já estiver no meio do cadastro (nome/telefone/endereço) quando digitar "gás", o
cadastro **continua normalmente** — a palavra "gás" não interrompe um fluxo já em andamento.
Isso é decidido pelo `ServicoDeAtendimentoIntegrado`, olhando se já existe uma sessão ativa de
cadastro ou de pedido antes de decidir para quem a mensagem vai.

## Como usar

### Conversar de verdade, digitando (recomendado para testar como cliente)
```bash
python conversar.py
```
Abre uma conversa interativa no terminal: você digita como se fosse o cliente mandando mensagem
no WhatsApp, e vê a resposta do bot na hora. Funciona tanto para o cadastro ("oi" pra começar)
quanto para o pedido de gás ("gás" ou "pedido" pra começar), na mesma sessão. Pra sair: "sair".

### Demonstração automática (roteiro fixo, sem digitar nada)
```bash
python demo_pedido.py
```

### Testes
```bash
python -m unittest -v tests.test_pedido
```
Todos os testes: `python -m unittest discover -v`.

### Servidor HTTP com a nova função
No lugar de `revgas_atendimento.api:criar_app`, use:
```bash
uvicorn revgas_atendimento.api_pedido:criar_app_com_pedido_de_gas --factory --host 127.0.0.1 --port 8000
```
`api.py` (o entry point original) não foi tocado e continua funcionando exatamente como antes,
sem a função de pedido.

## Limitações (mesmas do projeto original)

- Os pedidos ficam em `PedidosEmMemoria`: são perdidos ao reiniciar o servidor, do mesmo jeito
  que os cadastros em `CadastrosEmMemoria`.
- Esta adição usa `WhatsAppEmMemoria` (modo console), igual ao `api.py` original — nenhuma
  mensagem é enviada de verdade pelo WhatsApp.
- Em produção, troque `PedidosEmMemoria` por uma tabela/sistema de logística real, seguindo o
  mesmo padrão de substituição já descrito no `README.md` original para cadastros e sessões.
