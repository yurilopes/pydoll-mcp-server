# Reavaliação após FIX_08

Data: 2026-06-12  
Escopo: revisão do estado após o desenvolvedor informar conclusão de `FIX_08_SECOND_PASS_VALIDATION.md`.

## Resultado dos gates

Comandos executados:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
```

Resultados:

- `pytest -q`: 106 passed.
- `ruff check .`: All checks passed.
- `mypy src`: Success, 31 source files.
- `pytest -m browser_smoke -q`: 1 passed, 105 deselected.

## Pontos corrigidos corretamente

- O desenvolvedor estava certo sobre as async properties da Pydoll:
  - `await tab.current_url`
  - `await tab.title`
  - `await element.text`
- `WebElement.get_shadow_root` foi corrigido para `await el.get_shadow_root(timeout=2)`.
- `/mcp` e `/sse` agora são mounts explícitos em `create_app()`.
- O teste que aceitava `RuntimeError` como sucesso foi removido.
- Existe um smoke real com navegador headless, navegação local e clique.
- `ruff`, `mypy` e `pytest` estão verdes.

## Findings

### 1. `page_get_tree` retorna árvore vazia em runtime

Severidade: P0  
Arquivos: `src/pydoll_mcp_server/dom/tree.py`, `src/pydoll_mcp_server/tools/javascript.py`, `src/pydoll_mcp_server/tools/storage.py`, `src/pydoll_mcp_server/browser/cdp_helpers.py`, `src/pydoll_mcp_server/recovery/health.py`.

A Pydoll só retorna objetos JavaScript completos quando `execute_script(..., return_by_value=True)` é usado. Sem isso, objetos retornam `objectId`, não `value`.

Evidência prática executada contra a Pydoll local:

```text
await tab.execute_script('return {a: 1, b: "x"}')
```

retornou:

```text
{'result': {'result': {'type': 'object', 'className': 'Object', 'description': 'Object', 'objectId': '...'}}}
```

E `build_page_tree()` contra `tests/fixtures/pages/simple.html` retornou:

```python
{'success': True, 'root_id': None, 'nodes': [], 'count': 0, 'truncated': False}
```

Isso quebra uma tool central para agentes. O smoke atual não cobre `page_get_tree`.

Correção esperada:

- Usar `return_by_value=True` em todos os `execute_script` que esperam objeto ou array serializável.
- Pelo menos em:
  - `dom/tree.py` para `page_get_tree`;
  - `tools/javascript.py` para `js_evaluate` e `js_evaluate_readonly`;
  - `tools/storage.py` para `storage_get`;
  - `browser/cdp_helpers.py` para `viewport_set`;
  - `recovery/health.py` para `check_tab_health`.
- Criar teste com browser real ou fake fiel que falhe antes da correção e prove que `page_get_tree` retorna nós em `simple.html`.

### 2. Locks por recurso existem, mas não são usados nas operações mutantes

Severidade: P0  
Arquivos: `src/pydoll_mcp_server/browser/locks.py`, `src/pydoll_mcp_server/tools/page.py`, `src/pydoll_mcp_server/tools/elements.py`, `src/pydoll_mcp_server/tools/tabs.py`, `src/pydoll_mcp_server/tools/storage.py`.

O módulo `browser/locks.py` define `tab_operation_lock()` e `browser_operation_lock()`, mas buscas no código mostram que essas funções não são usadas fora do próprio módulo.

Isso mantém o risco original: dois agentes ou duas chamadas simultâneas podem disparar clique, navegação, reload ou fill na mesma aba ao mesmo tempo.

Correção esperada:

- Aplicar `tab_operation_lock(tab_id)` em operações mutantes por aba:
  - `page_goto`, `page_reload`, `page_back`, `page_forward`;
  - `element_click`, `element_type`, `element_fill`;
  - `tab_close`, `tab_recover`;
  - `storage_set`, `cookies_set` quando operarem por `tab_id`.
- Aplicar lock de browser quando a operação afetar browser inteiro.
- Criar teste de concorrência com duas operações mutantes na mesma aba e verificar serialização.
- Manter concorrência entre abas diferentes.

### 3. `page_screenshot` e `element_screenshot` permitem escrita arbitrária

Severidade: P0  
Arquivos: `src/pydoll_mcp_server/dom/tree.py`, `src/pydoll_mcp_server/tools/elements.py`.

As tools aceitam `path` e repassam diretamente para Pydoll:

- `page_screenshot(..., path=path)`;
- `element_screenshot(..., path=path)`.

Isso viola a política do projeto: tools de browser automation não devem escrever arbitrariamente no filesystem. Screenshot deve gravar somente em diretório permitido, preferencialmente `config.artifacts_dir`, com nome sanitizado ou caminho validado por allowlist.

Correção esperada:

- Remover escrita arbitrária ou validar com `PathAllowlist`.
- Se `path` for relativo, resolver dentro de `artifacts_dir`.
- Se `path` for absoluto, aceitar somente quando estiver em diretórios permitidos.
- Adicionar testes contra bypass por prefixo e parent traversal.

### 4. Upload usa validação por prefixo de string

Severidade: P1  
Arquivo: `src/pydoll_mcp_server/tools/files.py`.

`upload_files` valida caminhos com:

```python
path_str.startswith(str(Path(d).resolve()))
```

Isso é inferior ao `PathAllowlist` já corrigido e reabre o bypass de prefixo, por exemplo um diretório irmão cujo nome começa igual ao permitido.

Correção esperada:

- Reusar `PathAllowlist`.
- Validar cada path com `Path.resolve(strict=False)` e `relative_to`.
- Conferir existência e tipo de arquivo antes de upload.
- Criar teste unitário específico para `upload_files`, não apenas para `PathAllowlist`.

### 5. IDs de elementos de `page_get_tree` ainda não são confiáveis o suficiente

Severidade: P1  
Arquivos: `src/pydoll_mcp_server/dom/tree.py`, `src/pydoll_mcp_server/tools/elements.py`.

`page_get_tree` gera IDs no JavaScript e salva apenas hints. Quando a ação posterior usa `element_id`, `_resolve_element()` tenta reencontrar por CSS ou XPath.

Isso melhora a versão anterior, mas ainda é frágil:

- elementos sem `id`, `data-testid`, `name` ou atributo estável podem virar selector genérico como `div`;
- `tag:has-text(...)` é pseudo seletor de Playwright, não está documentado como seletor Pydoll;
- a reaquisição pode apontar para o primeiro elemento parecido, não para o elemento observado.

Correção esperada:

- Para P0, garantir que IDs vindos de `element_find` continuam fortes.
- Para `page_get_tree`, retornar explicitamente `actionable: true/false` por nó.
- Só cachear como acionável quando houver selector ou XPath confiável.
- Para P1, implementar mecanismo mais robusto de reaquisição por path estrutural, atributos e verificação de texto/bounds.
- Criar teste real: observar árvore, escolher botão sem ID estável, clicar pelo `element_id` e verificar que o botão correto foi acionado.

### 6. O smoke real ainda é estreito

Severidade: P2  
Arquivo: `tests/integration/test_browser_smoke.py`.

O smoke real valida launch, goto direto da Pydoll, query e clique. Ele não passa pelas tools MCP nem pelas wrappers centrais como `page_goto`, `page_get_tree`, `js_evaluate`, locks e screenshot.

Correção esperada:

- Adicionar smoke real de wrappers internos:
  - registrar browser e tab no registry;
  - chamar `page_get_tree`;
  - chamar `js_evaluate_readonly` retornando objeto;
  - chamar `element_find` e `element_click`;
  - validar screenshot base64 sem path.
- Depois, adicionar teste de contrato MCP real com cliente MCP quando viável.

## Decisão

O estado está melhor que a rodada anterior, mas ainda não considero pronto para avançar como base P1/P2 sem `FIX_09`.

O bloqueador principal é `page_get_tree` retornar árvore vazia em runtime. Essa tool é central para agentes e precisa funcionar antes de novos planos de expansão.
