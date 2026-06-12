# FIX_08: Segunda passagem de validação e correção final

## Objetivo

Corrigir os problemas que permaneceram após a primeira remediação e impedir que testes superficiais escondam bugs de integração real.

## Escopo

- Validar `pydoll_compat.py` com fakes fiéis às async properties da Pydoll.
- Corrigir mounts HTTP MCP para `/mcp` e `/sse`.
- Remover testes que passam ignorando exceção real.
- Corrigir shadow traversal com `await`.
- Fechar `ruff`.
- Criar ou justificar smoke real.

## Fora de escopo

- Implementar P2.
- Refatorar arquitetura inteira.
- Adicionar features novas de network, console ou tracing.

## Critérios de início

- Ler `docs/evaluation-2026-06-12-remediation-review.md`.
- Rodar e confirmar:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
```

- Registrar progresso em `progress/YYYY-MM-DD_AGENT_FIX_08.md`.

## Tarefa 1: Validar helpers de compatibilidade Pydoll

### Arquivo

- `src/pydoll_mcp_server/browser/pydoll_compat.py`

### Correção da orientação anterior

Esta instrução foi corrigida após nova inspeção da Pydoll local. Na Pydoll, `Tab.current_url`, `Tab.title` e `WebElement.text` são async properties. Portanto a sintaxe correta é:

```python
await tab.current_url
await tab.title
await element.text
```

Não adicione parênteses a essas três chamadas.

### Testes obrigatórios

Criar testes unitários com fakes assim:

```python
class FakeTab:
    @property
    async def current_url(self):
        return 'https://example.test/'

    @property
    async def title(self):
        return 'Example'

class FakeElement:
    @property
    async def text(self):
        return 'Hello'
```

Esses testes devem provar:

- `get_tab_url(FakeTab()) == 'https://example.test/'`;
- `get_tab_title(FakeTab()) == 'Example'`;
- `get_element_text(FakeElement()) == 'Hello'`.

Também deve haver teste para `get_element_attribute`, confirmando que `get_attribute(name)` é síncrono.

## Tarefa 2: Montar MCP em `/mcp` e SSE em `/sse`

### Arquivo

- `src/pydoll_mcp_server/server.py`

### Correção obrigatória

- Montar `mcp.streamable_http_app()` em `/mcp`.
- Montar `mcp.sse_app()` em `/sse` se disponível.
- Não montar o app MCP inteiro em `/`.
- Manter `/health` separado.

### Testes obrigatórios

Os testes devem verificar as rotas reais do app, não apenas que uma chamada não retorna 404 por cair no mount raiz.

Verificar:

- existe `Mount('/mcp', ...)`;
- existe `Mount('/sse', ...)` se `FastMCP.sse_app` existe;
- não existe `Mount('', ...)` ou `Mount('/', ...)` para o app MCP;
- `mcp.http_app()` não aparece no código.

## Tarefa 3: Remover teste que engole falha real

### Arquivo

- `tests/contract/test_mcp_contract.py`

### Correção obrigatória

Remover padrão:

```python
try:
    ...
except RuntimeError:
    pass
```

Se o endpoint MCP precisa de payload válido para responder, construa payload válido ou teste apenas montagem e autenticação em camada ASGI. Não deixe exceção virar sucesso.

## Tarefa 4: Corrigir shadow traversal async

### Arquivo

- `src/pydoll_mcp_server/dom/deep_traversal.py`

### Correção obrigatória

Substituir:

```python
sr = el.get_shadow_root(timeout=2)
```

por:

```python
sr = await el.get_shadow_root(timeout=2)
```

Criar teste com fake element cujo `get_shadow_root` é async e cuja shadow root tem `query`. O teste deve falhar se `get_shadow_root` não for aguardado.

## Tarefa 5: Fechar ruff

Corrigir todos os itens de:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
```

Não desabilitar regra global para esconder o problema. Pode quebrar linhas longas, renomear variável não usada para `_strategy`, ajustar tests e trocar `pytest.raises(Exception)` por exceção específica.

## Tarefa 6: Smoke real

Criar marcador `browser_smoke` em `pyproject.toml`.

Criar teste opt-in que:

1. sobe página local ou usa fixture local;
2. lança browser headless;
3. navega;
4. chama `page_get_tree`;
5. interage com `element_id`;
6. fecha browser em cleanup.

Se não for possível rodar por limitação do ambiente, registrar em `progress/`:

- comando executado;
- erro completo;
- causa provável;
- próximo passo objetivo.

Não é aceitável deixar `pytest -m browser_smoke` com zero testes sem explicação.

## Critérios de aceite

Todos passam:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
```

E:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
```

seleciona pelo menos um teste. Se o teste for skipado, o motivo precisa ser técnico e específico.

## Erros a evitar

- Não testar fakes que reproduzem o erro antigo.
- Não montar MCP na raiz para fazer `/mcp` "parecer" existir.
- Não engolir `RuntimeError` em teste.
- Não tratar coroutine como objeto final.
- Não declarar pronto com `ruff` falhando.

## Definição de pronto

Este plano está pronto quando os helpers funcionam com fakes fiéis à Pydoll, as rotas MCP estão montadas nos paths planejados, `ruff` está verde e existe smoke real ou justificativa técnica objetiva.
