# FIX_03: `element_id` acionável a partir de `page_get_tree`

## Problema

`page_get_tree` gera `element_id` no JavaScript da página e armazena cache sem `_pydoll_element`. As tools de interação resolvem apenas elementos com `_pydoll_element`. Portanto, um agente pode observar um botão na árvore, mas não consegue clicar nele pelo `element_id` retornado.

## Arquivos envolvidos

- `src/pydoll_mcp_server/dom/tree.py`
- `src/pydoll_mcp_server/dom/element_cache.py`
- `src/pydoll_mcp_server/tools/elements.py`
- `tests/unit/test_element_cache.py`
- `tests/fixtures/pages/form.html`

## Objetivo

Permitir o fluxo agent-friendly central:

1. `page_get_tree`
2. escolher `element_id`
3. `element_click` ou `element_fill`
4. observar efeito na página

## Decisão de design

Use reaquisição por locator hints para `page_get_tree`. Não tente materializar todos os objetos Pydoll durante a árvore compacta, porque isso pode ficar caro. A árvore deve armazenar hints suficientes para resolver o elemento quando a interação acontecer.

## Tarefas detalhadas

1. Estender `ElementCacheEntry`:
   - `is_locator_only: bool`;
   - `selector_hint`;
   - `xpath_hint`;
   - `role_hint`;
   - `text_summary`;
   - `attributes_summary`;
   - `frame_path`;
   - `shadow_path`.
2. Melhorar o JS de tree para retornar:
   - id;
   - data-testid;
   - name;
   - role;
   - aria-label;
   - texto curto;
   - CSS path curto;
   - XPath curto se viável;
   - bounds;
   - interactive.
3. Criar resolver comum:

```text
resolve_element_for_action(client_id, tab_id, element_id)
```

4. O resolver deve tentar:
   - `_pydoll_element`, se existir e estiver válido;
   - `selector_hint` com `tab.query`;
   - `xpath_hint` com `tab.query`;
   - fallback por texto apenas se o hint for específico e seguro.
5. O resolver deve atualizar o cache com o objeto Pydoll quando reaquisição funcionar.
6. `element_click`, `element_fill`, `element_type`, `element_get_text` e `element_get_attribute` devem usar esse resolver.
7. Quando a reaquisição falhar, retornar `STALE_ELEMENT` com:
   - `element_id`;
   - selector hints usados;
   - `recovery_hint` pedindo nova observação.
8. Criar teste com fixture `form.html`:
   - construir árvore;
   - encontrar botão por texto ou atributo;
   - clicar via `element_id`;
   - validar mudança no DOM.
9. Criar teste para input Unicode:
   - `page_get_tree`;
   - achar input;
   - `element_fill`;
   - validar valor.
10. Invalidar elementos em navegação e reload, preservando erro claro.

## Critérios de aceite

- `element_id` retornado por `page_get_tree` pode ser usado em `element_click`.
- `element_id` retornado por `page_get_tree` pode ser usado em `element_fill`.
- Elemento stale retorna erro estruturado e não falha com exceção bruta.
- O cache não cresce sem limite.

## Como testar

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest tests\unit\test_element_cache.py -q
C:\Users\Yuri\anaconda3\python.exe -m pytest tests\integration -q
```

Quando houver browser smoke:

```powershell
$env:PYDOLL_MCP_AUTH_TOKEN = "test-token"
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
Remove-Item Env:PYDOLL_MCP_AUTH_TOKEN -ErrorAction SilentlyContinue
```

## Erros a evitar

- Não gerar IDs aleatórios no JS sem estratégia de reaquisição.
- Não afirmar que `page_get_tree` suporta interação se `element_click` não aceitar seus IDs.
- Não esconder stale element com retry infinito.

## Definição de pronto

Este plano está pronto quando o fluxo observe e act funciona em teste real ou smoke com browser.
