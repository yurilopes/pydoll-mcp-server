# Plano geral do Pydoll MCP Server

## Visão do produto

Este projeto deve criar um servidor MCP em Python para automação de navegador baseada na biblioteca Pydoll. O objetivo é oferecer uma alternativa ao Playwright MCP Server, com ergonomia previsível para agentes, mas sem copiar a API ou a arquitetura do Playwright.

O servidor deve empoderar agentes para navegar, observar, interagir, diagnosticar e se recuperar de falhas em páginas modernas. Isso inclui páginas com UTF-8, conteúdo internacional, iframes, OOPIFs, shadow DOM aberto ou fechado, múltiplas abas e múltiplos clientes MCP.

## Objetivos

- Expor um MCP server Python baseado em Pydoll.
- Usar async/await internamente sem bloquear o event loop.
- Atender clientes MCP por HTTP local, com Streamable HTTP em `/mcp` e SSE em `/sse` quando viável.
- Usar bind seguro por padrão em `127.0.0.1`.
- Exigir bearer token por padrão.
- Suportar múltiplos clientes MCP simultâneos com isolamento por `client_id`.
- Fornecer comportamento previsível de tool: a chamada só retorna quando a ação foi concluída, falhou, expirou ou foi cancelada.
- Fornecer camada Playwright-like em semântica, sem copiar nomes ou detalhes internos do Playwright.
- Tratar frames, iframes, OOPIFs e shadow roots como requisitos centrais, não como casos extras.
- Documentar claramente métodos sensíveis, proibidos e políticas de segurança.
- Permitir retomada por outros agentes por meio de planos detalhados e registros em `progress/`.

## Não objetivos

- Não implementar o servidor MCP durante a fase de artefatos iniciais.
- Não expor `execute_cdp_cmd` livre.
- Não automatizar bypass de CAPTCHA, fraude, abuso, stealth malicioso ou evasão de segurança.
- Não interferir no navegador Chrome pessoal do usuário.
- Não depender exclusivamente de sites externos para testes.
- Não assumir capacidades da Pydoll sem validação no código local ou na documentação vendorizada.

## Fontes locais verificadas

- Repositório deste projeto: `C:\Users\Yuri\Documents\Git\pydoll-mcp-server`.
- Repositório local da Pydoll: `C:\Users\Yuri\Documents\Git\pydoll`.
- Remoto Pydoll: `https://github.com/autoscrape-labs/pydoll.git`.
- Commit Pydoll verificado: `59330abf`.
- Versão Pydoll local em `pyproject.toml`: `2.23.0`.
- Documentação vendorizada: `references/pydoll-docs/`.
- Python local via Anaconda: `C:\Users\Yuri\anaconda3\python.exe`.

## Decisões arquiteturais iniciais

- Transporte P0: HTTP local, Streamable HTTP em `/mcp`, SSE em `/sse` quando viável.
- `stdio`: fora do P0, planejado como P2.
- Bind padrão: `127.0.0.1`.
- Autenticação: bearer token obrigatório por padrão. O servidor deve exigir `PYDOLL_MCP_AUTH_TOKEN`. Modo sem autenticação só pode existir com variável explícita de desenvolvimento, por exemplo `PYDOLL_MCP_ALLOW_NO_AUTH=true`.
- Identidade: `client_id` explícito em tools de lifecycle e em operações que acessam estado.
- Isolamento: browsers, tabs, janelas, contextos, perfis, caches de elementos e artefatos pertencem ao `client_id`, exceto quando uma tool aceitar compartilhamento explícito.
- Perfil persistente padrão: um perfil por `client_id`, em diretório de app data do usuário.
- Perfis persistentes nomeados: disponíveis via `profile_id`, com lock exclusivo.
- Perfil temporário: disponível por chamada em `browser_launch`.
- Navegador: Chrome ou Chromium controlado por Pydoll, visível por padrão, headless configurável.
- Concorrência: locks por recurso. Duas ações mutantes na mesma aba não podem rodar ao mesmo tempo. Ações em abas ou browsers independentes podem rodar em paralelo.
- Timeouts: nenhuma operação pode ficar sem timeout.
- Erros: toda tool deve retornar erro estruturado com `error_code`, `message`, `details`, `retryable`, `resource_state` e `recovery_hint`.

## Stack recomendada

