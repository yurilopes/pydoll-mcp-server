# PLAN_FIX_12: Correção de conclusão real do P2

## Objetivo

Corrigir a entrega P2 para que as novas capacidades sejam funcionais, testadas e documentadas com precisão, sem implementar nada fora do escopo seguro.

## Escopo

- Corrigir `stdio` para iniciar sem token HTTP.
- Corrigir network inspection usando APIs reais da Pydoll.
- Implementar trace leve real ou reduzir explicitamente o escopo com `UNSUPPORTED`.
- Adicionar testes dedicados P2.
- Corrigir documentação e progresso.
- Validar versionamento `0.1.0a1`.
- Manter `console_*` como `UNSUPPORTED` se a API Runtime não for validada com segurança.
- Manter `browser_attach` seguro e limitado.

## Fora de Escopo

- Publicar no PyPI.
- Expor `execute_cdp_cmd`.
- Aceitar endpoint, porta, PID, URL ou websocket arbitrário em `browser_attach`.
- Criar comando de sistema operacional.
- Matar Chrome pessoal do usuário.
- Implementar CAPTCHA bypass, fraude ou evasão.

## Pré-requisitos

- Ler `AGENTS.md`.
- Ler `docs/evaluation-2026-06-12-p2-review.md`.
- Ler `plans/PLAN_P2.md`.
- Ler `plans/p2/PLAN_P2_02_STDIO_CLIENTS.md`.
- Ler `plans/p2/PLAN_P2_03_NETWORK_CONSOLE.md`.
- Ler `plans/p2/PLAN_P2_04_DIAGNOSTICS_TRACE.md`.
- Ler `plans/p2/PLAN_P2_05_MULTI_CLIENT_ATTACH.md`.
- Consultar a Pydoll local em `C:\Users\Yuri\Documents\Git\pydoll` quando houver dúvida de API.

## Critérios de início

