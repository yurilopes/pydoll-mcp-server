# Prompt para o LLM desenvolvedor: FIX 11

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
2. `docs/evaluation-2026-06-12-fix10-review.md`
3. `plans/remediation/FIX_11_PATH_TRAVERSAL_AND_COOKIE_LOCK.md`
4. `progress/2026-06-12_AGENT_FIX_10.md`

## O que você acertou no FIX_10

Você aplicou locks em várias tools mutantes, validou `element_screenshot` para path absoluto proibido, extraiu `validate_artifact_path`, manteve os gates verdes e adicionou testes.

## O que ainda está errado

Há dois resíduos:

1. `validate_artifact_path` aceita traversal relativo. Exemplo: `../escape.png` vira `artifacts_dir/../escape.png` e escapa de `artifacts_dir` após resolução.
2. `cookies_set` ainda não usa lock. O plano pedia `tab_operation_lock` com `tab_id` e `browser_operation_lock` com `browser_id`.

O primeiro item é bloqueador de segurança. Não trate como P2.

## Como corrigir

Execute `plans/remediation/FIX_11_PATH_TRAVERSAL_AND_COOKIE_LOCK.md`.

Pontos obrigatórios:

- Corrigir `validate_artifact_path` para resolver path relativo e garantir que continua dentro de `artifacts_dir`.
- Adicionar testes para `../escape.png` e `subdir/../../escape.png`.
- Garantir que `page_screenshot` e `element_screenshot` rejeitam traversal relativo.
- Aplicar `tab_operation_lock` e `browser_operation_lock` em `cookies_set`.
- Adicionar testes de lock para `cookies_set`.

## Como se reavaliar corretamente

Não basta rejeitar path absoluto fora da allowlist. Você precisa testar path relativo com `..`.

Não basta `storage_set` usar lock. `cookies_set` também é mutação de estado do navegador.

Não use `startswith` para paths. Use `Path.resolve(strict=False)` e `relative_to`.

## Gates finais

Execute:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
```

Registre em:

```text
progress/2026-06-12_AGENT_FIX_11.md
```

## Critério de conclusão

Você só terminou quando:

- traversal relativo em screenshot é bloqueado;
- `cookies_set` usa lock correto para `tab_id` e `browser_id`;
- os gates finais passam.