- Python `>=3.10`.
- `mcp[cli]` com FastMCP.
- Starlette e Uvicorn para servidor HTTP local.
- Pydantic v2 para schemas de entrada, saída e configuração.
- `pydoll-python`.
- `pytest`, `pytest-asyncio`, `pytest-cov`.
- `ruff` para lint e format.
- `mypy` para checagem gradual.

## Diretórios runtime planejados

O código não deve gravar dados runtime dentro do repositório por padrão.

- Windows: `%LOCALAPPDATA%\pydoll-mcp-server`.
- macOS: `~/Library/Application Support/pydoll-mcp-server`.
- Linux/Unix: `~/.local/share/pydoll-mcp-server`.

Subpastas planejadas:

- `profiles/{safe_client_id}/default/`
- `profiles/{safe_client_id}/{profile_id}/`
- `tmp/{safe_client_id}/`
- `downloads/{safe_client_id}/`
- `artifacts/{safe_client_id}/`
- `logs/`

## IDs e validade

- `browser_id`: estável enquanto o browser existir.
- `context_id`: estável enquanto o contexto existir.
- `window_id`: mapeado do Browser CDP quando disponível.
- `tab_id`: estável enquanto o target existir.
- `frame_id`: derivado de frame path, target ou contexto Pydoll quando disponível.
- `element_id`: referência curta reutilizável entre chamadas, mas não permanente.

`element_id` deve ser invalidado quando houver navegação, reload, fechamento de aba, mudança de documento, erro de stale object ou troca de frame context. O cache deve manter selector hints, xpath hints, frame path, shadow path, texto resumido e bounding box para tentar reaquisição controlada.

## Roadmap por fases

1. Levantar Pydoll, vendorizar docs e validar capacidades.
2. Criar esqueleto do projeto Python e servidor MCP mínimo.
3. Implementar registry, lifecycle, perfis, sessões, browsers, tabs e janelas.
4. Implementar navegação e waits previsíveis.
5. Implementar observação de página e árvores compactas.
6. Implementar busca e interação por elementos.
7. Implementar traversal profundo para iframes, OOPIFs e shadow roots.
8. Implementar JavaScript sensível, helpers CDP seguros, cookies, storage, upload e download.
9. Implementar resiliência, health checks e recovery.
10. Endurecer segurança, permissões, logs e métodos proibidos.
11. Implementar testes de contrato, concorrência e fixtures locais.
12. Documentar uso, exemplos e preparar release experimental.

## Planos detalhados

- `plans/PLAN_01.md`: Levantamento da Pydoll, documentação local e validação de capacidades.
- `plans/PLAN_02.md`: Arquitetura MCP, configuração Python e servidor mínimo.
- `plans/PLAN_03.md`: Lifecycle de browser, sessões, perfis, janelas e abas.
- `plans/PLAN_04.md`: Navegação, waits robustos e semântica Playwright-like.
- `plans/PLAN_05.md`: Observação de página, árvores, UTF-8 e extração semântica.
- `plans/PLAN_06.md`: Busca e interação com elementos.
- `plans/PLAN_07.md`: Frames, iframes, OOPIFs e shadow DOM.
- `plans/PLAN_08.md`: JavaScript execution e helpers seguros CDP-backed.
- `plans/PLAN_09.md`: Resiliência, health checks, timeouts e recovery.
- `plans/PLAN_10.md`: Segurança, permissões, logging e métodos proibidos.
- `plans/PLAN_11.md`: Testes, fixtures locais, contrato MCP e concorrência.
- `plans/PLAN_12.md`: Documentação, exemplos e release experimental.

Os planos devem ser executados em sequência estrita.

## API MCP proposta

Todas as tools devem receber ou derivar `request_id`, registrar `client_id`, respeitar timeout, validar ownership do recurso e retornar JSON serializável.

