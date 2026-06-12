# Planos de remediação dos problemas encontrados

Este diretório detalha a correção dos problemas encontrados na avaliação técnica registrada em `docs/evaluation-2026-06-12.md`.

## Ordem obrigatória

Execute em sequência:

1. `FIX_01_TRANSPORT_AND_AUTH.md`
2. `FIX_02_PYDOLL_API_COMPAT.md`
3. `FIX_03_ACTIONABLE_ELEMENT_IDS.md`
4. `FIX_04_DEEP_TRAVERSAL.md`
5. `FIX_05_CONCURRENCY_PROFILES.md`
6. `FIX_06_SECURITY_AND_ARTIFACTS.md`
7. `FIX_07_TEST_QUALITY_GATES.md`
8. `FIX_08_SECOND_PASS_VALIDATION.md`
9. `FIX_09_RUNTIME_FUNCTIONAL_GAPS.md`
10. `FIX_10_LOCKS_AND_ELEMENT_SCREENSHOT.md`
11. `FIX_11_PATH_TRAVERSAL_AND_COOKIE_LOCK.md`

Não avance para o próximo plano se o plano atual não cumprir seus critérios de aceite.

## Regra de reavaliação

Depois de cada plano:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
```

Depois do plano 7, todos devem passar:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
```

Depois do plano 8, também deve existir e passar um smoke real ou, se o ambiente impedir, deve haver justificativa técnica objetiva em `progress/`.

Depois do plano 9, deve existir teste de runtime provando que `page_get_tree` retorna árvore não vazia em página real e que retorno objeto de `execute_script` é tratado com `return_by_value=True`.

Depois do plano 10, os locks por recurso devem estar aplicados nas tools mutantes, não apenas definidos, e `element_screenshot` deve validar path como `page_screenshot`.

Depois do plano 11, traversal relativo em screenshots deve ser rejeitado e `cookies_set` deve usar locks para `tab_id` e `browser_id`.

## Princípio central

Não confunda código que importa com código que funciona. Um teste que só importa módulos não valida browser real, transporte MCP real, nem integração com Pydoll.

Cada correção precisa de teste que falharia antes da correção.
