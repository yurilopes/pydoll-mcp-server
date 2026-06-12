# Pydoll MCP Server

Servidor MCP de automação de navegador baseado na biblioteca [Pydoll](https://github.com/autoscrape-labs/pydoll).

O objetivo é oferecer uma alternativa local ao Playwright MCP Server, com API própria orientada a agentes e implementação sobre Pydoll. O projeto não copia a API do Playwright. Ele busca entregar uma camada previsível para agentes: observar página, escolher elementos, agir por `element_id`, navegar, capturar screenshots, executar JavaScript com limites e lidar com iframes e shadow DOM.

## Status

Alpha local em estabilização.

Neste ciclo, o transporte principal é HTTP local em `127.0.0.1`. O wrapper `stdio` está planejado para P2. O servidor já expõe endpoints MCP HTTP e exige bearer token por padrão.

## Requisitos

- Python `>=3.10`.
- Chrome ou Chromium instalado.
- Pydoll `>=2.23.0`.
- Em desenvolvimento local nesta máquina, use:

```powershell
C:\Users\Yuri\anaconda3\python.exe
```

## Instalação local

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pip install -e ".[dev]"
```

Quando distribuído por release, o pacote será instalável via `pip`.

## Execução local

Defina um token antes de iniciar:

```powershell
$env:PYDOLL_MCP_AUTH_TOKEN = "troque-este-token"
```

Inicie o servidor:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pydoll_mcp_server.cli --host 127.0.0.1 --port 8765
```

Endpoints:

- `GET http://127.0.0.1:8765/health`: health público, sem token.
- `POST http://127.0.0.1:8765/mcp/`: Streamable HTTP MCP, com bearer token.
- `GET http://127.0.0.1:8765/sse/`: SSE MCP, com bearer token quando suportado pelo SDK instalado.

Clientes MCP devem enviar:

```text
Authorization: Bearer <PYDOLL_MCP_AUTH_TOKEN>
```

`PYDOLL_MCP_ALLOW_NO_AUTH=true` só deve ser usado em desenvolvimento isolado.

## Ferramentas MCP

Health e diagnóstico:

- `health_check`
- `server_status`

Lifecycle:

- `browser_launch`
- `browser_list`
- `browser_close`
- `tab_list`
- `tab_activate`
- `tab_close`
- `tab_recover`

Navegação:

- `page_goto`
- `page_reload`
- `page_back`
- `page_forward`
- `page_wait`

Observação:

- `page_get_text`
- `page_get_tree`
- `page_get_tree_deep`
- `page_screenshot`

Elementos:

- `element_find`
- `element_find_deep`
- `element_click`
- `element_type`
- `element_fill`
- `element_get_text`
- `element_get_attribute`
- `element_screenshot`

JavaScript e helpers avançados:

- `js_evaluate_readonly`
- `js_evaluate`
- `user_agent_set`
- `viewport_set`
- `cookies_get`
- `cookies_set`
- `storage_get`
- `storage_set`
- `download_expect`
- `upload_files`

## Modelo agent-friendly

`page_get_tree` retorna uma árvore compacta e limitada por padrão. Os nós interativos recebem `element_id`, `selector_hint`, `xpath_hint`, `actionable` e `resolution_confidence`. Um agente pode observar a árvore e chamar `element_click` ou `element_fill` diretamente com o `element_id`, sem chamar `element_find` antes.

`page_get_tree_deep` é a opção recomendada quando a página usa iframes ou shadow DOM. Ela é mais cara, tem timeout próprio e retorna:

- `frame_path`
- `shadow_path`
- `partial`
- `errors`
- metadados de visibilidade e interação quando disponíveis

O alpha cobre iframe simples, nested iframe same-origin e shadow DOM aberto. Closed shadow root e casos cross-origin complexos ainda exigem validação adicional.

## Segurança

Padrões importantes:

- Bearer token é obrigatório por padrão.
- O bind padrão deve permanecer em `127.0.0.1`.
- `execute_cdp_cmd` livre não é exposto.
- Comandos do sistema operacional não são expostos.
- Leitura ou escrita arbitrária de filesystem não é exposta.
- Screenshots, downloads e uploads usam diretórios controlados ou allowlist.
- Cookies e storage são redigidos por padrão em leitura.
- Atributos sensíveis, como tokens, senhas e cookies, são redigidos.
- Logs devem redigir bearer tokens, cookies, authorization headers e campos sensíveis.

`js_evaluate` é tool sensível:

- exige `tab_id` explícito;
- usa timeout curto por padrão;
- limita tamanho de código e resultado;
- registra auditoria resumida com hash, duração e tamanho;
- não deve registrar código completo nem resultado completo em logs;
- alerta ou bloqueia padrões perigosos, conforme o modo;
- pode ser desabilitada futuramente por configuração de modo seguro.

`js_evaluate_readonly` é preferível para inspeção, mas também deve ser tratada como sensível.

## Diretórios runtime

Dados runtime ficam fora do repositório por padrão:

- Windows: `%LOCALAPPDATA%\pydoll-mcp-server`
- macOS: `~/Library/Application Support/pydoll-mcp-server`
- Linux: `~/.local/share/pydoll-mcp-server`

Subdiretórios esperados:

- `profiles/`
- `tmp/`
- `downloads/`
- `artifacts/`
- `logs/`

Use `PYDOLL_MCP_RUNTIME_DIR` para sobrescrever em testes ou ambientes isolados.

## Documentação local da Pydoll

A documentação vendorizada da Pydoll fica em:

```text
references/pydoll-docs/
```

Consulte também o repositório local da Pydoll quando estiver trabalhando nesta máquina:

```text
C:\Users\Yuri\Documents\Git\pydoll
```

Não misture documentação vendorizada com código do servidor MCP.

## Testes

Gates principais:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
```

Testes úteis por área:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest tests\contract -q
C:\Users\Yuri\anaconda3\python.exe -m pytest tests\unit\test_concurrency.py -q
C:\Users\Yuri\anaconda3\python.exe -m pytest tests\unit\test_security.py tests\unit\test_files_security.py -q
```

`browser_smoke` abre Chrome/Chromium headless e valida fluxos reais com fixtures locais.

## Limitações conhecidas do alpha

- Transporte `stdio` ainda é P2.
- Inspeção completa de network e console ainda é P2.
- Closed shadow root e OOPIFs complexos ainda precisam de validação dedicada.
- Deep traversal é mais caro que `page_get_tree` e deve ser usado de forma explícita.
- Downloads dependem do fluxo `expect_download` da Pydoll e devem permanecer no runtime dir controlado.
- Uploads só devem usar caminhos permitidos pela allowlist.

## Planos e progresso

- Visão geral: `PLAN.md`
- P1 atual: `plans/PLAN_P1.md`
- P2: `plans/PLAN_P2.md`, quando existir ou for atualizado
- Progresso dos agentes: `progress/`

Agentes devem registrar progresso curto em:

```text
progress/YYYY-MM-DD_AGENT_PLAN_XX.md
```

## Licença

MIT