1. Rodar baseline:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
```

2. Criar ou atualizar `progress/YYYY-MM-DD_AGENT_FIX_12.md`.
3. Registrar no progresso que FIX_12 corrige uma entrega P2 incompleta, não inicia P3.

## Tarefas detalhadas

### T1. Corrigir stdio

- Alterar o CLI para decidir `args.transport` antes de instanciar config que exige token HTTP.
- `stdio` não deve exigir `PYDOLL_MCP_AUTH_TOKEN` por padrão.
- HTTP deve continuar exigindo token por padrão.
- Adicionar teste que prova que `--transport stdio` despacha para `_run_stdio()` sem chamar config HTTP obrigatória.
- Se houver teste subprocess, ele deve ser controlado e não pode travar.

Aceite:

- `'' | C:\Users\Yuri\anaconda3\python.exe -m pydoll_mcp_server.cli --transport stdio` não falha por falta de token.
- Existe teste automatizado cobrindo isso.

### T2. Corrigir network inspection

- Reescrever `network_list` para usar `await pydoll_tab.get_network_logs(filter_url or None)`.
- Normalizar logs CDP reais:
  - `request_id`
  - `url`
  - `method`
  - `type`
  - `timestamp`
  - `resource_type`, se existir
- Redigir URL e campos sensíveis.
- Garantir que `network_get_response` rejeite `request_id` vazio com `INVALID_INPUT`.
- Manter limite de retenção se ainda houver manager em memória, mas não depender de callback quebrado para listar rede.

Aceite:

- Probe real com fixture HTTP local retorna ao menos uma URL não vazia e `request_id` não vazio.
- `token=secret` aparece redigido em URLs.
- `network_get_response` funciona para um `request_id` real quando Pydoll disponibiliza body, ou retorna erro estruturado justificável.

### T3. Implementar trace leve real

- Criar componente dedicado para trace, por exemplo `src/pydoll_mcp_server/diagnostics/trace.py`.
- O trace deve ter ownership por `client_id`.
- `trace_start` cria registro real com `trace_id`, `client_id`, `created_at`, `name` e status `running`.
- `trace_get` retorna eventos reais, mesmo que o conjunto inicial seja mínimo.
- Eventos mínimos aceitáveis:
  - trace started
  - diagnostics_snapshot called
  - network enabled/listed/response requested
  - trace stopped
  - structured error resumido
- `trace_stop` muda status para stopped e registra evento.
- `trace_cleanup` remove traces antigos somente dentro do runtime dir permitido ou da estrutura em memória controlada.
- Não registrar cookies, storage completo, bearer token, JS completo ou response body completo.

Aceite:

- Teste prova start, event append, stop, get e cleanup.
- Teste prova isolamento por `client_id`.
- Teste prova redaction de token/cookie/authorization em eventos.

### T4. Completar cobertura P2

Adicionar testes para:

- `server_status.capabilities` inclui P2.
- `stdio` não exige token HTTP.
- `network_enable`, `network_list`, `network_get_response`.
- `console_*` retorna `UNSUPPORTED` estruturado.
- `diagnostics_snapshot` não vaza token.
- `trace_*` funciona de verdade.
- `browser_attach` não aceita inputs arbitrários e respeita ownership.
- `version` em status é `0.1.0a1` ou vem da metadata do pacote.

Aceite:

- `rg "network_enable|network_list|console_enable|diagnostics_snapshot|trace_start|browser_attach|stdio" tests -n` retorna testes reais, não só comentários.
- O número de testes deve aumentar em relação a 150, salvo justificativa muito clara no progresso.

### T5. Corrigir documentação

- Criar `docs/clients/` com exemplos para:
  - Codex
  - OpenCode
  - Claude Code
- Corrigir README:
  - remover "Transporte stdio ainda é P2";
  - atualizar network e console para estado real;
  - explicar que console é `UNSUPPORTED` se continuar assim;
  - documentar trace conforme implementação real.
- Corrigir `docs/security.md` para não afirmar storage de trace em runtime dir se isso não estiver implementado.
- Corrigir `docs/release-checklist.md` para marcar como completo apenas o que tiver teste e probe.
- Corrigir `progress/2026-06-12_AGENT_PLAN_P2.md` ou criar `progress/YYYY-MM-DD_AGENT_FIX_12.md` com a verdade atual.

Aceite:

- `Test-Path docs\clients` retorna `True`.
- README não contém afirmações contraditórias sobre P2.
- Checklist bate com comportamento validado.

### T6. Browser attach e metadata

- Se metadata runtime for implementada:
  - persistir apenas dados mínimos e não sensíveis;
  - não gravar bearer token, cookies, storage, ws endpoint completo ou headers;
  - limpar metadata stale sem matar processos.
- Se metadata runtime ficar fora do escopo:
  - documentar explicitamente como limitação;
  - manter `browser_attach` como `UNSUPPORTED` seguro;
  - adicionar testes provando ownership e recusa de browser inexistente ou de outro client.

Aceite:

- O comportamento real de `browser_attach` é testado e documentado.
- Não há caminho para anexar a Chrome pessoal por endpoint, porta, PID ou URL.

## Como testar

Gates obrigatórios:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
```

Probes obrigatórios:

```powershell
'' | C:\Users\Yuri\anaconda3\python.exe -m pydoll_mcp_server.cli --transport stdio
```

Criar também probe automatizado ou teste real para network com servidor HTTP local.

## Riscos

- Teste de stdio travar se subprocesso não for encerrado.
- Network response body pode depender do timing da Pydoll e do tipo de resposta.
- Trace automático completo pode exigir refactor maior que o necessário.
- Browser attach real pode aumentar risco de segurança.

## Estratégia de recuperação

- Se stdio subprocess for instável, testar dispatch CLI com monkeypatch.
- Se `network_get_response` falhar por timing, manter erro estruturado mas `network_list` precisa funcionar com request IDs reais.
- Se trace automático amplo ficar arriscado, implementar trace explícito mínimo e documentar limite.
- Se attach real não for seguro, preferir `UNSUPPORTED` testado e documentado.

## Artefatos esperados

- Código corrigido.
- Testes P2 novos.
- `docs/clients/` criado.
- README corrigido.
- `docs/security.md` corrigido.
- `docs/release-checklist.md` corrigido.
- `progress/YYYY-MM-DD_AGENT_FIX_12.md` criado ou atualizado.

## Definição de pronto

FIX_12 só está pronto quando:

- `stdio` inicia sem token HTTP obrigatório.
- `network_list` retorna dados reais e úteis.
- `trace_*` não é stub enganoso.
- P2 tem testes próprios.
- Docs não contêm afirmações falsas.
- Todos os gates passam.
- Progresso registra claramente o que foi validado.

