# Reavaliação após FIX_11

Data: 2026-06-12  
Escopo: revisão do estado após o desenvolvedor informar conclusão de `FIX_11_PATH_TRAVERSAL_AND_COOKIE_LOCK.md`.

## Resultado dos gates

Comandos executados:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
```

Resultados:

- `pytest -q`: 129 passed.
- `ruff check .`: All checks passed.
- `mypy src`: Success, 33 source files.
- `pytest -m browser_smoke -q`: 4 passed, 125 deselected.

## Pontos verificados

### Path traversal

Arquivo revisado:

```text
src/pydoll_mcp_server/security/paths.py
```

O helper agora:

- resolve path absoluto e diretórios permitidos com `resolve(strict=False)`;
- usa `relative_to`, não `startswith`;
- para path relativo, resolve o candidato dentro de `artifacts_dir` e valida que o resultado final ainda está dentro de `artifacts_dir`.

Probe manual executado:

```text
ok.png => C:\safe\root\artifacts\ok.png
subdir/screen.png => C:\safe\root\artifacts\subdir\screen.png
../escape.png => None
subdir/../../escape.png => None
../../Windows/Temp/x.png => None
```

Resultado: aprovado.

### Locks em `cookies_set`

Arquivo revisado:

```text
src/pydoll_mcp_server/tools/storage.py
```

O código agora:

- usa `tab_operation_lock(tab_id)` quando `tab_id` é informado;
- usa `browser_operation_lock(browser_id)` quando opera por `browser_id`.

Resultado: aprovado.

### Testes adicionados

Arquivos revisados:

```text
tests/unit/test_path_traversal.py
tests/unit/test_concurrency.py
```

Cobertura relevante:

- path relativo simples aceito;
- path relativo em subdiretório aceito;
- `../escape.png` rejeitado;
- `subdir/../../escape.png` rejeitado;
- path absoluto fora da allowlist rejeitado;
- path absoluto dentro de `artifacts_dir`, `downloads_dir` e `tmp_dir` aceito;
- `cookies_set` contém uso de `tab_operation_lock`;
- `cookies_set` contém uso de `browser_operation_lock`.

Resultado: aprovado para a etapa atual.

## Riscos residuais

- Alguns testes de lock ainda usam inspeção de source. Isso é aceitável para fechar a remediação atual, mas P1 deve substituir ou complementar com testes comportamentais usando fakes async e context managers instrumentados.
- `validate_artifact_path` ainda aceita path relativo com nomes de arquivos potencialmente estranhos. Isso não é bypass de diretório, mas P1 pode adicionar sanitização de nome se o projeto quiser padronizar artefatos.

## Decisão

Não encontrei novo bloqueador P0 ou P1 para a sequência de remediações.

O conjunto `FIX_08` a `FIX_11` agora está suficientemente corrigido para retomar o planejamento P1/P2 ou avançar para hardening adicional.
