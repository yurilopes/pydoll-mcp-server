# PLAN_P2_01: API contract, schema_version e capabilities

## Objetivo

Padronizar o contrato MCP antes de adicionar novas ferramentas P2, para que agentes consigam descobrir capacidades, interpretar outputs e se recuperar de erros sem decisões adicionais.

## Escopo

- Adicionar `schema_version` aos outputs principais.
- Adicionar `capabilities` em `server_status`.
- Definir convenção de resposta para tools novas.
- Garantir catálogo MCP com todas as tools P0, P1 e P2 esperadas.
- Documentar formato mínimo de erro estruturado.

## Fora de Escopo

- Implementar network, console, trace, stdio ou attach nesta fase.
- Renomear tools existentes.
- Fazer breaking changes em inputs já usados no P1.

## Pré-requisitos

- P1 verde.
- `plans/PLAN_P2.md` rebaseado.
- Baseline registrado em `progress/YYYY-MM-DD_AGENT_PLAN_P2.md`.

## Critérios de Início

- `pytest`, `ruff`, `mypy` e `browser_smoke` passaram no baseline.
- O agente leu `src/pydoll_mcp_server/server.py` e `tests/contract/test_mcp_contract.py`.

## Tarefas Detalhadas

1. Definir constante interna de schema, por exemplo `SCHEMA_VERSION = "2026-06-12.p2"`.
2. Adicionar `schema_version` em:
   - `health_check`
   - `server_status`
   - outputs das tools P2 novas conforme forem adicionadas.
3. Adicionar `capabilities` em `server_status` com grupos:
   - `transports`: `http`, `sse`, `stdio`
   - `browser`: launch, close, list, attach policy
   - `page`: navigation, tree, deep tree, screenshot
   - `elements`: find, find_deep, click, type, fill, attributes
   - `diagnostics`: health, status, diagnostics_snapshot, trace
   - `inspection`: network, console
   - `security`: auth, redaction, path allowlist, no free CDP
4. Para tools novas, retornar sempre:
   - sucesso: `{"success": true, "schema_version": "...", ...}`
   - erro: `StructuredError.to_dict()` com `error_code`, `message`, `retryable` e `resource_state` quando aplicável.
5. Verificar se `ErrorCode` possui `UNSUPPORTED`.
   - Se não houver, adicionar `UNSUPPORTED` sem quebrar códigos existentes.
6. Atualizar testes de contrato para validar:
   - `server_status.capabilities`
   - `schema_version`
   - ausência de tools proibidas
   - presença das tools P2 quando registradas nas fases seguintes.

## Critérios de Aceite

- `server_status(client_id="x")` retorna `schema_version`.
- `server_status` retorna `capabilities` com grupos úteis para agentes.
- Nenhuma tool proibida aparece no catálogo MCP.
- Teste de contrato falha se `schema_version` desaparecer.

## Definição de Pronto

- Contrato base P2 está documentado e testado.
- Fases seguintes podem adicionar tools sem redesenhar o contrato.

## Como Testar

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest tests\contract -q
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
```

## Riscos

- Quebrar clientes existentes se outputs antigos forem alterados de forma incompatível.
- Capabilities prometerem ferramenta ainda não implementada.

## Estratégia de Recuperação

Se uma alteração quebrar contrato existente, manter campos antigos e adicionar campos novos de forma compatível. Não renomear keys usadas por P1.

## Artefatos Esperados

- Tests de contrato atualizados.
- `server_status` com `schema_version` e `capabilities`.
- Progresso registrado.

## Notas Para o Próximo Agente

Não avance para stdio ou network se o catálogo MCP estiver instável.
