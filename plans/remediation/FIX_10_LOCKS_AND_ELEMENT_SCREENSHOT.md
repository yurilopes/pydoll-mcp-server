# FIX 10: Locks mutantes e segurança de element_screenshot

## Objetivo

Fechar os dois critérios de aceite que ficaram pendentes após `FIX_09`: aplicar locks por recurso nas operações mutantes e impedir escrita arbitrária em `element_screenshot`.

## Escopo

- Aplicar `tab_operation_lock(tab_id)` nas tools mutantes por aba.
- Aplicar `browser_operation_lock(browser_id)` quando houver mutação de browser inteiro.
- Validar `path` em `element_screenshot`.
- Criar testes específicos para concorrência e path proibido.
- Manter os gates atuais verdes.

## Fora de escopo

- Alterar `return_by_value=True` já corrigido.
- Reescrever `page_get_tree`.
- Mudar API pública das tools, exceto se necessário para retorno de erro estruturado.
- Implementar network, console, trace ou recursos P1/P2.

## Pré-requisitos

- Ler `docs/evaluation-2026-06-12-fix09-review.md`.
- Ler `plans/remediation/FIX_09_RUNTIME_FUNCTIONAL_GAPS.md`.
- Ler `progress/2026-06-12_AGENT_FIX_09.md`.
- Confirmar gates verdes antes de editar.

## Critérios de início

- `git status --short` foi verificado.
- O agente sabe que `return_by_value=True` já foi corrigido e não deve desfazer isso.
- O agente sabe que `await tab.current_url`, `await tab.title` e `await element.text` continuam corretos sem parênteses.

## Tarefas detalhadas

### T1: Aplicar locks nas operações de navegação

Em `src/pydoll_mcp_server/tools/page.py`, usar:

```python
async with tab_operation_lock(tab_id):
    ...
```

nas operações:

- `page_goto`;
- `page_reload`;
- `page_back`;
- `page_forward`.

O lock deve envolver a seção que modifica a aba, chama Pydoll e atualiza `tab_info`.

### T2: Aplicar locks nas interações de elemento

Em `src/pydoll_mcp_server/tools/elements.py`, aplicar `tab_operation_lock(tab_id)` em:

- `element_click`;
- `element_type`;
- `element_fill`;
- `element_screenshot` quando escrever arquivo.

Leituras puras como `element_get_text` e `element_get_attribute` podem ficar sem lock, exceto se o agente justificar o contrário.

### T3: Aplicar locks em tabs e storage

Em `src/pydoll_mcp_server/tools/tabs.py`, aplicar lock em:

- `tab_close`;
- `tab_recover`.

Em `src/pydoll_mcp_server/tools/storage.py`, aplicar lock em:

- `storage_set`;
- `cookies_set` quando usar `tab_id`.

Quando `cookies_set` usar `browser_id`, usar `browser_operation_lock(browser_id)`.

### T4: Validar path em `element_screenshot`

Não duplicar lógica de path.

Opção recomendada:

- mover `_validate_artifact_path` de `dom/tree.py` para um helper comum, por exemplo `security/paths.py`;
- usar o mesmo helper em `page_screenshot` e `element_screenshot`.

Regras:

- sem `path`, retornar base64 como hoje;
- com `path` relativo, salvar dentro de `config.artifacts_dir`;
- com `path` absoluto, aceitar apenas dentro de `artifacts_dir`, `downloads_dir` ou `tmp_dir`;
- path proibido retorna erro estruturado `PERMISSION_DENIED`.

### T5: Testes de concorrência

Criar teste unitário sem browser real que prove:

- duas chamadas mutantes na mesma aba não entram simultaneamente na seção crítica;
- chamadas mutantes em abas diferentes usam locks diferentes.

Sugestão:

- usar fakes async com eventos `asyncio.Event`;
- instrumentar uma operação simples ou testar diretamente `tab_operation_lock`;
- o teste precisa falhar se a tool não usar o lock.

Não basta testar `tab_operation_lock` isolado. O teste precisa provar que pelo menos uma tool mutante usa o lock.

### T6: Teste de `element_screenshot` com path proibido

Criar teste unitário com fake element cacheado.

Entrada:

```text
path = C:\Windows\Temp\forbidden.png
```

ou equivalente fora dos diretórios permitidos.

Resultado esperado:

- `success` ausente ou falso;
- `error_code == "PERMISSION_DENIED"`;
- `element.take_screenshot` não é chamado.

### T7: Melhorar teste de `js_evaluate`

Opcional, mas recomendado:

- adicionar teste que chama `js_evaluate_readonly` real, não só `tab.execute_script`.

## Critérios de aceite

- `tab_operation_lock` é usado pelas operações mutantes listadas.
- `browser_operation_lock` é usado para mutação por `browser_id`.
- `element_screenshot` não aceita path arbitrário.
- Existe teste que falha se uma tool mutante não usar lock.
- Existe teste que falha se `element_screenshot` aceitar path proibido.
- Gates finais passam.

## Definição de pronto

O plano está pronto quando os dois itens marcados como pendência no progresso do `FIX_09` forem corrigidos, testados e registrados em novo progresso.

## Como testar

Executar:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
```

## Riscos

- Locks aplicados em ordem inconsistente podem causar deadlock. Evite adquirir múltiplos locks numa mesma operação.
- Lock amplo demais pode reduzir concorrência entre abas. Use lock por aba quando a mutação é de aba.
- Não mover path helper de forma que quebre `page_screenshot`, que já está funcionando.

## Estratégia de recuperação se interrompido

1. Ler este arquivo.
2. Ler `docs/evaluation-2026-06-12-fix09-review.md`.
3. Verificar se existe `progress/2026-06-12_AGENT_FIX_10.md`.
4. Rodar `pytest -q`.
5. Continuar da primeira tarefa incompleta.

## Artefatos esperados

- Código corrigido em `src/`.
- Testes novos ou ampliados em `tests/`.
- Registro curto em `progress/2026-06-12_AGENT_FIX_10.md`.

## Notas para o próximo agente

Não trate os itens como P2. Eles eram critérios de aceite do `FIX_09`. O objetivo do `FIX_10` é somente fechar esse débito sem mexer nas partes já corretas.
