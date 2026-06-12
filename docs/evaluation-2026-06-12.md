# Avaliação técnica da implementação atual

Data: 2026-06-12.

## Veredito

A implementação atual é um bom esqueleto inicial, mas ainda não está pronta para validação humana com browser real. A suíte `pytest` passa com 87 testes, porém os testes atuais validam principalmente config, modelos, registry, imports e contratos superficiais. A revisão estática e a comparação com a Pydoll local mostram problemas bloqueantes que precisam entrar no P1 antes de qualquer expansão de features.

## Validações executadas

```powershell
Remove-Item Env:PYDOLL_MCP_ALLOW_NO_AUTH -ErrorAction SilentlyContinue
Remove-Item Env:PYDOLL_MCP_AUTH_TOKEN -ErrorAction SilentlyContinue
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
```

Resultado: `87 passed in 1.08s`.

```powershell
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
```

Resultado: 20 violações.

```powershell
C:\Users\Yuri\anaconda3\python.exe -m mypy src
```

Resultado: 16 erros.

## Pontos positivos

- Estrutura de pacote Python foi criada com separação clara entre server, config, browser, DOM, tools, recovery e security.
- `pyproject.toml` existe e aponta para distribuição via pip.
- A autenticação por token foi modelada como padrão obrigatório.
- O runtime dir padrão fica fora do repositório.
- A documentação local da Pydoll foi vendorizada.
- Há fixtures HTML locais para Unicode, forms, iframes, shadow DOM, delay e many-nodes.
- Há um modelo de erro estruturado.
- O registry isola recursos por `client_id` em memória.
- A lista de tools cobre a maior parte da API planejada.
- O progresso foi registrado em `progress/2026-06-12_AGENT_PLAN_01_12.md`.

## Achados bloqueantes

### 1. O servidor HTTP MCP não deve iniciar como está

`src/pydoll_mcp_server/server.py` usa `mcp.http_app()` na linha 518, mas a versão instalada do SDK MCP expõe `streamable_http_app()` e `sse_app()`, não `http_app()`.

Impacto: `create_app()` tende a falhar em runtime antes de servir `/mcp`.

Correção P1: trocar para `mcp.streamable_http_app()` em `/mcp`, montar `mcp.sse_app()` em `/sse`, e criar teste que chama `create_app()` com token configurado.

### 2. `browser_launch` usa métodos inexistentes da Pydoll

`src/pydoll_mcp_server/tools/browser.py` chama `options.set_user_data_dir(...)` na linha 50 e `options.set_headless(True)` na linha 52. Na Pydoll local, `ChromiumOptions` usa `add_argument('--user-data-dir=...')` e propriedade `headless`.

Impacto: `browser_launch` falha antes de abrir o navegador.

Correção P1: ajustar integração com `ChromiumOptions` conforme `C:\Users\Yuri\Documents\Git\pydoll\pydoll\browser\options.py`.

### 3. Métodos async da Pydoll são usados como atributos

`Tab.current_url` e `Tab.title` são `async def` na Pydoll local. O código usa `pydoll_tab.current_url` e `pydoll_tab.title` sem chamada e sem `await` em `browser.py` e `page.py`.

Impacto: URLs e títulos podem virar objetos de método ou coroutine, quebrando serialização, registry e status.

Correção P1: criar helpers internos `await_tab_url(tab)` e `await_tab_title(tab)` e substituir todos os acessos.

### 4. `get_attribute` é chamado com assinatura errada

Correção posterior: esta avaliação original errou sobre `WebElement.text`. Na Pydoll local, `WebElement.text` é async property, então `await element.text` está correto. O problema real nesta categoria era `get_attribute(name)`, que é síncrono e não deve receber `await`.

Impacto: leitura de atributos pode falhar em runtime com browser real se for aguardada indevidamente.

Correção P1: manter `await element.text`, trocar `await element.get_attribute(name)` por `element.get_attribute(name)`, e criar tests com doubles que reproduzam async properties da Pydoll.

### 5. `page_get_tree` gera `element_id` sem objeto Pydoll

`src/pydoll_mcp_server/dom/tree.py` gera IDs no JavaScript da página e cria `ElementCacheEntry` sem `_pydoll_element`. Em seguida, `element_click` só resolve elementos com `_pydoll_element`.

Impacto: elementos retornados por `page_get_tree` não são clicáveis, contrariando o objetivo principal de agentes observarem e agirem por `element_id`.

Correção P1: decidir e implementar um modelo consistente:

- opção A: `page_get_tree` retorna locator ids com hints e `element_click` reaquece por selector antes de agir;
- opção B: `page_get_tree` usa Pydoll para materializar objetos nos nós interativos;
- recomendação: opção A para escala, com reaquisição controlada e erro claro.

### 6. Deep traversal ainda não atravessa iframes recursivamente

`src/pydoll_mcp_server/dom/deep_traversal.py` detecta iframes via JS, mas só retorna metadados. Não entra nos iframes, não constrói árvore recursiva e usa `find_shadow_roots(deep=False)`.

Impacto: a promessa central de `page_get_tree_deep` ainda não foi cumprida.

Correção P1: implementar traversal real por iframe como `WebElement`, nested iframes, `find_shadow_roots(deep=True)` quando solicitado e resultados parciais por subárvore.

### 7. Locks por recurso existem, mas quase não são usados

O `LockManager` existe, mas as tools mutantes não usam locks de tab de forma consistente.

Impacto: duas ações concorrentes na mesma aba podem gerar estado inconsistente.

Correção P1: envolver ações mutantes por tab e browser em `async with lock`.

### 8. Perfil persistente default não é travado

`browser_launch` trava somente perfil nomeado. O perfil default persistente por `client_id` pode ser usado por múltiplos browsers simultaneamente.

Impacto: risco de lock real do Chrome, corrupção de perfil ou falha de start.

Correção P1: lock exclusivo para qualquer perfil persistente, incluindo default.

### 9. Path allowlist usa comparação por prefixo textual

`PathAllowlist.is_allowed` usa `str(resolved).startswith(str(allowed))`. Um caminho como `C:\allowed-other` pode passar quando `C:\allowed` está permitido.

Impacto: bypass de allowlist de filesystem.

Correção P1: usar `Path.is_relative_to` em Python 3.10+ ou `relative_to` com exceção.

### 10. P1/P2 foram marcados como completos sem validação real

O progresso declara tudo completo, mas não há teste de browser real, teste de `create_app`, teste de mount `/mcp`, teste `/sse`, teste de launch com Pydoll, nem teste de click em elemento vindo de `page_get_tree`.

Impacto: o estado real é scaffold funcional parcial, não implementação completa.

Correção P1: redefinir baseline como "P0 scaffold implementado, P1 pendente".

## Qualidade estática

- `ruff check .` falha com linhas longas e problemas pequenos em tests.
- `mypy src` falha com 16 erros, incluindo dois problemas funcionais relevantes: FastMCP app e `ChromiumOptions`.

## Recomendação

Não iniciar P2 antes de concluir P1. O P1 deve ser tratado como estabilização obrigatória para transformar o scaffold em alpha real com browser, transporte MCP e fluxos agent-friendly básicos.
