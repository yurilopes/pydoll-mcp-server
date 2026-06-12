# Prompt para o LLM desenvolvedor - FIX_12

```text
Você está no repositório:

C:\Users\Yuri\Documents\Git\pydoll-mcp-server

Use Python:

C:\Users\Yuri\anaconda3\python.exe

Contexto obrigatório:
- Leia AGENTS.md.
- Leia docs/evaluation-2026-06-12-p2-review.md.
- Leia plans/remediation/PLAN_FIX_12_P2_COMPLETION.md.
- Leia plans/PLAN_P2.md.
- Leia plans/p2/PLAN_P2_02_STDIO_CLIENTS.md.
- Leia plans/p2/PLAN_P2_03_NETWORK_CONSOLE.md.
- Leia plans/p2/PLAN_P2_04_DIAGNOSTICS_TRACE.md.
- Leia plans/p2/PLAN_P2_05_MULTI_CLIENT_ATTACH.md.
- Consulte a Pydoll local em C:\Users\Yuri\Documents\Git\pydoll quando precisar validar API real.
- Não reverta mudanças existentes.
- Não use em dash.
- Preserve UTF-8.
- Não exponha execute_cdp_cmd livre.
- Não crie tool de comando do sistema operacional.
- Não aceite endpoint, porta, PID, URL ou websocket arbitrário para browser_attach.
- Não faça bypass de CAPTCHA, fraude ou evasão.

O que aconteceu de errado:
Você declarou P2 concluído porque os gates antigos continuaram verdes. Isso não é aceite de P2. O total de testes continuou 150, igual ao fim do P1, e as novas tools P2 não tinham cobertura dedicada. Além disso:
- stdio falha sem PYDOLL_MCP_AUTH_TOKEN porque cli.py chama get_config() antes de decidir o transporte.
- network_list não retorna dados úteis em browser real porque o callback lê atributos inexistentes no evento CDP da Pydoll.
- trace_start, trace_stop, trace_get e trace_cleanup são stubs, não trace leve real.
- progress e docs afirmam que docs/clients existe, mas a pasta não existe.
- README e release checklist ainda têm afirmações contraditórias ou falsas.

Como se corrigir:
Trate cada critério de aceite como contrato. Para cada fase, crie teste que falha primeiro ou um probe automatizado equivalente, implemente, rode o teste específico e só então atualize docs. Não marque checklist como completo sem prova funcional.

Tarefa:
Executar plans/remediation/PLAN_FIX_12_P2_COMPLETION.md em sequência estrita.

Baseline antes de alterar:
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q

T1. Corrigir stdio:
- Não instancie config HTTP antes de entrar em stdio.
- stdio não deve exigir PYDOLL_MCP_AUTH_TOKEN por padrão.
- HTTP continua exigindo token por padrão.
- Adicione teste de dispatch CLI ou subprocess controlado.
- Prove que:
  '' | C:\Users\Yuri\anaconda3\python.exe -m pydoll_mcp_server.cli --transport stdio
  não falha por falta de token.

T2. Corrigir network inspection:
- network_list deve usar await pydoll_tab.get_network_logs(filter_url or None).
- Normalize log['params']['requestId'], log['params']['request']['url'], log['params']['request']['method'], log['params']['type'], log['params']['timestamp'].
- Redija token, key, secret, auth, password em URLs.
- network_get_response deve rejeitar request_id vazio com INVALID_INPUT.
- Adicione teste com servidor HTTP local e browser headless provando URL e request_id não vazios.

T3. Corrigir trace:
- Crie TraceManager leve.
- trace_start cria trace real com ownership por client_id.
- trace_get retorna eventos reais.
- trace_stop registra evento e muda status.
- trace_cleanup remove traces antigos de forma segura.
- Registre eventos mínimos para trace_start, diagnostics_snapshot, network_*, trace_stop e erros estruturados.
- Redija bearer token, cookies, Authorization, storage e JS completo.
- Adicione testes de start, get, stop, cleanup, redaction e isolamento por client.

T4. Completar testes P2:
- Adicione cobertura para server_status.capabilities, stdio, network, console UNSUPPORTED, diagnostics_snapshot, trace, browser_attach e versionamento.
- O comando abaixo deve retornar testes reais:
  rg "network_enable|network_list|console_enable|diagnostics_snapshot|trace_start|browser_attach|stdio" tests -n

T5. Corrigir documentação:
- Crie docs/clients/ com exemplos para Codex, OpenCode e Claude Code.
- Corrija README removendo afirmações obsoletas como "stdio ainda é P2".
- Corrija docs/security.md e docs/release-checklist.md para refletirem apenas o que foi validado.
- Atualize progress/YYYY-MM-DD_AGENT_FIX_12.md com resumo curto e honesto.

T6. Browser attach:
- Se attach real não for seguro, mantenha UNSUPPORTED.
- Mesmo assim, teste ownership, browser inexistente, browser de outro client e ausência de inputs arbitrários.
- Se implementar metadata runtime, não persista dados sensíveis e não mate Chrome pessoal no cleanup.

Gates finais obrigatórios:
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q

Critério de conclusão:
Você só terminou quando:
- stdio inicia sem token HTTP obrigatório;
- network_list retorna dados reais e úteis;
- trace_* não é stub;
- P2 tem testes próprios;
- docs/clients existe;
- README, security docs e release checklist não fazem afirmações falsas;
- todos os gates finais passam;
- progress registra exatamente o que foi validado.
```

