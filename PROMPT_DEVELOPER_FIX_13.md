# Prompt para o LLM desenvolvedor - FIX_13

```text
Você está no repositório:

C:\Users\Yuri\Documents\Git\pydoll-mcp-server

Use Python:

C:\Users\Yuri\anaconda3\python.exe

Contexto obrigatório:
- Leia AGENTS.md.
- Leia docs/evaluation-2026-06-12-fix12-review.md.
- Leia plans/remediation/FIX_13_POST_FIX12_ACCEPTANCE.md.
- Leia progress/2026-06-12_AGENT_FIX_12.md.
- Consulte a Pydoll local em C:\Users\Yuri\Documents\Git\pydoll se precisar validar comportamento real.
- Não reverta mudanças existentes.
- Não use em dash.
- Preserve UTF-8.
- Não exponha execute_cdp_cmd livre.
- Não crie comandos do sistema operacional.
- Não implemente console real neste FIX.
- Não implemente attach real pós restart neste FIX.

Estado atual confirmado pela reavaliação:
- pytest -q: 181 passed, 2 warnings.
- ruff check .: All checks passed.
- mypy src: Success, 37 source files.
- pytest -m browser_smoke -q: 9 passed.
- stdio sem PYDOLL_MCP_AUTH_TOKEN não falha por autenticação.
- network_list já usa get_network_logs() e retorna eventos úteis em browser real.
- docs/clients existe.

Problemas remanescentes:
1. health_check, server_status e /health ainda reportam version 0.1.0, enquanto pyproject.toml está em 0.1.0a1.
2. TraceManager existe, mas trace_get só recebe eventos reais de trace_start e trace_stop. diagnostics_snapshot e network_* não registram eventos em trace ativo.
3. network_list retorna eventos vazios duplicados quando a Pydoll entrega logs sem params.request.url.
4. Alguns testes P2 importantes usam inspect.getsource em vez de provar comportamento.
5. docs/release-checklist.md ainda registra números antigos, como 150 passed e 35 source files.

Tarefa:
Executar plans/remediation/FIX_13_POST_FIX12_ACCEPTANCE.md em sequência estrita.

Baseline antes de alterar:
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q

T1. Corrigir versão:
- health_check, server_status e /health devem reportar 0.1.0a1.
- Preferir helper centralizado com importlib.metadata.version("pydoll-mcp-server") e fallback seguro.
- Atualizar testes para igualdade com 0.1.0a1.

T2. Integrar trace mínimo:
- Adicionar forma de recuperar trace ativo por client_id.
- Registrar eventos quando houver trace ativo para diagnostics_snapshot, network_enable, network_list, network_get_response e erros estruturados dessas tools.
- Não registrar secrets, response body completo, cookies, storage ou JS completo.
- Testar trace_start -> diagnostics_snapshot -> trace_get.
- Testar trace_start -> network_enable ou network_list com fake -> trace_get.
- Testar evento de erro com error_code.

T3. Limpar network_list:
- Filtrar logs sem params.request.url por padrão.
- Não retornar eventos com url vazia por padrão.
- Manter redaction de query params sensíveis.
- Testar logs mistos com e sem request.url.
- Fazer probe real ou teste equivalente para garantir output útil.

T4. Fortalecer testes:
- Trocar source inspection por testes comportamentais onde possível.
- stdio: monkeypatch _run_stdio e get_config, chamar main() com --transport stdio, provar que get_config não foi chamado.
- network_list: fake tab com get_network_logs instrumentado, provar chamada e normalização.

T5. Atualizar docs:
- Atualizar docs/release-checklist.md com números finais.
- Atualizar progress/YYYY-MM-DD_AGENT_FIX_13.md.
- Ajustar README somente se necessário.

Gates finais obrigatórios:
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q

Critério de conclusão:
Você só terminou quando:
- version reportada é 0.1.0a1;
- trace registra eventos reais além de start/stop;
- network_list não retorna eventos vazios por padrão;
- testes P2 críticos são comportamentais;
- release checklist reflete os números finais;
- todos os gates finais passam.
```

