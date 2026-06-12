# Prompt Para Desenvolvedor P2

```text
Você está no repositório:

C:\Users\Yuri\Documents\Git\pydoll-mcp-server

Use Python:

C:\Users\Yuri\anaconda3\python.exe

Contexto obrigatório:
- Leia AGENTS.md.
- Leia README.md.
- Leia plans/PLAN_P1.md.
- Leia progress/2026-06-12_AGENT_PLAN_P1.md.
- Leia plans/PLAN_P2.md.
- Leia todos os arquivos em plans/p2/.
- Consulte a Pydoll local em C:\Users\Yuri\Documents\Git\pydoll quando precisar validar capacidade real.
- Não reverta mudanças existentes.
- Não use em dash.
- Preserve UTF-8.
- Não exponha execute_cdp_cmd livre.
- Não crie tool de comando do sistema operacional.
- Não faça bypass de CAPTCHA, fraude ou evasão de segurança.

Estado atual confirmado:
- P1 rebaseado concluído.
- pytest -q: 150 passed.
- ruff check .: All checks passed.
- mypy src: Success, 33 source files.
- pytest -m browser_smoke -q: 9 passed.
- HTTP local, auth bearer, page_get_tree, element_id, UTF-8 fill, deep iframe, nested iframe, shadow DOM aberto, locks comportamentais e redaction já existem.

Objetivo:
Executar o P2 em sequência estrita, usando plans/PLAN_P2.md como índice e plans/p2/PLAN_P2_01 a PLAN_P2_06 como planos detalhados.

P2.0 Baseline:
- Rodar:
  C:\Users\Yuri\anaconda3\python.exe -m pytest -q
  C:\Users\Yuri\anaconda3\python.exe -m ruff check .
  C:\Users\Yuri\anaconda3\python.exe -m mypy src
  C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
- Registrar baseline em progress/YYYY-MM-DD_AGENT_PLAN_P2.md.

P2.1 API contract:
- Adicionar schema_version nos outputs principais.
- Adicionar capabilities em server_status.
- Garantir sucesso ou erro estruturado em toda tool nova.
- Adicionar ErrorCode.UNSUPPORTED se ausente.
- Testar catálogo MCP e ausência de tools proibidas.

P2.2 stdio:
- Adicionar transporte stdio opcional usando FastMCP.run("stdio") ou equivalente validado no SDK instalado.
- HTTP local continua padrão.
- Documentar exemplos para Codex, OpenCode e Claude Code.
- Testar listagem de tools via stdio quando possível.

P2.3 network e console:
- Implementar network_enable, network_disable, network_list, network_get_response usando APIs reais da Pydoll.
- Redigir Authorization, Cookie, Set-Cookie, Proxy-Authorization e tokens.
- Implementar console_enable, console_disable, console_list usando Runtime.consoleAPICalled se viável.
- Limitar retenção por tab a 1000 eventos por padrão.
- Se console não for viável, retornar UNSUPPORTED estruturado e documentar.

P2.4 diagnostics e trace:
- Implementar diagnostics_snapshot sem segredos.
- Implementar trace leve próprio: tool calls, erros redigidos, screenshots opcionais, network e console resumidos quando habilitados.
- Salvar artifacts somente em diretórios permitidos.
- Implementar trace_cleanup.

P2.5 multi-cliente e attach:
- Adicionar stress leve com 2 clientes, 2 browsers e 4 tabs.
- Persistir metadata runtime mínima de browsers lançados pelo servidor.
- Implementar startup cleanup de metadata stale sem matar Chrome pessoal.
- Implementar browser_attach somente para browser_id registrado e pertencente ao mesmo client_id.
- Recusar endpoint, porta, PID ou URL arbitrários fornecidos pelo cliente.

P2.6 release docs:
- Definir versão 0.1.0a1.
- Criar LICENSE se ausente.
- Criar CHANGELOG.md.
- Criar docs/security.md.
- Criar docs/release-checklist.md.
- Atualizar README com P2.
- Validar build sdist e wheel.
- Instalar wheel em ambiente temporário e rodar smoke mínimo.
- Preparar release checklist, sem publicar nada.

Gates finais obrigatórios:
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q

Critério de conclusão:
Você terminou apenas quando:
- stdio opcional funciona ou tem limitação documentada com teste.
- network inspection funciona com redaction.
- console inspection funciona ou retorna UNSUPPORTED estruturado.
- diagnostics_snapshot existe e não vaza segredos.
- trace leve existe com cleanup seguro.
- multi-cliente e isolamento passam em teste.
- browser_attach só aceita browsers lançados pelo servidor e do mesmo client_id.
- wheel instala em ambiente temporário.
- todos os gates finais passam.
- progress/YYYY-MM-DD_AGENT_PLAN_P2.md está atualizado.
```
