# Prompt para o LLM desenvolvedor: FIX 10

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
2. `docs/evaluation-2026-06-12-fix09-review.md`
3. `plans/remediation/FIX_10_LOCKS_AND_ELEMENT_SCREENSHOT.md`
4. `progress/2026-06-12_AGENT_FIX_09.md`

## O que você acertou no FIX_09

Você corrigiu o bloqueador de runtime mais importante:

- `page_get_tree` agora retorna árvore real.
- `return_by_value=True` foi aplicado nos retornos de objeto.
- `extract_script_value()` está correto para o formato CDP/Pydoll.
- `upload_files` não usa mais `startswith`.
- `page_screenshot` valida path.
- Os gates estão verdes.

Não desfaça essas correções.

## O que ficou errado

Você marcou como P2 dois itens que eram critérios de aceite do FIX_09:

1. `tab_operation_lock` está definido, mas não aplicado nas tools de navegação e mutação.
2. `element_screenshot` ainda aceita path arbitrário.

Isso não pode ficar para P2 porque:

- concorrência por aba era requisito central desde o planejamento;
- escrita arbitrária no filesystem viola a política de segurança do projeto.

## Como corrigir

Execute `plans/remediation/FIX_10_LOCKS_AND_ELEMENT_SCREENSHOT.md`.

Pontos obrigatórios:

1. Aplicar `tab_operation_lock(tab_id)` nas operações mutantes por aba.
2. Aplicar `browser_operation_lock(browser_id)` quando a mutação for por browser.
3. Validar `path` em `element_screenshot` usando o mesmo helper de `page_screenshot`.
4. Criar teste que prove que uma tool mutante usa lock.
5. Criar teste que prove que `element_screenshot` rejeita path proibido e não chama `take_screenshot`.

## Como se reavaliar corretamente

Não basta o lock existir no módulo `browser/locks.py`. Você precisa provar que as tools usam o lock.

Não basta `page_screenshot` estar seguro. `element_screenshot` também expõe escrita em arquivo e precisa da mesma política.

Não basta gate verde. O teste precisa falhar antes da correção principal.

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
progress/2026-06-12_AGENT_FIX_10.md
```

## Critério de conclusão

Você só terminou quando os dois riscos do progresso `FIX_09` deixam de existir:

- locks aplicados, não apenas definidos;
- `element_screenshot` com path validado.
