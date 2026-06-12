# FIX_04: Traversal real de iframes, nested iframes e shadow DOM

## Problema

`page_get_tree_deep` apenas detecta iframes por JavaScript e lista metadados. Ele não entra nos iframes, não percorre nested iframes e chama `find_shadow_roots(deep=False)`, deixando fora OOPIFs e shadow roots dentro de iframes.

## Arquivos envolvidos

- `src/pydoll_mcp_server/dom/deep_traversal.py`
- `src/pydoll_mcp_server/dom/tree.py`
- `src/pydoll_mcp_server/dom/element_cache.py`
- `tests/fixtures/pages/iframe-parent.html`
- `tests/fixtures/pages/iframe-content.html`
- `tests/fixtures/pages/nested-iframe.html`
- `tests/fixtures/pages/shadow-dom.html`

## Objetivo

Implementar traversal profundo real, com resultados parciais seguros, para permitir que agentes encontrem e interajam com elementos em:

- DOM principal;
- iframe simples;
- nested iframe;
- shadow DOM aberto;
- shadow roots suportados pela Pydoll;
- combinação iframe mais shadow root quando viável.

## Tarefas detalhadas

1. Criar modelo de resultado interno:
   - `DeepNode`;
   - `FramePath`;
   - `ShadowPath`;
   - `PartialError`.
2. Implementar função recursiva:

```text
traverse_scope(scope, frame_path, shadow_path, depth, budget)
```

3. No DOM principal:
   - coletar árvore compacta;
   - identificar iframes;
   - identificar candidatos a shadow host.
4. Para iframe:
   - localizar iframe como `WebElement`;
   - usar o próprio iframe como escopo Pydoll;
   - buscar elementos dentro dele;
   - recursar se houver iframe interno;
   - anexar `frame_path`.
5. Para shadow root:
   - usar `get_shadow_root` ou `find_shadow_roots`;
   - dentro de shadow root, usar CSS selector;
   - anexar `shadow_path`;
   - registrar limitação de XPath.
6. Quando `include_iframes=true` e `include_shadow=true`, usar `find_shadow_roots(deep=True)` quando a estratégia global exigir descoberta cross-origin.
7. Implementar budgets:
   - `max_depth`;
   - `max_nodes`;
   - `timeout`;
   - `max_frames`;
   - `max_shadow_roots`.
8. Em qualquer falha de subárvore:
   - não falhar a tool inteira;
   - retornar `partial=true`;
   - adicionar item em `errors[]` com path e mensagem redigida.
9. Implementar `element_find_deep` usando o mesmo traversal ou resolvers por escopo:
   - main DOM;
   - frames recursivos;
   - shadow roots.
10. Criar tests:
   - encontra texto em iframe simples;
   - encontra botão em nested iframe;
   - encontra elemento em shadow DOM aberto;
   - retorna partial quando um frame falha;
   - respeita `max_nodes` e `timeout`.

## Critérios de aceite

- `page_get_tree_deep` retorna pelo menos um elemento de iframe simples.
- `element_find_deep` encontra elemento em nested iframe.
- Shadow DOM aberto é coberto por teste.
- `partial=true` funciona quando uma subárvore falha.
- O output inclui `frame_path` e `shadow_path` quando aplicável.

## Como testar

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest tests\integration -q
C:\Users\Yuri\anaconda3\python.exe -m pytest -k "deep or iframe or shadow" -q
```

## Erros a evitar

- Não confundir detectar iframe com entrar nele.
- Não usar apenas `document.querySelectorAll` do DOM principal.
- Não prometer closed shadow root sem teste ou fonte local.
- Não deixar traversal profundo sem timeout.

## Definição de pronto

Este plano está pronto quando iframes simples e nested iframes são realmente percorridos em teste, não apenas listados.
