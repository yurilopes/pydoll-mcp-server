# FIX_13: Ajustes finais de aceitação pós FIX_12

## Objetivo

Fechar lacunas de aceitação remanescentes após FIX_12, garantindo que versão, trace, network list, testes e documentação estejam coerentes com o estado real do P2.

## Escopo

- Corrigir versão reportada por health/status.
- Integrar trace mínimo com tools de diagnóstico e network.
- Filtrar eventos vazios em `network_list`.
- Trocar testes baseados em source inspection por testes comportamentais.
- Atualizar release checklist e progresso.

## Fora de escopo

- Implementar console real.
- Implementar attach real pós restart.
- Expor CDP livre.
- Criar commands de sistema operacional.
- Publicar PyPI.
- Refatorar arquitetura ampla.

## Pré-requisitos

- Ler `AGENTS.md`.
- Ler `docs/evaluation-2026-06-12-fix12-review.md`.
- Ler `plans/remediation/PLAN_FIX_12_P2_COMPLETION.md`.
- Ler `progress/2026-06-12_AGENT_FIX_12.md`.
- Confirmar baseline atual.

## Critérios de início

Rodar:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
```

Criar ou atualizar:

```text
progress/YYYY-MM-DD_AGENT_FIX_13.md
```

## Tarefas detalhadas

### T1. Corrigir versão reportada

- Centralizar a versão do servidor.
- `health_check`, `server_status` e `/health` devem reportar a versão real do pacote, hoje `0.1.0a1`.
- Preferência:
  - usar helper em módulo pequeno, por exemplo `pydoll_mcp_server.version`;
  - tentar `importlib.metadata.version("pydoll-mcp-server")`;
  - fallback para constante `0.1.0a1`.
- Atualizar testes para exigir `0.1.0a1`, não apenas substring `0.1.0`.

Aceite:

- `health_check()["version"] == "0.1.0a1"`.
- `server_status(... )["version"] == "0.1.0a1"`.
- `/health` retorna `version: 0.1.0a1`.

### T2. Integrar trace mínimo com tools reais

- Adicionar no `TraceManager` uma forma segura de recuperar trace ativo por `client_id`.
- Registrar eventos em trace ativo para:
  - `diagnostics_snapshot`;
  - `network_enable`;
  - `network_list`;
  - `network_get_response`;
  - erros estruturados dessas tools.
- O evento deve incluir:
  - timestamp;
  - tool;
  - status;
  - tab_id quando aplicável;
  - error_code quando aplicável;
  - summary curto e redigido.
- Não registrar:
  - bearer token;
  - cookies;
  - storage completo;
  - response body completo;
  - JS completo.

Aceite:

- Teste chama `trace_start`, depois `diagnostics_snapshot`, depois `trace_get`, e encontra evento `diagnostics_snapshot`.
- Teste chama `trace_start`, depois `network_enable` com fake tab ou fake registry, depois `trace_get`, e encontra evento `network_enable`.
- Teste de erro estruturado mostra evento com `error_code`.

### T3. Limpar `network_list`

- Filtrar por padrão logs sem `params.request.url`.
- Não retornar eventos vazios duplicados por padrão.
- Manter request IDs reais nos eventos úteis.
- Redigir query params sensíveis.
- Se houver necessidade futura de eventos parciais, deixar para opção explícita posterior, não no padrão.

Aceite:

- Teste com logs mistos prova que eventos sem URL são omitidos.
- Teste com token em URL prova redaction.
- Probe real com browser local não mostra eventos com `url: ""` no output padrão.

### T4. Fortalecer testes comportamentais

- Substituir ou complementar source inspection:
  - teste de `stdio`: monkeypatch em `_run_stdio` e `get_config`, chamando `main()` com `--transport stdio`, provando que `_run_stdio` foi chamado e `get_config` não foi chamado;
  - teste de `network_list`: fake tab com `get_network_logs` instrumentado, provando chamada real e normalização.
- Remover asserts que dependem de texto no source quando houver teste comportamental equivalente.

Aceite:

- `rg "inspect.getsource|source = inspect" tests/p2 -n` não retorna teste essencial ou retorna apenas uso justificado.

### T5. Atualizar documentação e progresso

- Atualizar `docs/release-checklist.md` com os números finais.
- Atualizar README se algum comportamento de trace/network for documentado.
- Criar `progress/YYYY-MM-DD_AGENT_FIX_13.md`.

Aceite:

- Checklist não menciona números antigos de FIX_12 se FIX_13 alterou a suíte.
- Progresso descreve os testes executados e os problemas fechados.

## Como testar

Gates finais:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
```

Probes finais:

```powershell
'' | C:\Users\Yuri\anaconda3\python.exe -m pydoll_mcp_server.cli --transport stdio
```

Executar probe real de network com fixture HTTP local ou teste equivalente.

## Riscos

- Integrar trace automaticamente em todas as tools pode crescer demais.
- `importlib.metadata.version()` pode falhar em editable install se metadata não estiver disponível.
- Eventos de network da Pydoll podem variar por Chromium.

## Estratégia de recuperação

- Se versão via metadata falhar, usar constante local sincronizada com `pyproject.toml`.
- Se trace automático amplo for arriscado, registrar apenas `diagnostics_snapshot` e `network_*` neste FIX.
- Se eventos da Pydoll variarem, filtrar apenas por presença de `params.request.url`.

## Artefatos esperados

- Código corrigido.
- Testes P2 ajustados.
- `docs/release-checklist.md` atualizado.
- `progress/YYYY-MM-DD_AGENT_FIX_13.md` criado.

## Definição de pronto

FIX_13 está pronto quando:

- versão reportada é `0.1.0a1`;
- trace registra eventos reais além de start/stop;
- `network_list` não retorna eventos vazios no padrão;
- testes P2 são comportamentais nos pontos críticos;
- docs refletem os gates atuais;
- todos os gates finais passam.

