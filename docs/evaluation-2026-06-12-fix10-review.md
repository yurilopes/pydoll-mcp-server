# Reavaliação após FIX_10

Data: 2026-06-12  
Escopo: revisão do estado após o desenvolvedor informar conclusão de `FIX_10_LOCKS_AND_ELEMENT_SCREENSHOT.md`.

## Resultado dos gates

Comandos executados:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
```

Resultados:

- `pytest -q`: 118 passed.
- `ruff check .`: All checks passed.
- `mypy src`: Success, 33 source files.
- `pytest -m browser_smoke -q`: 4 passed, 114 deselected.

## Pontos corrigidos corretamente

- `page_goto`, `page_reload`, `page_back` e `page_forward` usam `tab_operation_lock`.
- `element_click`, `element_type`, `element_fill` e `element_screenshot` usam `tab_operation_lock`.
- `tab_close` e `tab_recover` usam `tab_operation_lock`.
- `storage_set` usa `tab_operation_lock`.
- `element_screenshot` rejeita path absoluto fora dos diretórios permitidos.
- `page_screenshot` e `element_screenshot` usam helper comum `validate_artifact_path`.
- Gates continuam verdes.

## Findings

### 1. `validate_artifact_path` aceita traversal relativo

Severidade: P0  
Arquivo: `src/pydoll_mcp_server/security/paths.py`.

O helper aceita qualquer path relativo retornando diretamente:

```python
return str(config.artifacts_dir / p)
```

Sem normalizar e verificar `relative_to(config.artifacts_dir)`, paths como `../escape.png` e `../../Windows/Temp/x.png` escapam do diretório de artifacts.

Validação executada:

```text
ok.png => C:\safe\root\artifacts\ok.png
../escape.png => C:\safe\root\artifacts\..\escape.png, resolved C:\safe\root\escape.png
../../Windows/Temp/x.png => C:\safe\root\artifacts\..\..\Windows\Temp\x.png, resolved C:\safe\Windows\Temp\x.png
```

Impacto:

- `page_screenshot` e `element_screenshot` continuam podendo escrever fora de `artifacts_dir` usando path relativo com `..`.
- O teste atual só cobre path absoluto proibido e path relativo simples.

Correção esperada:

- Para path relativo, construir `candidate = (config.artifacts_dir / path).resolve(strict=False)`.
- Aceitar somente se `candidate.relative_to(config.artifacts_dir.resolve(strict=False))` funcionar.
- Rejeitar traversal relativo com `PERMISSION_DENIED`.
- Criar testes para `../escape.png`, `subdir/../../escape.png` e equivalente Windows.

### 2. `cookies_set` ainda não usa lock

Severidade: P1  
Arquivo: `src/pydoll_mcp_server/tools/storage.py`.

O plano `FIX_10` exigia:

- `cookies_set` com `tab_id`: usar `tab_operation_lock(tab_id)`;
- `cookies_set` com `browser_id`: usar `browser_operation_lock(browser_id)`.

O código atual importa apenas `tab_operation_lock` e aplica lock em `storage_set`, mas `cookies_set` ainda chama `set_cookies` sem lock.

Impacto:

- duas mutações concorrentes de cookies podem intercalar estado;
- o critério de aceite de `browser_operation_lock` não foi cumprido.

Correção esperada:

- importar `browser_operation_lock`;
- envolver `pydoll_tab.set_cookies(cookies)` em `tab_operation_lock(tab_id)`;
- envolver `browser.set_cookies(cookies)` em `browser_operation_lock(browser_id)`;
- adicionar teste que falha se `cookies_set` não usar os locks.

### 3. Testes de locks ainda usam inspeção de source

Severidade: P2  
Arquivo: `tests/unit/test_concurrency.py`.

Os testes verificam strings no source, por exemplo:

```python
assert 'tab_operation_lock' in source
```

Isso é útil como barreira mínima, mas não prova serialização dentro da tool. O `FIX_10` aceitou isso para avançar, mas a próxima rodada deve trocar pelo menos um teste para instrumentação real com fake async.

Correção recomendada:

- monkeypatchar `tab_operation_lock` com context manager fake que registra entrada e saída;
- chamar uma tool mutante com fake Pydoll;
- provar que a operação crítica ocorreu dentro do context manager.

## Decisão

O `FIX_10` resolveu parte substancial dos riscos, mas ainda não está pronto para avançar sem `FIX_11`.

O bloqueador é `validate_artifact_path` aceitar traversal relativo. Isso afeta diretamente `page_screenshot` e `element_screenshot`.
