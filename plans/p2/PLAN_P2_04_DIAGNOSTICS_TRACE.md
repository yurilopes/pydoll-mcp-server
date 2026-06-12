# PLAN_P2_04: Diagnostics snapshot e trace leve

## Objetivo

Fornecer diagnóstico operacional e trace leve para reproduzir falhas de agentes, sem usar tracing CDP bruto e sem vazar segredos.

## Escopo

- Implementar `diagnostics_snapshot`.
- Implementar `trace_start`, `trace_stop`, `trace_get`, `trace_cleanup`.
- Registrar tool calls, erros, duração, browser_id, tab_id e eventos resumidos.
- Integrar network e console resumidos quando habilitados.
- Salvar artifacts somente em diretórios permitidos.

## Fora de Escopo

- Tracing CDP bruto.
- Captura automática de todos os screenshots.
- Zip contendo cookies, storage ou payloads completos.
- Upload externo de artifacts.

## Pré-requisitos

- P2.1 concluído.
- P2.3 concluído ou documentado como parcialmente unsupported.

## Critérios de Início

- Ler `src/pydoll_mcp_server/logging.py`.
- Ler estado atual de `ServerState` em `server.py`.
- Confirmar diretórios runtime em `config.py`.

## Tarefas Detalhadas

1. Criar armazenamento leve de diagnostics em memória com limite de retenção.
2. `diagnostics_snapshot(client_id, include_clients=false)` deve retornar:
   - `schema_version`
   - server uptime
   - auth mode
   - browsers do client
   - tabs do client
   - health por recurso
   - contadores de erros
   - paths runtime redigidos ou resumidos
   - capabilities
3. Snapshot não deve incluir:
   - bearer token
   - cookie values
   - storage values
   - código JS completo
   - response body completo
4. Trace leve:
   - `trace_start(client_id, name="", include_screenshots=false)`
   - `trace_stop(client_id, trace_id)`
   - `trace_get(client_id, trace_id, max_events=200)`
   - `trace_cleanup(client_id, older_than_seconds=86400)`
5. Trace deve armazenar no runtime artifacts dir do cliente.
6. Trace event mínimo:
   - timestamp
   - tool
   - status
   - duration_ms
   - browser_id
   - tab_id
   - error_code
   - redacted summary
7. Integrar com logger ou wrappers de tool sem criar dependência circular.
8. Se capturar screenshot opcional, usar path validado e nunca fora do artifacts dir.
9. Criar testes unitários para redaction e cleanup.

## Critérios de Aceite

- `diagnostics_snapshot` funciona sem browser aberto.
- Snapshot com browser aberto não vaza segredos.
- Trace pode iniciar, receber eventos, parar e ser lido.
- Cleanup remove artifacts antigos dentro do diretório permitido.

## Definição de Pronto

- Agentes têm uma tool de diagnóstico segura para handoff e troubleshooting.
- Trace leve é útil sem introduzir risco de exfiltração.

## Como Testar

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest tests\unit -q
C:\Users\Yuri\anaconda3\python.exe -m pytest tests\contract -q
```

## Riscos

- Criar logs duplicados ou circular imports.
- Salvar artifacts fora do runtime dir.
- Armazenar dados sensíveis em eventos.

## Estratégia de Recuperação

Se integração automática de tool calls for arriscada, implementar trace manual inicial e registrar apenas eventos explícitos de diagnostics, network e console.

## Artefatos Esperados

- Tools de diagnostics e trace registradas.
- Tests unitários.
- README e docs de segurança atualizados.

## Notas Para o Próximo Agente

Trace leve é o padrão. Não implemente CDP Tracing neste P2.
