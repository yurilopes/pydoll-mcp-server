# FIX_06: Segurança de paths, artifacts, cookies, storage e valores sensíveis

## Problema

A segurança foi modelada, mas ainda há riscos práticos:

- `PathAllowlist` usa `startswith` textual.
- Screenshots aceitam paths sem validação clara.
- Downloads não passam diretório controlado para `expect_download`.
- `storage_get` e `storage_set` recebem `origin`, mas não validam ou usam esse campo.
- Atributos sensíveis podem ser retornados sem redaction.

## Arquivos envolvidos

- `src/pydoll_mcp_server/security/policy.py`
- `src/pydoll_mcp_server/tools/files.py`
- `src/pydoll_mcp_server/tools/storage.py`
- `src/pydoll_mcp_server/dom/tree.py`
- `src/pydoll_mcp_server/tools/elements.py`
- `tests/unit/test_security.py`
- `tests/unit/test_javascript.py`

## Objetivo

Fechar bypasses de path e garantir que artifacts e dados sensíveis sejam tratados de forma segura por padrão.

## Tarefas detalhadas

1. Trocar allowlist por relação real de paths:

```python
try:
    resolved.relative_to(allowed)
    return True
except ValueError:
    ...
```

ou usar `Path.is_relative_to` quando disponível.

2. Normalizar allowed dirs e paths com `resolve(strict=False)`.
3. Criar tests para:
   - path permitido;
   - path fora da allowlist;
   - path traversal;
   - prefixo parecido, como `allowed-other`.
4. Aplicar `PathAllowlist` em:
   - `page_screenshot`;
   - `element_screenshot`;
   - `download_expect`;
   - `upload_files`.
5. Corrigir `download_expect`:
   - passar `keep_file_at=download_dir`;
   - garantir que o arquivo final está dentro de `downloads_dir/client_id`;
   - retornar artifact metadata.
6. Em `element_get_attribute`, redigir por padrão se `name` for sensível:
   - value;
   - password;
   - token;
   - authorization;
   - cookie;
   - secret.
7. Em `storage_get` e `storage_set`:
   - se `origin` for informado, validar que bate com a origem atual;
   - se não for informado, documentar e retornar `origin_used`;
   - nunca permitir leitura ampla sem redaction por padrão.
8. Em cookies:
   - exigir escopo por browser ou tab;
   - redigir por padrão;
   - documentar que `redact_values=false` é sensível.
9. Atualizar README e `docs/evaluation-2026-06-12.md` se necessário.

## Critérios de aceite

- `PathAllowlist` não aceita prefixos parecidos.
- Screenshots e downloads não escrevem fora do runtime dir ou allowlist.
- Upload fora de allowlist falha.
- Atributos sensíveis são redigidos.
- Storage informa a origem usada e mantém redaction por padrão.

## Como testar

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest tests\unit\test_security.py -q
C:\Users\Yuri\anaconda3\python.exe -m pytest -k "storage or cookie or screenshot or upload or download" -q
```

## Erros a evitar

- Não comparar paths com `startswith`.
- Não aceitar path absoluto arbitrário por conveniência.
- Não retornar cookies ou storage sem redaction por padrão.
- Não registrar valores de campos em logs.

## Definição de pronto

Este plano está pronto quando paths, artifacts e dados sensíveis têm tests negativos e positivos.