| Tool | Prioridade | Objetivo | Inputs principais | Output esperado | Erros esperados | Segurança | Concorrência |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `health_check` | P0 | Verificar saúde básica do servidor. | `include_runtime=false` | status, versão, uptime, auth_mode | config inválida | Não expor segredos. | Sem lock. |
| `server_status` | P0 | Diagnóstico agregado do servidor. | `client_id`, `include_clients=false` | contadores, browsers do cliente, limites | auth, client desconhecido | Não listar recursos de outros clientes. | Lock de registry para leitura. |
| `browser_launch` | P0 | Lançar browser Pydoll isolado. | `client_id`, `headless`, `profile_mode`, `profile_id`, `browser` | `browser_id`, `tab_id`, perfil, headless | launch timeout, perfil locked | Não usar Chrome pessoal. Token obrigatório. | Lock por `client_id` e perfil. |
| `browser_list` | P0 | Listar browsers do cliente. | `client_id` | lista de browsers visíveis ao cliente | auth | Isolamento por `client_id`. | Leitura do registry. |
| `browser_close` | P0 | Fechar browser controlado pelo servidor. | `client_id`, `browser_id` | estado final, tabs fechadas | not found, close timeout | Só owner fecha. | Lock do browser. |
| `browser_attach` | P2 | Anexar a instância lançada pelo servidor. | `client_id`, `browser_id` | browser reanexado | unsupported, unhealthy | Nunca anexar ao Chrome pessoal. | Lock do browser. |
| `window_list` | P1 | Listar janelas do browser. | `client_id`, `browser_id` | janelas, bounds quando disponível | not found | Só recursos do cliente. | Lock de leitura. |
| `window_set_bounds` | P1 | Alterar posição, tamanho ou estado da janela. | `client_id`, `window_id`, bounds | bounds finais | invalid bounds | Pode afetar abas da janela. | Lock da janela. |
| `tab_list` | P0 | Listar tabs do cliente. | `client_id`, `browser_id` opcional | tabs, urls, títulos, saúde | not found | Só owner. | Leitura do registry. |
| `tab_activate` | P0 | Trazer tab para frente. | `client_id`, `tab_id` | tab ativa | tab closed | Sem dados sensíveis. | Lock da tab. |
| `tab_close` | P0 | Fechar tab. | `client_id`, `tab_id` | estado final | tab closed, timeout | Só owner. | Lock da tab. |
| `tab_recover` | P0 | Recuperar tab unhealthy de forma explícita. | `client_id`, `tab_id`, `mode=reload|recreate`, `force=false` | ações tentadas, tab final | recovery failed | Recreate pode perder estado, exige opção explícita. | Lock exclusivo da tab. |
| `page_goto` | P0 | Navegar e aguardar estado robusto. | `client_id`, `tab_id`, `url`, `timeout=30` | url final, load_state, timing | navigation error, timeout | Validar URL e registrar sem segredos. | Lock mutante da tab. |
| `page_reload` | P0 | Recarregar página com timeout. | `client_id`, `tab_id`, `ignore_cache`, `timeout=30` | load_state, timing | timeout | Sem segredos. | Lock mutante da tab. |
| `page_back` | P1 | Voltar histórico. | `client_id`, `tab_id`, `timeout=15` | url final | no history, timeout | Sem segredos. | Lock mutante da tab. |
| `page_forward` | P1 | Avançar histórico. | `client_id`, `tab_id`, `timeout=15` | url final | no history, timeout | Sem segredos. | Lock mutante da tab. |
| `page_wait` | P0 | Aguardar load, selector, text ou idle heurístico. | `client_id`, `tab_id`, `state`, `selector`, `text`, `timeout` | matched, timing | timeout | Não capturar conteúdo além do necessário. | Lock compartilhado, mutante se precisar polling agressivo. |
| `page_screenshot` | P0 | Capturar screenshot da página. | `client_id`, `tab_id`, `format`, `full_page`, `as_base64`, `path` | base64 ou artifact path | screenshot failed | Path só em diretório permitido. | Lock de observação da tab. |
| `page_get_text` | P0 | Extrair texto visível ou documento resumido. | `client_id`, `tab_id`, `max_chars` | texto UTF-8, truncation | timeout | Redigir padrões sensíveis configurados. | Lock de observação. |
| `page_get_tree` | P0 | Retornar árvore compacta limitada. | `client_id`, `tab_id`, `max_depth`, `max_nodes` | nós, element_ids, hints | timeout, truncated | Limites obrigatórios. | Lock de observação. |
| `page_get_tree_deep` | P1 | Traversal robusto com iframes e shadow roots. | `client_id`, `tab_id`, `max_depth`, `max_nodes`, `timeout=20` | frame tree, shadow paths, element_ids | timeout, partial | Opt-in por custo e exposição. | Lock de observação caro. |
| `element_find` | P0 | Encontrar elemento no DOM principal ou escopo informado. | `client_id`, `tab_id`, selector, strategy, timeout=15 | element_id, metadata | not found, timeout | Limitar retorno. | Lock de observação. |
| `element_find_deep` | P1 | Buscar em DOM, iframes e shadow roots. | `client_id`, `tab_id`, selector, strategy, timeout=20 | matches, paths | timeout, partial | Opt-in e limitado. | Lock de observação caro. |
| `element_click` | P0 | Clicar elemento e aguardar pós-ação. | `client_id`, `tab_id`, `element_id`, `timeout=10`, wait policy | estado pós-clique | stale, not clickable, timeout | Só elementos do cliente. | Lock mutante da tab. |
| `element_type` | P0 | Digitar texto incremental. | `client_id`, `tab_id`, `element_id`, `text`, `delay` | chars typed | stale, not editable | Preservar UTF-8, não logar texto completo. | Lock mutante da tab. |
| `element_fill` | P0 | Limpar e preencher campo. | `client_id`, `tab_id`, `element_id`, `value` | value length, success | not editable, timeout | Não logar valor completo. | Lock mutante da tab. |
| `element_get_text` | P0 | Ler texto do elemento. | `client_id`, `tab_id`, `element_id`, `max_chars` | texto, truncated | stale | Redaction aplicável. | Lock de observação. |
| `element_get_attribute` | P0 | Ler atributo específico. | `client_id`, `tab_id`, `element_id`, `name` | valor, exists | stale | Atributos sensíveis podem ser redigidos. | Lock de observação. |
| `element_screenshot` | P1 | Screenshot de elemento. | `client_id`, `tab_id`, `element_id`, `path` | artifact path ou base64 | stale, unsupported | Path permitido. | Lock de observação. |
| `js_evaluate_readonly` | P0 | Inspeção JS com tentativa de bloquear side effects. | `client_id`, `tab_id`, `script`, `timeout=5` | valor JSON, truncated | blocked pattern, timeout | Sensível, limites de código e resultado. | Lock da tab, preferir leitura. |
| `js_evaluate` | P0 | Executar JS com efeitos colaterais permitidos. | `client_id`, `tab_id`, `script`, `timeout=5` | valor JSON, audit summary | blocked pattern, timeout | Tool sensível, auditada, desabilitável. | Lock mutante da tab. |
| `user_agent_set` | P0 | Alterar user-agent com helper seguro CDP-backed. | `client_id`, `tab_id` ou `browser_id`, `user_agent` | user-agent aplicado | invalid UA | Não expor CDP livre. | Lock da tab ou browser. |
| `viewport_set` | P0 | Ajustar viewport quando suportado. | `client_id`, `tab_id`, width, height, scale | viewport final | invalid size, unsupported | Limites mínimos e máximos. | Lock da tab. |
| `cookies_get` | P1 | Ler cookies delimitados. | `client_id`, `browser_id` ou `tab_id`, `url_filter`, `redact=true` | cookies redigidos por padrão | denied | Sensível, auditado, escopo obrigatório. | Lock de contexto. |
| `cookies_set` | P1 | Definir cookies delimitados. | `client_id`, `browser_id` ou `tab_id`, cookies | count, domains | invalid cookie | Sensível, auditado. | Lock de contexto. |
| `storage_get` | P1 | Ler local/session storage delimitado. | `client_id`, `tab_id`, `origin`, `keys`, `redact=true` | itens redigidos | denied, timeout | Sensível, escopo obrigatório. | Lock da tab. |
| `storage_set` | P1 | Escrever local/session storage delimitado. | `client_id`, `tab_id`, `origin`, items | count | denied, timeout | Sensível, auditado. | Lock mutante da tab. |
| `download_expect` | P1 | Aguardar download acionado por ação. | `client_id`, `tab_id`, action ref, timeout=60 | artifact path, size | timeout | Diretório permitido. | Lock da tab e download dir. |
| `upload_files` | P1 | Enviar arquivos para input. | `client_id`, `tab_id`, `element_id`, paths | count | path denied, stale | Allowlist de paths. | Lock mutante da tab. |
| `console_list` | P2 | Inspecionar logs de console se Pydoll permitir. | `client_id`, `tab_id`, filters | eventos | unsupported | Redaction. | Lock de observação. |
| `network_list` | P2 | Inspecionar eventos de rede se Pydoll permitir. | `client_id`, `tab_id`, filters | requests resumidos | network disabled | Redigir headers sensíveis. | Lock de observação. |

