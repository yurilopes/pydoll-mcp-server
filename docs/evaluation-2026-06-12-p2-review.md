# Reavaliação P2 - 2026-06-12

## Resultado

P2 não deve ser aceito como concluído ainda.

Os gates principais estão verdes na minha execução local, mas a implementação não cumpre critérios funcionais centrais do P2. O problema principal foi tratar "tests still pass" como aceite, sem adicionar testes P2 e sem validar fluxos reais para as novas tools.

## Gates reexecutados

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
# 150 passed, 2 warnings

C:\Users\Yuri\anaconda3\python.exe -m ruff check .
# All checks passed!

C:\Users\Yuri\anaconda3\python.exe -m mypy src
# Success: no issues found in 35 source files

C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
# 9 passed, 141 deselected
```

## O que foi entregue corretamente

- `schema_version` foi adicionado em `health_check` e `server_status`.
- `server_status.capabilities` foi adicionado.
- As tools P2 foram registradas no catálogo MCP.
- `--transport stdio` foi adicionado ao CLI.
- `console_*` retorna `UNSUPPORTED`, o que é aceitável se bem documentado e testado.
- `LICENSE`, `CHANGELOG.md`, `docs/security.md`, `docs/release-checklist.md` e artifacts de build existem.

## Achados

### 1. `stdio` falha sem `PYDOLL_MCP_AUTH_TOKEN`

Severidade: bloqueador P2.

Evidência:

- `src/pydoll_mcp_server/cli.py:46` chama `get_config()` antes de decidir o transporte.
- `src/pydoll_mcp_server/cli.py:48` só depois verifica `args.transport == 'stdio'`.
- `plans/p2/PLAN_P2_02_STDIO_CLIENTS.md:39` exige que `stdio` não requeira `PYDOLL_MCP_AUTH_TOKEN` por padrão.

Probe executado:

```powershell
'' | C:\Users\Yuri\anaconda3\python.exe -m pydoll_mcp_server.cli --transport stdio
```

Resultado: falha com `ValidationError`, exigindo `PYDOLL_MCP_AUTH_TOKEN`.

Correção esperada:

- Não instanciar config HTTP antes de entrar no transporte `stdio`.
- `stdio` deve iniciar sem token por padrão.
- Adicionar teste de CLI dispatch ou teste subprocess controlado.

### 2. `network_list` não retorna dados úteis em browser real

Severidade: bloqueador P2.

Evidência:

- `plans/p2/PLAN_P2_03_NETWORK_CONSOLE.md:47` exige usar `await tab.get_network_logs(filter)`.
- `src/pydoll_mcp_server/tools/inspection.py:32` cria callback manual `on_network_event`.
- `src/pydoll_mcp_server/tools/inspection.py:48` registra `Network.requestWillBeSent`.
- O evento real da Pydoll é dict CDP com `params`, mas a implementação tenta ler atributos como `event.request`, `event.url`, `event.method`.

Probe real com browser headless:

```json
{
  "success": true,
  "events": [
    {"request_id": "", "url": "", "method": "", "type": "", "timestamp": 0},
    {"request_id": "", "url": "", "method": "", "type": "", "timestamp": 0},
    {"request_id": "", "url": "", "method": "", "type": "", "timestamp": 0}
  ],
  "count": 3,
  "total": 3
}
```

Correção esperada:

- `network_list` deve usar `await pydoll_tab.get_network_logs(filter_url or None)`.
- Normalizar `log['params']['requestId']`, `log['params']['request']['url']`, `log['params']['request']['method']`, `log['params']['type']`, `log['params']['timestamp']`.
- Manter callback apenas se houver teste real provando utilidade adicional.
- Adicionar teste browser real ou integração com fixture HTTP local que prove URLs e `request_id` não vazios.

### 3. `trace_*` é stub, não trace leve

Severidade: bloqueador P2.

Evidência:

- `src/pydoll_mcp_server/server.py:615` cria `trace_id`, mas não registra estado.
- `src/pydoll_mcp_server/server.py:639` retorna sempre `events: []`.
- `src/pydoll_mcp_server/server.py:653` retorna sempre `cleaned: 0`.
- `plans/p2/PLAN_P2_04_DIAGNOSTICS_TRACE.md:57` exige armazenamento no runtime artifacts dir do cliente.
- `docs/security.md:68` afirma que trace events são armazenados no runtime artifacts dir, mas isso não ocorre.

Correção esperada:

- Criar um `TraceManager` leve, com retenção limitada, ownership por `client_id`, redaction e cleanup seguro.
- Registrar pelo menos eventos explícitos de `trace_start`, `trace_stop`, `diagnostics_snapshot`, `network_*` e erros estruturados. Se integração automática de todas as tools for grande demais, documentar esse limite.
- `trace_get` deve retornar eventos reais do trace.
- `trace_cleanup` deve remover traces expirados dentro de diretório permitido.
- Adicionar testes unitários de start, get, stop, cleanup, redaction e isolamento por client.

### 4. P2 não adicionou testes dedicados

Severidade: alto.

Evidência:

- O total continua 150 testes, mesmo número do fim de P1.
- `rg "network_enable|network_list|console_enable|diagnostics_snapshot|trace_start|browser_attach|stdio" tests -n` não retornou cobertura.

Correção esperada:

- Adicionar testes P2 para stdio, network, console `UNSUPPORTED`, diagnostics, trace, browser_attach e catálogo MCP.
- Não aceitar P2 apenas porque os testes antigos continuam verdes.

### 5. Documentação e progresso afirmam entregas inexistentes

Severidade: alto.

Evidência:

- `progress/2026-06-12_AGENT_PLAN_P2.md:25` afirma que `docs/clients/` existe, mas `Test-Path docs\clients` retornou `False`.
- `README.md:216` ainda diz que transporte `stdio` é P2.
- `README.md:217` ainda diz que inspeção completa de network e console é P2.
- `docs/release-checklist.md:36` marca network como concluído, mas o probe real mostrou dados vazios.
- `docs/security.md:68` afirma armazenamento de trace em runtime artifacts dir, mas o código não armazena trace.

Correção esperada:

- Criar docs reais de clientes ou remover alegação.
- Atualizar README para estado real após correção.
- Não marcar release checklist como completo até haver testes e probes funcionais.
- Corrigir progress para refletir o que foi validado de fato.

### 6. `browser_attach` não implementa metadata runtime e não testa isolamento

Severidade: médio.

Evidência:

- `plans/p2/PLAN_P2_05_MULTI_CLIENT_ATTACH.md` pede metadata runtime mínima e cleanup stale.
- Não há metadata runtime em `src/pydoll_mcp_server/browser/registry.py`.
- `browser_attach` retorna `UNSUPPORTED` mesmo para browser registrado no mesmo processo.
- Não há testes P2 para cross-client attach ou recusa de inputs arbitrários.

Correção esperada:

- Se attach real não for seguro, manter `UNSUPPORTED`, mas implementar metadata runtime mínima ou ajustar o plano/documentação para assumir explicitamente que metadata fica fora do P2.
- Adicionar testes de ownership e de que a tool não aceita endpoint, porta, PID ou URL.

### 7. Versão reportada diverge da versão do pacote

Severidade: médio.

Evidência:

- `pyproject.toml` está em `0.1.0a1`.
- `health_check` e `server_status` retornam `version: 0.1.0`.

Correção esperada:

- Centralizar versão ou atualizar para `0.1.0a1`.
- Adicionar teste para consistência entre metadata do pacote e status.

## Diagnóstico do erro de execução

O desenvolvedor executou os gates, mas não leu os critérios de aceite como contrato. O P2 pedia funcionalidades novas com testes novos. Como não houve testes P2, os gates apenas provaram que P1 continuou passando.

O padrão incorreto foi:

1. Registrar tools no servidor.
2. Criar implementações mínimas ou stubs.
3. Atualizar docs e checklist como concluído.
4. Rodar testes antigos.
5. Declarar P2 completo.

O padrão correto deve ser:

1. Para cada fase do plano, criar primeiro um teste que falhe pelo comportamento esperado.
2. Validar a API real da Pydoll local antes de implementar wrapper.
3. Implementar só até o teste e o aceite passarem.
4. Fazer probe real quando a funcionalidade depende de browser, network, stdio ou filesystem.
5. Atualizar docs apenas com o que foi provado.
6. Reavaliar o próprio progresso contra os critérios de aceite do plano, não contra o número global de testes.

## Recomendação

Executar `plans/remediation/PLAN_FIX_12_P2_COMPLETION.md` antes de aceitar P2 ou seguir para release.

