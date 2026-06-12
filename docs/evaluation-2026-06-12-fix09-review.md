# Reavaliação após FIX_09

Data: 2026-06-12  
Escopo: revisão do estado após o desenvolvedor informar conclusão de `FIX_09_RUNTIME_FUNCTIONAL_GAPS.md`.

## Resultado dos gates

Comandos executados:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
```

Resultados:

- `pytest -q`: 109 passed.
- `ruff check .`: All checks passed.
- `mypy src`: Success, 32 source files.
- `pytest -m browser_smoke -q`: 4 passed, 105 deselected.

## Pontos corrigidos corretamente

- `return_by_value=True` foi aplicado nos pontos principais que esperam retorno serializável de `execute_script`.
- `extract_script_value()` resolve o formato correto de resposta CDP/Pydoll.
- `page_get_tree` agora tem smoke real e retorna nós em `simple.html`.
- `js_evaluate_readonly` foi validado manualmente via tool e retornou objeto como string JSON serializável.
- `page_screenshot` valida `path` com `_validate_artifact_path`.
- `upload_files` passou a usar `PathAllowlist` em vez de `startswith`.
- `:has-text()` foi removido dos selector hints.
- Nós da árvore incluem `actionable`, `resolution_confidence`, `selector_hint` e `xpath_hint`.

## Findings

### 1. Locks por recurso continuam não aplicados

Severidade: P0  
Arquivos:

- `src/pydoll_mcp_server/browser/locks.py`
- `src/pydoll_mcp_server/tools/page.py`
- `src/pydoll_mcp_server/tools/elements.py`
- `src/pydoll_mcp_server/tools/tabs.py`
- `src/pydoll_mcp_server/tools/storage.py`

O próprio progresso do desenvolvedor registra:

```text
tab_operation_lock esta definido mas nao aplicado nas tools de navegacao/mutacao (P2)
```

Isso não é P2. Era critério de aceite do `FIX_09` porque o requisito original do projeto exige que ações mutantes na mesma aba não concorram entre si.

Exemplos ainda sem lock:

- `page_goto`
- `page_reload`
- `page_back`
- `page_forward`
- `element_click`
- `element_type`
- `element_fill`
- `tab_close`
- `tab_recover`
- `storage_set`
- `cookies_set` quando usa `tab_id`

Impacto:

- dois agentes podem clicar, navegar ou preencher a mesma aba simultaneamente;
- o estado do DOM e do cache de elementos pode ficar incoerente;
- timeouts e recovery ficam menos confiáveis.

Correção esperada:

- usar `async with tab_operation_lock(tab_id)` ao redor da seção mutante de cada operação por aba;
- usar `browser_operation_lock(browser_id)` para mutações de browser inteiro;
- criar testes de concorrência que provem serialização na mesma aba e independência em abas diferentes.

### 2. `element_screenshot` ainda permite escrita arbitrária

Severidade: P0  
Arquivo: `src/pydoll_mcp_server/tools/elements.py`.

`element_screenshot` ainda faz:

```python
await element.take_screenshot(path=path, as_base64=False)
```

sem validar `path`.

O progresso do desenvolvedor também registra:

```text
element_screenshot ainda nao tem validacao de path (P2)
```

Isso não é P2. É uma violação direta da política de filesystem do projeto.

Correção esperada:

- reutilizar a mesma validação de path de `page_screenshot`;
- mover `_validate_artifact_path` para helper comum, por exemplo `security/paths.py` ou `tools/artifacts.py`;
- se `path` for relativo, resolver em `config.artifacts_dir`;
- se `path` for absoluto, aceitar somente dentro de diretórios permitidos;
- retornar `PERMISSION_DENIED` para path proibido;
- adicionar teste unitário cobrindo path proibido em `element_screenshot`.

### 3. Teste de `js_evaluate` não cobre a tool, mas a tool funciona manualmente

Severidade: P2  
Arquivo: `tests/integration/test_browser_smoke.py`.

O teste `test_js_evaluate_returns_object` chama `tab.execute_script` direto e valida `extract_script_value`, mas não chama `js_evaluate_readonly`.

Validação manual executada nesta revisão:

```python
await js_evaluate_readonly(client_id, tab_id, 'return {answer: 42, text: "ok"};')
```

Resultado:

```python
{'success': True, 'value': '{"answer": 42, "text": "ok"}', ...}
```

Portanto não há bug funcional aparente, mas o teste deveria cobrir a tool real para evitar regressão.

## Decisão

O `FIX_09` corrigiu o bloqueador de `page_get_tree`, mas não está completo porque deixou dois critérios de aceite como pendência:

- locks em operações mutantes;
- validação de path em `element_screenshot`.

Criar e executar `FIX_10` antes de avançar para P1/P2.
