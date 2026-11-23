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

## Estabilização corretiva — `fix/estabilidade-revgas`

A correção mantém o fluxo original de cadastro, o adaptador de simulação, a inbox
SQLite e o webhook assinado. Nenhum recurso de IA ou pedidos de gás foi adicionado.

### Falhas corrigidas

| Arquivo | Antes | Depois / verificação |
| --- | --- | --- |
| `revgas_atendimento/worker.py` | Exceções no ACK local ou no acesso ao banco encerravam o loop. | Supervisão com backoff, cancelamento normal e tratamento da confirmação incerta (`test_supervisor_recupera_erro_e_aceita_cancelamento`, `test_falha_de_confirmacao_apos_envio_nao_interrompe_worker`). |
| `revgas_atendimento/persistencia.py` | `sending` vencido voltava para `ready` e podia ser enviado outra vez sem aviso. | Lease vencido passa para `uncertain`, bloqueando retransmissão automática (`test_se_o_banco_cair_ao_marcar_incerta_lease_isola_envio`). |
| `revgas_atendimento/persistencia.py` | `dead` liberava mensagens posteriores do mesmo contato. | `dead` e `uncertain` bloqueiam a conversa até intervenção; reabertura é explícita (`test_dead_bloqueia_mensagens_posteriores_e_reabertura_manual`). |
| `revgas_atendimento/whatsapp_cloud.py` e `modelos.py` | Erro HTTP 5xx/timeout era tratado como falha genérica e podia gerar novo envio automático. | `EntregaIncertaError` distingue resposta externa de resultado incerto e interrompe reenvio automático (`test_falha_de_rede_com_envio_incerto_nao_retransmite`, `test_timeout_vira_integracao_error`). |
| `revgas_atendimento/api.py` | Sem rota de saúde. | `GET /health` retorna 200 somente com worker ativo e SQLite acessível, ou 503 se indisponível; não expõe dados privados (`TesteHealth`). |
| `test_estabilidade_worker.py` | Casos de concorrência, supervisão e falhas de ACK não tinham cobertura dedicada. | Testes de disputa por workers, persistência, idempotência, dead/uncertain, recuperação e operação sem Meta. |

### Política de entrega, retries e intervenção

- `pending`: mensagem aceita e persistida, ainda sem executar regra de cadastro.
- `processing`: reivindicada por worker; lease vencido retorna a `pending` para reprocessar.
- `sending`: resposta e alteração da sessão já foram persistidas; envio iniciado ou iminente.
- `ready`: resposta preparada e reenvio liberado após **falha de envio considerada conclusiva**; backoff exponencial até cinco tentativas (valor padrão).
- `sent`: a operação local de envio foi confirmada e registrada.
- `dead`: cinco falhas (padrão); não avança a conversa automaticamente.
- `uncertain`: envio com resultado indeterminado (ex.: timeout, erro HTTP 5xx, perda do ACK no banco, lease `sending` expirado). **Não será reenviado automaticamente**. Pode ser entregue ao cliente ou não.

Todas as mensagens anteriores ainda não `sent` bloqueiam mensagens posteriores do
mesmo telefone, preservando a consistência da sequência de atendimento. Um
operador deve consultar os registros e o destino externo antes de decidir sobre
reprocessamento. A função `CaixaDeMensagensSQLite.reprocessar_manualmente(id)`
reabre itens `dead`; para `uncertain`, exige `reenviar_incerta=True` **após confirmação
humana de que o reenvio é apropriado**. Não há painel de operação nesta versão.

Contadores locais sem PII: `await caixa.resumo()`. O monitoramento público
`GET /health` retorna apenas `status`, `worker`, `database` e `mode` (simulation
ou whatsapp); não deve ser confundido com prova de entrega. A demonstração CLI
(`python -m revgas_atendimento`) não usa WhatsApp real e não persiste cadastros
entre execuções; a API HTTP demonstra persistência SQLite.

### Comandos de validação

```bash
python -m pytest -q
python -m unittest discover -v
python -m compileall -q revgas_atendimento
python -m revgas_atendimento
```

### Limitações e riscos residuais

1. **At-least-once de entrada, não exactly-once de saída.** Uma falha depois que a
   Meta aceitou o envio, mas antes do ACK persistir, não pode ser resolvida sem
   confirmação externa. A política `uncertain` evita reenvio automático, mas pode
   exigir intervenção humana e atrasar conversas.
2. **Envios não confirmados por falhas do gateway genérico:** exceções não marcadas
   como `EntregaIncertaError` continuam no retry controlado; gateways novos devem
   distinguir erro conclusivo de resultado incerto.
3. **Leases:** dois processos em máquinas isoladas, travas de longa duração ou
   operação lenta maior que o lease fixo exigem testes de carga e fencing tokens.
4. **SQLite síncrono** na aplicação assíncrona pode bloquear o event loop sob
   volume elevado. A solução é adequada a um protótipo local de baixo volume;
   PostgreSQL e filas distribuídas não foram introduzidos.
5. **Ordem:** é respeitada a ordem de persistência da inbox, não a sequência
   absoluta de chegada à Meta. Ainda são necessários monitoramento persistente,
   políticas LGPD/backup e testes com credenciais reais antes de produção.
6. **Endpoint de saúde:** não deve ser usado sozinho como indicador de capacidade
   ou de entrega efetiva do WhatsApp; mantenha acesso restrito se exposto à rede.
