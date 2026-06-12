# FIX 11: Traversal relativo em artifacts e lock em cookies_set

## Objetivo

Corrigir o bypass de path relativo no helper de artifacts e aplicar locks ausentes em `cookies_set`.

## Escopo

- Corrigir `validate_artifact_path` para bloquear `..` em paths relativos.
- Adicionar testes para traversal relativo em screenshots.
- Aplicar `tab_operation_lock` e `browser_operation_lock` em `cookies_set`.
- Adicionar testes para locks de `cookies_set`.
- Manter os gates verdes.

## Fora de escopo

- Reescrever todos os testes de concorrência.
- Alterar API pública das tools.
- Mexer em `return_by_value=True`.
- Expandir P1/P2.

## Pré-requisitos

- Ler `docs/evaluation-2026-06-12-fix10-review.md`.
- Ler `plans/remediation/FIX_10_LOCKS_AND_ELEMENT_SCREENSHOT.md`.
- Ler `progress/2026-06-12_AGENT_FIX_10.md`.
- Confirmar gates verdes antes de editar.

## Critérios de início

- `git status --short` foi verificado.
- O agente sabe que paths relativos simples continuam permitidos dentro de `artifacts_dir`.
- O agente sabe que paths relativos com `..` devem ser rejeitados se escaparem de `artifacts_dir`.

## Tarefas detalhadas

### T1: Corrigir `validate_artifact_path`

Arquivo:

```text
src/pydoll_mcp_server/security/paths.py
```

Regra para path relativo:

```python
base = config.artifacts_dir.resolve(strict=False)
candidate = (base / path).resolve(strict=False)
candidate.relative_to(base)
```

Se `relative_to` falhar, retornar `None`.

Regra para path absoluto:

- manter allowlist de `artifacts_dir`, `downloads_dir` e `tmp_dir`;
- resolver cada diretório permitido antes de comparar;
- usar `relative_to`, nunca `startswith`.

### T2: Testar traversal relativo

Criar ou ampliar testes para `validate_artifact_path` diretamente.

Casos obrigatórios:

- `screenshot.png` aceito dentro de `artifacts_dir`;
- `subdir/screenshot.png` aceito dentro de `artifacts_dir`;
- `../escape.png` rejeitado;
- `subdir/../../escape.png` rejeitado;
- equivalente Windows com backslash, se aplicável.

Também adicionar pelo menos um teste via `element_screenshot` ou `page_screenshot` garantindo que `take_screenshot` não é chamado quando o path relativo tenta escapar.

### T3: Aplicar locks em `cookies_set`

Arquivo:

```text
src/pydoll_mcp_server/tools/storage.py
```

Regras:

- se `tab_id` for informado, envolver `pydoll_tab.set_cookies(cookies)` em `async with tab_operation_lock(tab_id)`;
- se `browser_id` for informado, envolver `browser.set_cookies(cookies)` em `async with browser_operation_lock(browser_id)`;
- importar `browser_operation_lock`.

### T4: Testar locks em `cookies_set`

Adicionar testes que verifiquem:

- `cookies_set` com `tab_id` usa `tab_operation_lock`;
- `cookies_set` com `browser_id` usa `browser_operation_lock`.

Preferência:

- monkeypatchar os context managers com fakes async que registram uso;
- chamar `cookies_set` com fake tab/browser;
- evitar apenas inspeção textual de source quando viável.

### T5: Registrar progresso

Criar:

```text
progress/2026-06-12_AGENT_FIX_11.md
```

Conteúdo curto:

- tarefas feitas;
- arquivos alterados;
- testes executados;
- riscos restantes.

## Critérios de aceite

- `validate_artifact_path('../escape.png', config)` retorna `None`.
- `validate_artifact_path('subdir/../../escape.png', config)` retorna `None`.
- Path relativo normal continua aceito dentro de `artifacts_dir`.
- `page_screenshot` e `element_screenshot` rejeitam traversal relativo.
- `cookies_set` usa lock por aba quando recebe `tab_id`.
- `cookies_set` usa lock por browser quando recebe `browser_id`.
- Gates finais passam.

## Definição de pronto

O plano está pronto quando traversal relativo não escapa de `artifacts_dir` e `cookies_set` cumpre os locks previstos no `FIX_10`.

## Como testar

Executar:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
```

## Riscos

- Usar `Path.resolve()` em path inexistente é permitido com `strict=False`.
- Comparar paths no Windows precisa evitar string prefix.
- Não bloquear paths relativos válidos como `screenshots/a.png`.

## Estratégia de recuperação se interrompido

1. Ler este arquivo.
2. Ler `docs/evaluation-2026-06-12-fix10-review.md`.
3. Verificar se existe `progress/2026-06-12_AGENT_FIX_11.md`.
4. Rodar `pytest -q`.
5. Continuar da primeira tarefa incompleta.

## Artefatos esperados

- `src/pydoll_mcp_server/security/paths.py` corrigido.
- `src/pydoll_mcp_server/tools/storage.py` corrigido.
- Testes novos ou ampliados.
- `progress/2026-06-12_AGENT_FIX_11.md`.
