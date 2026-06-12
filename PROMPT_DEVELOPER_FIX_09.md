# Prompt para o LLM desenvolvedor: FIX 09

Você está trabalhando no repositório:

```text
C:\Users\Yuri\Documents\Git\pydoll-mcp-server
```

Use Python:

```text
C:\Users\Yuri\anaconda3\python.exe
```

Leia antes de editar:

1. `AGENTS.md`
2. `docs/evaluation-2026-06-12-fix08-review.md`
3. `plans/remediation/FIX_09_RUNTIME_FUNCTIONAL_GAPS.md`
4. O progresso mais recente em `progress/`

## O que você acertou

Você acertou ao questionar a orientação anterior sobre `current_url`, `title` e `text`. Na Pydoll local:

```python
await tab.current_url
await tab.title
await element.text
```

está correto. Não coloque parênteses nessas três APIs.

Você também corrigiu corretamente:

- `get_shadow_root` com `await el.get_shadow_root(timeout=2)`;
- mounts explícitos em `/mcp` e `/sse`;
- teste fraco que aceitava `RuntimeError`;
- `ruff`, `mypy`, `pytest` e browser smoke.

## O que ainda está errado

Os gates verdes escondem bugs de runtime. O problema mais importante é este:

```python
await tab.execute_script("return {a: 1}")
```

sem `return_by_value=True` não retorna o objeto em `result.value`. A Pydoll retorna um `objectId`. O código atual espera `value`, então `page_get_tree` fica vazio e `js_evaluate` pode retornar `null` para objetos.

Foi confirmado em runtime que:

```python
await build_page_tree("eval", tab_id)
```

em `tests/fixtures/pages/simple.html` retornou:

```python
{'success': True, 'root_id': None, 'nodes': [], 'count': 0, 'truncated': False}
```

Isso é um bloqueador. `page_get_tree` é uma tool central para agentes.

## Como se corrigir

Execute `plans/remediation/FIX_09_RUNTIME_FUNCTIONAL_GAPS.md` em ordem.

Pontos obrigatórios:

1. Use `return_by_value=True` quando `execute_script` precisa retornar objeto, array ou dict.
2. Crie teste real provando que `page_get_tree` retorna nós em `simple.html`.
3. Crie teste provando que `js_evaluate` ou `js_evaluate_readonly` retorna objeto serializável.
4. Aplique `tab_operation_lock(tab_id)` em operações mutantes da mesma aba.
5. Corrija screenshot para não escrever em path arbitrário.
6. Corrija upload para usar `PathAllowlist`, nunca `startswith`.
7. Marque nós de `page_get_tree` com `actionable` e `resolution_confidence`.

## Como não repetir o erro

Não considere uma tool pronta só porque importa e os mocks passam. Para APIs Pydoll/CDP:

- valide pelo menos um caso com navegador real;
- diferencie retorno primitivo de retorno objeto em CDP;
- crie teste que falha antes da correção;
- não substitua validação real por mocks que retornam exatamente o formato que o código espera.

## Gates finais obrigatórios

Execute:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
```

Registre o resultado em:

```text
progress/2026-06-12_AGENT_FIX_09.md
```

## Critério de conclusão

Você só terminou quando `page_get_tree` retorna uma árvore não vazia em página real e há teste automatizado cobrindo isso.
