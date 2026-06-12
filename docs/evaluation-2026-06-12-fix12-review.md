# Reavaliação FIX_12 - 2026-06-12

## Resultado

FIX_12 corrigiu os bloqueadores principais do P2, mas ainda não deve ser aceito como fechamento final sem um ajuste curto de qualidade.

Os gates reportados pelo desenvolvedor foram reproduzidos localmente:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
# 181 passed, 2 warnings

C:\Users\Yuri\anaconda3\python.exe -m ruff check .
# All checks passed!

C:\Users\Yuri\anaconda3\python.exe -m mypy src
# Success: no issues found in 37 source files

C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
# 9 passed, 172 deselected
```

O probe de `stdio` sem token também não falhou por autenticação:

```powershell
'' | C:\Users\Yuri\anaconda3\python.exe -m pydoll_mcp_server.cli --transport stdio
```

O processo retornou código 0. A mensagem de erro observada veio de JSON-RPC vazio no stdin, não de `PYDOLL_MCP_AUTH_TOKEN`.

## Melhorias confirmadas

- `cli.py` decide `--transport stdio` antes de carregar config HTTP.
- `tests/p2/` existe e aumentou a suíte para 181 testes.
- `network_list` usa `get_network_logs()` da Pydoll.
- `docs/clients/` existe com exemplos para Codex, OpenCode e Claude Code.
- `TraceManager` existe com ownership por `client_id`, start, stop, get e cleanup.
- README removeu as afirmações antigas de que `stdio` e network ainda eram P2.

## Achados remanescentes

### 1. Versão reportada ainda é `0.1.0`, mas o pacote está em `0.1.0a1`

Severidade: média.

Evidência:

- `pyproject.toml` define versão `0.1.0a1`.
- `src/pydoll_mcp_server/server.py` ainda retorna `version: '0.1.0'` em `health_check`, `server_status` e `health_endpoint`.
- `tests/p2/test_p2_features.py` só verifica que a string contém `0.1.0`, então não captura a divergência.

Impacto:

- Clientes MCP, diagnósticos e release checklist podem reportar versão diferente da wheel instalada.

Correção esperada:

- Centralizar versão em um único lugar ou ler via `importlib.metadata.version("pydoll-mcp-server")` com fallback seguro.
- `health_check`, `server_status` e `/health` devem reportar `0.1.0a1`.
- Teste deve exigir igualdade com `0.1.0a1` ou com a metadata do pacote.

### 2. Trace ainda não registra eventos de tools além de start e stop

Severidade: média.

Evidência:

- `TraceManager` existe, mas `rg "add_event|TraceEvent" src` mostra integração real apenas em `trace_start` e `trace_stop`.
- `diagnostics_snapshot`, `network_enable`, `network_list` e `network_get_response` não registram eventos em trace ativo.
- `plans/remediation/PLAN_FIX_12_P2_COMPLETION.md` pedia eventos mínimos para `diagnostics_snapshot`, `network_*`, `trace_stop` e erros estruturados.

Impacto:

- A tool `trace_get` deixa de ser um trace útil de troubleshooting. Ela prova estado interno do trace, mas não reproduz operações relevantes.

Correção esperada:

- Adicionar mecanismo simples para obter trace ativo por `client_id`.
- Registrar eventos mínimos quando houver trace ativo:
  - `diagnostics_snapshot`
  - `network_enable`
  - `network_list`
  - `network_get_response`
  - erros estruturados dessas tools
- Manter redaction e não registrar corpo completo de resposta.
- Adicionar testes que chamam `trace_start`, depois uma tool real, depois `trace_get`, verificando que o evento da tool aparece.

### 3. `network_list` retorna eventos vazios duplicados em browser real

Severidade: baixa a média.

Probe real com fixture HTTP local retornou eventos úteis, mas também eventos duplicados com `url`, `method`, `type` e `timestamp` vazios:

```json
{
  "request_id": "26964.2",
  "url": "",
  "method": "",
  "type": "",
  "timestamp": 0
}
```

Ao mesmo tempo, também retornou eventos corretos:

```json
{
  "request_id": "26964.2",
  "url": "http://127.0.0.1:50423/api/data?token=REDACTED",
  "method": "GET",
  "type": "Fetch"
}
```

Hipótese:

- A Pydoll pode estar incluindo eventos CDP relacionados sem `params.request`, como extra info, na coleção lida por `get_network_logs()`.

Correção esperada:

- `network_list` deve filtrar logs que não tenham `params.request.url` antes de normalizar, ou marcar explicitamente esses eventos como parciais e escondê-los por padrão.
- O padrão agent-friendly deve retornar eventos úteis, não duplicatas vazias.
- Adicionar teste para garantir que logs sem `request.url` não aparecem por padrão.

### 4. Testes P2 ainda usam inspeção de source em pontos importantes

Severidade: média.

Evidência:

- `tests/p2/test_p2_features.py` inspeciona source para verificar dispatch de `stdio`.
- `tests/p2/test_network.py` inspeciona source para verificar uso de `get_network_logs`.

Impacto:

- Source inspection é frágil e não prova comportamento. Já houve problema anterior com teste baseado em presença de texto.

Correção esperada:

- Substituir ou complementar por testes comportamentais:
  - monkeypatch em `_run_stdio` e `get_config` para provar que config não é chamada em `stdio`;
  - fake tab com método `get_network_logs` instrumentado para provar chamada e normalização sem inspecionar source.

### 5. Release checklist ficou desatualizado

Severidade: baixa.

Evidência:

- `docs/release-checklist.md` ainda informa `pytest -q: 150 passed` e `mypy src: 35 source files`.
- Estado atual é `181 passed` e `37 source files`.

Correção esperada:

- Atualizar checklist para refletir o estado pós FIX_12/FIX_13.
- Se FIX_13 adicionar testes, registrar o novo número final.

## Recomendação

Executar `plans/remediation/FIX_13_POST_FIX12_ACCEPTANCE.md` antes de aceitar a release alpha.

FIX_13 deve ser curto e focado. Não deve abrir P3, não deve mudar arquitetura e não deve tentar implementar console real ou attach real.

