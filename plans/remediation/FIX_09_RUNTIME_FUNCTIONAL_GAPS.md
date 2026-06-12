# FIX 09: Lacunas funcionais de runtime após FIX 08

## Objetivo

Corrigir bugs que passam nos gates estáticos, mas quebram comportamento real do MCP server com Pydoll, principalmente `page_get_tree`, retornos de JavaScript por valor, locks por recurso e segurança de paths.

## Escopo

- Corrigir `execute_script` para retornos serializáveis por valor.
- Fazer `page_get_tree` retornar nós reais em página local.
- Aplicar locks por recurso nas operações mutantes.
- Bloquear escrita arbitrária em screenshots.
- Reusar allowlist segura em upload.
- Fortalecer testes de runtime.

## Fora de escopo

- Reescrever arquitetura do servidor.
- Implementar Playwright-like completo.
- Refatorar todos os selectors agent-friendly.
- Implementar network tracing ou console inspection.
- Mudar transporte HTTP/SSE já criado.

## Pré-requisitos

- Ler `docs/evaluation-2026-06-12-fix08-review.md`.
- Ler `plans/remediation/FIX_08_SECOND_PASS_VALIDATION.md`.
- Confirmar que os gates atuais estão verdes antes de começar.
- Usar Python em `C:\Users\Yuri\anaconda3\python.exe`.

## Critérios de início

- `git status --short` foi verificado.
- O agente leu o progresso mais recente em `progress/`.
- O agente confirmou que `Tab.current_url`, `Tab.title` e `WebElement.text` continuam como async properties, sem parênteses.
- O agente sabe que `WebElement.get_shadow_root` é método async com parênteses.

## Tarefas detalhadas

### T1: Corrigir retornos de `execute_script`

Atualizar todos os pontos que esperam objeto, array ou dict:

- `src/pydoll_mcp_server/dom/tree.py`
- `src/pydoll_mcp_server/tools/javascript.py`
- `src/pydoll_mcp_server/tools/storage.py`
- `src/pydoll_mcp_server/browser/cdp_helpers.py`
- `src/pydoll_mcp_server/recovery/health.py`

Regra:

- Se o resultado esperado é objeto, array, dict ou valor JSON serializável, chamar `execute_script(..., return_by_value=True)`.
- Em `js_evaluate_readonly`, se a Pydoll suportar, usar também `throw_on_side_effect=True`. Se isso quebrar scripts legítimos, documentar e testar.
- Manter timeout externo com `asyncio.wait_for`.

### T2: Criar teste que prove `page_get_tree` real

Criar ou ampliar teste de integração com browser real:

- abrir `tests/fixtures/pages/simple.html`;
- registrar browser e tab no registry;
- chamar `build_page_tree`;
- exigir `success=True`;
- exigir `count > 0`;
- exigir `root_id` não vazio;
- exigir pelo menos um nó com tag `button` ou texto conhecido.

Esse teste deve falhar antes da correção de `return_by_value=True`.

### T3: Criar teste para `js_evaluate` retornando objeto

Teste esperado:

- script: `return {answer: 42, text: "ok"};`
- tool: `js_evaluate_readonly` ou helper interno;
- retorno deve ser JSON serializável;
- não pode retornar `null` só porque CDP devolveu `objectId`.

### T4: Aplicar locks por recurso

Usar `tab_operation_lock(tab_id)` nas operações mutantes:

- `page_goto`;
- `page_reload`;
- `page_back`;
- `page_forward`;
- `element_click`;
- `element_type`;
- `element_fill`;
- `tab_close`;
- `tab_recover`;
- `storage_set`;
- `cookies_set` quando houver `tab_id`.

Usar `browser_operation_lock(browser_id)` quando a operação afetar o browser inteiro.

Criar teste de concorrência:

- duas operações mutantes na mesma aba devem executar em série;
- duas operações em abas diferentes não devem usar o mesmo lock.

### T5: Bloquear escrita arbitrária de screenshots

Atualizar:

- `page_screenshot`;
- `element_screenshot`.

Regras:

- Sem `path`, retornar base64 como hoje.
- Com `path` relativo, resolver dentro de `config.artifacts_dir`.
- Com `path` absoluto, aceitar somente se estiver em diretório permitido.
- Usar `PathAllowlist` ou helper comum baseado em `Path.relative_to`.
- Retornar erro estruturado `PERMISSION_DENIED` para caminho proibido.

### T6: Corrigir upload allowlist

Atualizar `upload_files` para usar `PathAllowlist`.

Regras:

- Não usar `startswith` para validar path.
- Validar `resolve(strict=False)` e `relative_to`.
- Conferir que cada arquivo existe antes de chamar Pydoll.
- Retornar erro estruturado se algum path for negado.

### T7: Marcar acionabilidade em `page_get_tree`

Sem resolver todo o problema de referência perfeita nesta etapa, adicionar metadados claros:

- `actionable: true` se o nó tem hint confiável;
- `actionable: false` se o nó não deve ser usado diretamente em `element_click`;
- `selector_hint`;
- `xpath_hint`;
- `resolution_confidence`, por exemplo `high`, `medium`, `low`.

Evitar pseudo seletor `:has-text(...)` como CSS para Pydoll. Para texto, prefira XPath hint.

### T8: Registrar progresso

Criar:

```text
progress/2026-06-12_AGENT_FIX_09.md
```

Conteúdo curto:

- tarefas feitas;
- arquivos alterados;
- testes executados;
- riscos restantes;
- próximo passo.

## Critérios de aceite

- `page_get_tree` retorna nós reais em `simple.html`.
- `js_evaluate_readonly` ou `js_evaluate` retorna objeto serializável quando o script retorna objeto.
- Operações mutantes na mesma aba usam lock.
- Screenshot com path proibido retorna `PERMISSION_DENIED`.
- Upload não usa validação por prefixo de string.
- `pytest`, `ruff`, `mypy` e `browser_smoke` passam.

## Definição de pronto

Todos os critérios de aceite estão cumpridos e há testes que falhariam antes das correções principais.

## Como testar

Executar:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
```

Também executar um teste real ou script equivalente que confirme:

```python
result = await build_page_tree(client_id, tab_id)
assert result["count"] > 0
```

## Riscos

- `return_by_value=True` pode falhar para objetos não serializáveis. Nesse caso, retornar erro estruturado ou string segura, mas não retornar `None` silenciosamente.
- Locks podem causar deadlock se usados em ordem inconsistente. Use apenas um lock por operação quando possível.
- Path validation em Windows precisa usar `Path.resolve(strict=False)` e `relative_to`.

## Estratégia de recuperação se interrompido

1. Ler este arquivo.
2. Ler `docs/evaluation-2026-06-12-fix08-review.md`.
3. Verificar `progress/2026-06-12_AGENT_FIX_09.md`, se existir.
4. Rodar `pytest -q` para entender o estado.
5. Continuar da primeira tarefa incompleta.

## Artefatos esperados

- Correções no código em `src/`.
- Testes novos ou ampliados em `tests/`.
- Registro em `progress/2026-06-12_AGENT_FIX_09.md`.

## Notas para o próximo agente

Não altere `await tab.current_url`, `await tab.title` ou `await element.text` para chamadas com parênteses. Essas APIs são async properties na Pydoll local.

O erro central desta rodada não é sintaxe async property. O erro central é confundir `execute_script` que retorna primitivo com `execute_script` que retorna objeto CDP por referência.
