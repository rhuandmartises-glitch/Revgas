# RevGás — Protótipo de Atendimento

Protótipo RevGás, originalmente extraído de `Luchianni.rar`, com refatoração incremental de infraestrutura nesta branch. Destina-se a homologação e demonstração, não a uma operação comercial em produção.

## O que está implementado

- Fluxo de atendimento/cadastro pelo WhatsApp, com validações de dados e confirmação.
- Interfaces de integração e adaptador de mensagens da WhatsApp Cloud API.
- Webhook HTTP construído com FastAPI; valida assinatura e token de verificação.
- Armazenamento SQLite durável para cadastros, sessões e caixa de mensagens na API HTTP; simuladores mantidos para testes e demonstração local.
- Demonstração local do fluxo de cadastro e testes automatizados.

**Limites importantes:** a API HTTP usa SQLite e pode utilizar WhatsApp real somente com credenciais completas. A demonstração CLI ainda usa memória propositalmente. Não existe sistema de pedidos/entregas nem IA neste código. A incompatibilidade de importação foi corrigida.

## Estrutura

- `revgas_atendimento/`: núcleo de atendimento, modelos, validações, webhook, API HTTP, adaptadores WhatsApp, simulações e testes.
- `ambiente.py`, `composicao.py`, `seguranca.py`: encaminhamentos de compatibilidade para os módulos do pacote.
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

Configure `WA_APP_SECRET` e `WA_VERIFY_TOKEN` conforme `.env.example` (o projeto agora carrega `.env` automaticamente). Em seguida, é possível iniciar uma aplicação de desenvolvimento, por exemplo:

```bash
uvicorn revgas_atendimento.api:criar_app --factory --host 127.0.0.1 --port 8000
```

Sem credenciais de envio completas, o servidor funciona em simulação. Com credenciais reais, envia pela Cloud API; a homologação externa permanece necessária antes de expor na internet.

## Testes

```bash
python -m unittest discover -v
```

A incompatibilidade de importação de `CredenciaisWhatsApp` foi corrigida nesta branch. Execute a suíte novamente para obter o resultado na sua máquina.

## Segurança

O repositório deve conter somente exemplos fictícios de credenciais; nunca envie `.env`, tokens reais, chaves privadas, logs com dados pessoais ou arquivos do ambiente virtual. Se alguma credencial real tiver sido exposta, revogue ou substitua no serviço responsável.

## Próximas evoluções (não implementadas)

Pedido expresso, IA conversacional, painel de pedidos, encaminhamento humano e acompanhamento de entregas. Planeje e teste essas mudanças em branches separadas.

---

## Evolução incremental — persistência e entrega confiável (branch de refatoração)

Esta versão **não inclui IA, pedidos de gás ou integração ERP**. Conserva o atendimento
original de cadastro e altera apenas a infraestrutura.

### Como iniciar a API

1. Copie `.env.example` para `.env` e defina `WA_APP_SECRET` e `WA_VERIFY_TOKEN`.
2. Se for enviar mensagens reais, configure **ambas** `WA_ACCESS_TOKEN` e `WA_PHONE_NUMBER_ID`.
   Sem elas, o sistema entra explicitamente em modo de simulação; nenhum WhatsApp real é acionado.
3. Ajuste `REVGAS_DB_PATH` para um caminho persistente e com backup (padrão `dados/revgas.sqlite3`).
4. Execute:

```bash
pip install -r requirements.txt
uvicorn revgas_atendimento.api:criar_app --factory --host 127.0.0.1 --port 8000
```

A configuração é carregada pela única raiz de composição
`revgas_atendimento/composicao.py`. Os arquivos homônimos da raiz são apenas
compatibilidade. A demo `python -m revgas_atendimento` continua inteiramente simulada.

**Agora o HTTP somente responde 200 após confirmar a gravação das mensagens em SQLite**.
Se não conseguir gravar, retorna 503 para permitir reenvio pelo fornecedor.
A caixa de mensagens recebe todas as mensagens no lote do webhook e recusa IDs repetidos.
Um worker executado junto à API processa no máximo uma mensagem pendente por
telefone, de forma transacional. Sessão/cadastro e resposta preparada são gravados
juntos; falhas de envio tentam novamente sem repetir a regra de negócio.

Em desligamentos abruptos, eventos com lease vencido são retomados após 90 segundos.
Após cinco falhas um evento é marcado `dead`, exigindo inspeção e reprocessamento
supervisionado (sem excluir a mensagem). Backoff máximo: 300 segundos.

### Limitações e riscos residuais

- **Entrega externa at-least-once, não exactly-once:** se a Meta aceitar o envio e o
  processo cair antes de registrar `sent`, pode ocorrer uma resposta duplicada. A
  API de envio não oferece idempotência garantida por este projeto.
- SQLite é indicado para protótipo e instância única/pouco tráfego. O locking
  transacional impede a maior parte das corridas entre workers que compartilhem o
  mesmo banco em disco, mas não substitui PostgreSQL/fila distribuída numa escala alta.
- Mensagens que chegam fora de ordem da Meta são processadas na ordem em que foram
  persistidas, não na ordem absoluta da conversa. Não há buffer de reordenação temporal.
- Ainda faltam alertas sobre mensagens `dead`, dashboard de operação, backups
  automatizados, criptografia dos dados pessoais em repouso, políticas de retenção e
  teste de carga/queda de energia no ambiente real.
- O parser original ignora tipos não suportados (áudio/foto) e preserva o mesmo
  comportamento do fluxo de cadastro.
- O envio real exige token/permissões e observância das regras da Meta (janela de
  atendimento, templates e limites); não foi testado contra conta real.

### Validação antes de produção

```bash
python -m pytest -q
python -m unittest discover -q
python -m compileall -q revgas_atendimento
```

Para homologar: iniciar com banco descartável, enviar webhook assinado, repetir o
mesmo `wamid`, simular queda antes/depois do envio, reiniciar a API, acompanhar
linhas de `mensagens` até `sent` ou `dead` e verificar que o mesmo telefone não
recebe respostas fora de sequência. Não utilize informações pessoais reais na demo.
