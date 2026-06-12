# Segunda avaliação da remediação

Data: 2026-06-12.

## Veredito

O desenvolvedor avançou em algumas correções, mas a remediação ainda não está pronta. A suíte de testes aumentou para 104 testes e `mypy` agora passa, mas `ruff` ainda falha e ainda existem bugs funcionais centrais escondidos por testes fracos.

O problema principal continua sendo o mesmo: o desenvolvedor corrige para satisfazer testes superficiais, mas não valida o comportamento real contra a Pydoll local e contra o SDK MCP instalado.

## Validações executadas

```powershell
Remove-Item Env:PYDOLL_MCP_ALLOW_NO_AUTH -ErrorAction SilentlyContinue
Remove-Item Env:PYDOLL_MCP_AUTH_TOKEN -ErrorAction SilentlyContinue
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
```

Resultado: `104 passed in 1.08s`.

```powershell
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
```

Resultado: falhou com 17 erros.

```powershell
C:\Users\Yuri\anaconda3\python.exe -m mypy src
```

Resultado: `Success: no issues found in 31 source files`.

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
```

Resultado: `104 deselected`. Não há smoke real.

## Melhorias observadas

- `mypy src` agora passa.
- `browser_launch` passou a usar `options.add_argument('--user-data-dir=...')` e `options.headless = headless`.
- O perfil default persistente agora é travado em `browser_launch`.
- Foi criado `src/pydoll_mcp_server/browser/pydoll_compat.py`.
- Foram criados testes de reaquisição por selector hint em `tests/integration/test_element_resolution.py`.
- `PathAllowlist` passou a usar `relative_to`, bloqueando bypass por prefixo textual.

## Problemas restantes

### 1. Correção da avaliação sobre `pydoll_compat.py`

Arquivo: `src/pydoll_mcp_server/browser/pydoll_compat.py`.

Correção posterior: esta segunda avaliação errou neste ponto. O desenvolvedor estava certo. Na Pydoll local, `Tab.current_url`, `Tab.title` e `WebElement.text` são async properties. Portanto esta sintaxe está correta:

```python
await tab.current_url
await tab.title
await element.text
```

O erro foi meu: os fakes usados na avaliação eram métodos async comuns, não async properties. A ação correta é criar testes com `@property async def` para validar a assinatura real, mantendo a sintaxe sem parênteses.

### 2. Os testes não capturam assinatura real da Pydoll

Os testes novos validam selector hints, mas não validam `get_tab_url`, `get_tab_title` e `get_element_text` com objetos que têm async properties reais.

Impacto: `pytest` passa mesmo com integração Pydoll quebrada.

### 3. O servidor não monta `/mcp` e `/sse` como planejado

Arquivo: `src/pydoll_mcp_server/server.py`.

O código usa `mcp.streamable_http_app()`, mas monta em `Mount('/', app=mcp_app)`.

Rotas observadas:

```text
Route(path='/health', ...)
Mount(path='', ...)
```

Não há mount explícito em `/mcp` nem `/sse`. O plano pedia `/mcp` para Streamable HTTP e `/sse` para SSE quando disponível.

Os testes atuais verificam que `/mcp` não retorna 404, mas isso passa porque o app MCP foi montado na raiz, não porque `/mcp` foi montado corretamente.

### 4. `test_mcp_accepts_valid_token` aceita exceção e passa

Arquivo: `tests/contract/test_mcp_contract.py`.

O teste captura `RuntimeError` e faz `pass`. Isso permite que o teste passe mesmo quando o endpoint não funciona de verdade.

### 5. Shadow traversal chama `get_shadow_root` sem `await`

Arquivo: `src/pydoll_mcp_server/dom/deep_traversal.py`.

O código faz:

```python
sr = el.get_shadow_root(timeout=2)
```

Na Pydoll, `get_shadow_root` é async. O correto é:

```python
sr = await el.get_shadow_root(timeout=2)
```

Impacto: traversal de shadow DOM ainda não funciona corretamente e pode gerar coroutine não aguardada.

### 6. Ruff ainda falha

Ainda há 17 violações de ruff, incluindo linhas longas e variável de loop não usada em `tools/elements.py`.

Impacto: `FIX_07_TEST_QUALITY_GATES.md` não foi concluído.

### 7. Smoke real não existe

`pytest -m browser_smoke -q` seleciona zero testes. O plano exigia smoke real ou justificativa técnica objetiva.

## Conclusão

O estado atual é melhor que o anterior, mas ainda não pode ser marcado como remediação concluída. O próximo desenvolvedor deve executar `FIX_08_SECOND_PASS_VALIDATION.md` antes de qualquer trabalho de P2.
