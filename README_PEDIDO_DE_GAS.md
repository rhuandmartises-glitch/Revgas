# Pedido de gás

Como funciona a conversa do pedido de botijão. O resto do projeto está no [README.md](README.md).

## Arquivos

Em `revgas_atendimento/`:
- `modelos_pedido.py`: `Pedido`, `SessaoPedido`, `TipoBotijao` (P13, P20, P45), `FormaPagamento`, `StatusPedido` e `EtapaPedido`.
- `portas_pedido.py`: o contrato `RepositorioDePedidos`.
- `validacao_pedido.py`: valida botijão, quantidade, forma de pagamento e troco. O endereço é validado em `endereco.py`, pelo CEP, igual ao cadastro.
- `atendimento_pedido.py`: `ServicoDePedido`, a conversa do pedido.
- `atendimento_integrado.py`: `ServicoDeAtendimentoIntegrado`, que decide a cada mensagem se quem responde é o cadastro ou o pedido.
- `composicao_pedido.py`: monta o atendimento completo (`montar_loja`).
- `api_pedido.py`: o servidor com cadastro e pedido (`criar_app_com_pedido_de_gas`).
- `persistencia_sqlite.py`: grava os pedidos (`PedidosSqlite`). Nos testes e nas demos, `PedidosEmMemoria` (`simulacoes_pedido.py`) faz esse papel.

Fora do pacote:
- `tests/test_pedido.py` e `tests/test_pagamento_e_cancelamento.py`: testes do pedido.
- `demo_pedido.py`, na raiz: demonstração local, sem WhatsApp.

## A conversa

A conversa é só em texto, sem botões, para parecer com a de um atendente. O cliente começa um pedido a qualquer momento mandando uma mensagem com "gás" ou "pedido", com ou sem acento. O bot pergunta, nesta ordem:

1. Botijão. O cliente escreve como quiser: "P13", "13kg", "o pequeno" e "residencial" viram P13; "P20" e "médio" viram P20; "P45", "o grande" e "comercial" viram P45. Funciona dentro de uma frase ("quero um botijão P13, o pequeno mesmo").
2. Quantidade, de 1 a 6, em número ("2") ou por extenso ("duas, por favor").
3. Endereço de entrega, pelo CEP. O bot acha a rua e pergunta o número e o complemento. Se o cliente não souber o CEP ("não sei"), ele digita o endereço com o número.
4. Forma de pagamento na entrega: Pix, dinheiro, cartão de débito ou de crédito. Em dinheiro, o bot pergunta o troco ("troco para 100" ou "não").
5. Confirmação. O bot mostra o resumo, e o cliente responde "sim", "pode mandar", "confirmo", ou "não, tá errado". Para trocar o pagamento, basta dizer a forma nova ("prefiro pagar no Pix").

### Cliente já cadastrado

Se o número já tem cadastro, o bot não pergunta o endereço. Depois do botijão e da quantidade, mostra onde vai entregar e pergunta o pagamento. No resumo aparecem nome, telefone e endereço do cadastro.

Se o endereço mudou, o cliente manda o CEP novo na confirmação ("01310-100"), informa o número e confere o resumo atualizado. "Não" faz o bot pedir o CEP do endereço certo. "Refazer" ou "começar de novo" recomeça o pedido.

O fim do cadastro funciona do mesmo jeito: o cliente confirma com "sim" ou manda um CEP novo para trocar só o endereço.

### Cancelar

Antes de confirmar, qualquer jeito de desistir ("cancela", "deixa pra lá", "esquece", "não quero mais") descarta o pedido em andamento. A lista completa está em `intencoes.py`.

Depois de confirmar, a mensagem avisa o prazo: "Se mudar de ideia, dá para cancelar por aqui em até 5 minutos". Dentro do prazo, o mesmo tipo de mensagem cancela o último pedido, e o status no banco passa a `CANCELADO`. Depois do prazo, o bot explica que o pedido pode já estar a caminho e pede para o cliente falar com a loja. O prazo fica em `REVGAS_PRAZO_CANCELAMENTO_MIN` (0 desliga).

### Pedido no meio do cadastro

Se o cliente estiver no meio do cadastro e mandar "gás", o cadastro continua: a palavra não interrompe uma conversa em andamento. Quem decide é o `ServicoDeAtendimentoIntegrado`, que olha se já existe uma sessão aberta de cadastro ou de pedido antes de escolher quem responde.

## Como usar

### Conversar pelo terminal

```bash
python conversar.py
```

Você digita como se fosse o cliente e vê a resposta do bot na hora. Funciona para o cadastro ("oi") e para o pedido ("gás"). Para sair, digite "sair". Para uma tela parecida com o WhatsApp, use o simulador (`python -m revgas_atendimento.simulador`).

### Demonstração com roteiro fixo

```bash
python demo_pedido.py
```

### Testes

```bash
python -m unittest -v tests.test_pedido
```

Todos os testes: `python -m unittest discover -v`.

### Servidor

```bash
uvicorn revgas_atendimento.api_pedido:criar_app_com_pedido_de_gas --factory --host 127.0.0.1 --port 8000
```

O `api.py` sobe um servidor só com o cadastro, sem o pedido.

## Limites

- Os pedidos ficam no SQLite (`dados/revgas.sqlite3`). A conversa em andamento fica em memória e se perde quando o servidor reinicia.
- O bot não sabe o preço dos botijões. Por isso não confere se o troco é maior que o total; só aceita notas de R$ 1 a R$ 1.000.
- Quando o cliente cancela, ninguém da loja é avisado. O cancelamento só fica gravado no banco.