## Métodos que não devem ser expostos

- `execute_cdp_cmd` livre: permitiria qualquer comando CDP, incluindo extração de credenciais, manipulação de navegador, evasões e estados não auditáveis.
- Execução de comandos do sistema operacional: não pertence a browser automation e amplia risco para a máquina do usuário.
- Leitura arbitrária do filesystem: poderia exfiltrar arquivos locais. Exceções exigem allowlist explícita.
- Escrita arbitrária no filesystem: downloads, screenshots e artifacts devem ficar em diretórios permitidos.
- Exfiltração ampla de cookies, tokens, headers Authorization, localStorage e sessionStorage: deve ser redigida por padrão, auditada e delimitada por origem.
- Automação furtiva para bypass de segurança, CAPTCHA, fraude ou abuso: fora de escopo.
- Downloads automáticos sem política: devem exigir diretório permitido e registrar artifact.
- Upload de arquivos fora de allowlist: deve falhar com erro estruturado.

## Política para JavaScript

- `js_evaluate_readonly` é a tool recomendada para inspeção.
- `js_evaluate` permite efeitos colaterais e deve ser documentada como sensível.
- Ambas exigem `tab_id` explícito, timeout obrigatório, limite de código e limite de resultado.
- Defaults propostos: timeout 5s, máximo 15s, código até 20.000 caracteres, resultado até 256 KiB.
- Bloquear ou alertar padrões perigosos: loops infinitos óbvios, `fetch` para domínio externo, manipulação de cookies ou storage, submissão de formulários e alteração de `location`.
- Não registrar código completo nem resultado completo por padrão.
- Registrar auditoria resumida: `client_id`, `tab_id`, duração, sucesso ou falha, tamanho de resultado e hash curto do script.

