# FIX_05: Concorrência, locks e perfis persistentes

## Problema

O `LockManager` existe, mas as tools mutantes quase não usam locks. Além disso, o perfil persistente default não é travado em `browser_launch`, o que pode causar conflito real no Chrome.

## Arquivos envolvidos

- `src/pydoll_mcp_server/browser/locks.py`
- `src/pydoll_mcp_server/browser/profiles.py`
- `src/pydoll_mcp_server/tools/browser.py`
- `src/pydoll_mcp_server/tools/tabs.py`
- `src/pydoll_mcp_server/tools/page.py`
- `src/pydoll_mcp_server/tools/elements.py`
- `src/pydoll_mcp_server/tools/javascript.py`
- `src/pydoll_mcp_server/tools/storage.py`
- `src/pydoll_mcp_server/tools/files.py`
- `tests/unit/test_registry.py`

## Objetivo

Garantir que operações concorrentes em recursos independentes possam rodar em paralelo, mas operações mutantes no mesmo recurso sejam serializadas.

## Tarefas detalhadas

1. Criar helpers async:
   - `tab_operation_lock(tab_id, owner)`;
   - `browser_operation_lock(browser_id, owner)`;
   - `profile_operation_lock(profile_id, owner)`.
2. Ajustar `ResourceLock.acquire` para não marcar owner antes do lock ser realmente adquirido.
3. Usar `async with` para garantir release mesmo com exceção.
4. Em `browser_launch`, travar qualquer perfil persistente:
   - default;
   - nomeado.
5. Liberar lock de perfil em:
   - falha de launch;
   - `browser_close`;
   - cleanup de registry.
6. Remover perfil temporário no close, salvo se houver decisão explícita contrária.
7. Aplicar lock mutante de tab em:
   - `page_goto`;
   - `page_reload`;
   - `page_back`;
   - `page_forward`;
   - `element_click`;
   - `element_type`;
   - `element_fill`;
   - `js_evaluate`;
   - `storage_set`;
   - `upload_files`;
   - `tab_recover`.
8. Aplicar lock de leitura ou observação somente quando necessário. Não bloquear `page_get_text` em outra tab.
9. Criar tests:
   - duas operações mutantes na mesma tab serializam;
   - operações em tabs diferentes rodam em paralelo;
   - dois launches no mesmo perfil default não correm juntos;
   - lock é liberado se launch falha.

## Critérios de aceite

- O mesmo perfil persistente não é usado por dois browsers simultâneos.
- Mutação na mesma tab é serializada.
- Duas tabs independentes não se bloqueiam.
- Locks não ficam presos após exceção.

## Como testar

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest tests\unit\test_registry.py -q
C:\Users\Yuri\anaconda3\python.exe -m pytest -k "lock or profile or concurrency" -q
```

## Erros a evitar

- Não usar dict de locks sem `async with`.
- Não serializar o servidor inteiro com lock global.
- Não permitir perfil persistente default sem lock.
- Não esquecer cleanup em falhas.

## Definição de pronto

Este plano está pronto quando a concorrência segura é demonstrada por tests, não apenas por existência do `LockManager`.
