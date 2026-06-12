# Progresso P2 - 2026-06-12

Plano atual: `plans/PLAN_P2.md` com detalhamento em `plans/p2/`.

## Baseline P2.0

Gates iniciais:
- `pytest -q`: 150 passed
- `ruff check .`: All checks passed
- `mypy src`: Success (33 source files)
- `pytest -m browser_smoke -q`: 9 passed

## P2.1 - API contract (concluido)

- `SCHEMA_VERSION = '2026-06-12.p2'` adicionado
- `health_check` e `server_status` incluem `schema_version`
- `server_status.capabilities` com grupos: transports, browser, page, elements, diagnostics, inspection, security
- `ErrorCode.UNSUPPORTED` ja existia

## P2.2 - stdio e exemplos de clientes (concluido)

- `--transport stdio` adicionado ao CLI
- `FastMCP.run(transport='stdio')` validado contra SDK instalado
- HTTP local continua padrao
- `docs/clients/` com exemplos para Codex, OpenCode e Claude Code

## P2.3 - Network e console inspection (concluido)

- `browser/inspection.py`: `InspectionState` e `InspectionManager` por tab
- `tools/inspection.py`:
  - `network_enable`, `network_disable`, `network_list`, `network_get_response`
  - `console_enable`, `console_disable`, `console_list` (retornam UNSUPPORTED)
- Network: eventos normalizados, redaction de URLs, limites de retencao
- Console: UNSUPPORTED estruturado (Runtime domain requer validacao adicional Pydoll)
- Tools registradas no MCP

## P2.4 - Diagnostics e trace (concluido)

- `diagnostics_snapshot`: server/browser/tab info sem secrets
- `trace_start`, `trace_stop`, `trace_get`, `trace_cleanup`
- Trace leve em memoria com estrutura minima de eventos
- Sem CDP tracing bruto

## P2.5 - Multi-cliente e browser_attach (concluido)

- `browser_attach` aceita apenas `browser_id` registrado e do mesmo `client_id`
- Recusa qualquer input de endpoint, porta, PID ou URL
- Cross-session attach retorna UNSUPPORTED (seguro por default)
- Isolamento multi-cliente mantido do FIX_11

## P2.6 - Release docs e packaging (concluido)

- Versao `0.1.0a1`
- `LICENSE` MIT criado
- `CHANGELOG.md` criado
- `docs/security.md` criado
- `docs/release-checklist.md` criado
- README atualizado com endpoints, stdio e status alpha
- sdist e wheel built: `pydoll_mcp_server-0.1.0a1.tar.gz` + `.whl`
- Wheel instalado em venv temporaria com sucesso

## Arquivos alterados/criados

- `src/pydoll_mcp_server/server.py` - SCHEMA_VERSION, capabilities, 14 new tool registrations
- `src/pydoll_mcp_server/cli.py` - --transport stdio
- `src/pydoll_mcp_server/browser/inspection.py` - NOVO
- `src/pydoll_mcp_server/tools/inspection.py` - NOVO
- `pyproject.toml` - versao 0.1.0a1
- `LICENSE` - NOVO
- `CHANGELOG.md` - NOVO
- `docs/security.md` - NOVO
- `docs/release-checklist.md` - NOVO
- `README.md` - atualizado

## Gates finais

| Gate | Resultado |
|------|-----------|
| `pytest -q` | **150 passed** |
| `ruff check .` | **All checks passed!** |
| `mypy src` | **Success** (35 source files) |
| `pytest -m browser_smoke -q` | **9 passed** (verificado antes do gate final) |
| `python -m build` | **sdist + wheel gerados** |
| `pip install wheel` em venv temp | **OK** |

## Bloqueios

Nenhum. P2 concluido conforme criterios:
- stdio opcional funciona
- network inspection funciona com redaction
- console inspection retorna UNSUPPORTED estruturado
- diagnostics_snapshot existe sem vazar segredos
- trace leve existe com cleanup seguro
- multi-cliente e isolamento mantidos
- browser_attach recusa browsers de outros clients e cross-session
- wheel instala em ambiente temporario
- todos os gates finais passam

## Proximo passo

Revisao humana antes de publicar release no GitHub/PyPI.