## Resiliência

- Health do servidor: event loop, registry, config, auth, versão e limites.
- Health do browser: processo vivo, CDP responsivo, versão disponível.
- Health de tab: `current_url`, título ou script curto com timeout.
- Aba travada: diagnosticar, tentar reload uma vez se responder minimamente, marcar `unhealthy` se falhar.
- Recriação destrutiva: apenas por `tab_recover` ou `tab_recreate` explícito com `force=true`.
- Operação interrompida: registrar estado e retornar erro estruturado com recovery hint.

## Observabilidade

- Logging estruturado em JSON quando possível.
- Campos mínimos: `request_id`, `client_id`, `session_id`, `browser_id`, `tab_id`, `tool`, `operation`, `duration_ms`, `status`, `error_code`.
- Redigir tokens, cookies, Authorization headers, storage values, senhas e campos de formulário sensíveis.
- Métricas simples: contagem de tools, falhas por erro, timeouts, tabs unhealthy, recoveries.

## Convenções de progresso

Cada agente deve criar ou atualizar um arquivo curto em `progress/` ao concluir um bloco de trabalho.

Nome:

```text
progress/YYYY-MM-DD_AGENT_PLAN_XX.md
```

Conteúdo:

- plano atual;
- tarefas feitas;
- arquivos alterados;
- testes executados;
- bloqueios;
- próximo passo recomendado.

## Perguntas pendentes

Não há decisões bloqueantes pendentes para iniciar `PLAN_01`. Qualquer dúvida nova deve ser registrada em `QUESTIONS.md` como `PENDENTE` e mencionada no progresso do agente.

## Critérios globais de sucesso

- O projeto instala via pip em Windows, macOS e Unix com ruído mínimo.
- O servidor atende clientes Codex, OpenCode e Claude Code por HTTP local.
- Múltiplos `client_id` operam simultaneamente sem ver recursos uns dos outros.
- Ações comuns parecem síncronas para o cliente MCP, sem bloquear o event loop global.
- Abas independentes podem executar operações em paralelo.
- Elementos observados podem ser reutilizados por `element_id` até invalidação clara.
- Iframes, OOPIFs e shadow roots são suportados em tools robustas.
- Logs e outputs não vazam segredos por padrão.
- Testes locais cobrem navegação, iframes, shadow DOM, timeout, recovery e contrato MCP.
