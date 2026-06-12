# Prompt para segunda remediação do LLM desenvolvedor

Você está no repositório:

```text
C:\Users\Yuri\Documents\Git\pydoll-mcp-server
```

Use Python:

```text
C:\Users\Yuri\anaconda3\python.exe
```

Leia antes de editar:

```text
AGENTS.md
docs/evaluation-2026-06-12.md
docs/evaluation-2026-06-12-remediation-review.md
plans/remediation/README.md
plans/remediation/FIX_08_SECOND_PASS_VALIDATION.md
```

## Estado atual medido

Os comandos deram:

```text
pytest -q: 104 passed
ruff check .: falha com 17 erros
mypy src: success
pytest -m browser_smoke -q: 104 deselected
```

Ou seja: você melhorou o estado, mas ainda não terminou a remediação.

## O que você ainda fez errado

Correção importante: minha orientação anterior sobre `pydoll_compat.py` estava errada.

Você estava certo ao questionar. Na Pydoll local, `Tab.current_url`, `Tab.title` e `WebElement.text` são async properties. Portanto esta sintaxe está correta:

```python
await tab.current_url
await tab.title
await element.text
```

Não mude essas chamadas para `await tab.current_url()`, `await tab.title()` ou `await element.text()`.

O ajuste necessário é nos testes: os fakes precisam usar `@property async def`, não métodos async comuns.

Você também montou o app MCP em `Mount('/', app=mcp_app)`. Isso faz `/mcp` não retornar 404 por acidente, mas não cumpre a decisão de arquitetura. O planejado é:

```text
/mcp -> streamable_http_app
/sse -> sse_app quando disponível
/health -> health endpoint separado
```

Você deixou um teste que captura `RuntimeError` e passa. Isso é teste fraco. Um teste não pode transformar falha real em sucesso.

Você também chamou `get_shadow_root` sem `await` em deep traversal.

Por fim, você não criou smoke real. `pytest -m browser_smoke` seleciona zero testes.

## Sua tarefa

Execute somente:

```text
plans/remediation/FIX_08_SECOND_PASS_VALIDATION.md
```

Não comece P2.

## Regras obrigatórias

1. Para cada bug, crie teste que falharia antes da correção.
2. Os fakes precisam reproduzir a assinatura real da Pydoll local.
3. Não use `type: ignore` para esconder bug real.
4. Não desabilite regras do ruff para escapar.
5. Não capture exceção em teste e faça `pass`.
6. Não declare pronto com `ruff` falhando.
7. Não declare smoke real se `pytest -m browser_smoke` seleciona zero testes.

## Comandos finais obrigatórios

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
```

Registre o resultado em:

```text
progress/YYYY-MM-DD_AGENT_FIX_08.md
```

## Critério para dizer que terminou

Você só terminou se:

- `pytest -q` passa;
- `ruff check .` passa;
- `mypy src` passa;
- `pytest -m browser_smoke -q` seleciona pelo menos um teste;
- `pydoll_compat.py` mantém async properties da Pydoll sem `()`;
- `/mcp` e `/sse` estão montados explicitamente quando suportados;
- não há teste que engole `RuntimeError`;
- `get_shadow_root` é aguardado;
- progresso foi registrado.
