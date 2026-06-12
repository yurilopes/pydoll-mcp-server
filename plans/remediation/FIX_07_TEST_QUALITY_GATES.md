# FIX_07: Gates de qualidade, smoke real e reavaliação correta

## Problema

O agente anterior declarou "implementação completa" com 87 testes verdes, mas os testes eram superficiais para os riscos centrais. `ruff` e `mypy` falham, e não há smoke real de browser, nem validação de `create_app()` ou fluxo `page_get_tree` para `element_click`.

## Arquivos envolvidos

- `pyproject.toml`
- `tests/`
- `README.md`
- `progress/`
- todos os módulos em `src/pydoll_mcp_server/`

## Objetivo

Impedir que o projeto volte a ser marcado como pronto sem validação real de transporte, Pydoll, browser, segurança e qualidade estática.

## Tarefas detalhadas

1. Corrigir todos os problemas de `ruff check .`.
2. Corrigir todos os problemas de `mypy src`.
3. Adicionar tests obrigatórios:
   - `create_app()` com token;
   - mount `/mcp`;
   - `/sse` quando disponível;
   - `browser_launch` com mock que valida API real de `ChromiumOptions`;
   - helpers async de Pydoll;
   - `page_get_tree` para `element_click`;
   - path allowlist seguro;
   - locks de tab e profile.
4. Criar smoke real marcado como `browser_smoke`:
   - lança browser headless;
   - navega para fixture local;
   - chama `page_get_tree`;
   - clica elemento por `element_id`;
   - preenche input Unicode;
   - tira screenshot em artifacts;
   - fecha browser.
5. O smoke pode ser opt-in, mas precisa estar documentado e rodar no ambiente Windows.
6. Atualizar README:
   - comandos de teste;
   - comandos de lint;
   - comando de smoke;
   - critérios antes de declarar pronto.
7. Atualizar `progress/` ao fim de cada plano de remediação.

## Critérios de aceite

Todos passam:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
```

Smoke real documentado:

```powershell
$env:PYDOLL_MCP_AUTH_TOKEN = "test-token"
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
Remove-Item Env:PYDOLL_MCP_AUTH_TOKEN -ErrorAction SilentlyContinue
```

## Como se reavaliar corretamente

1. Não leia apenas `progress/`.
2. Rode os comandos.
3. Se um comando falhar, o plano não está pronto.
4. Se um teste só importa módulo, ele não valida comportamento.
5. Para cada bug corrigido, crie um teste que falharia antes.
6. Valide contra a Pydoll local, não contra suposições.
7. Diferencie scaffold, mock test e browser real.

## Erros a evitar

- Não declarar "P1/P2 completo" sem smoke real.
- Não usar `type: ignore` para esconder integração errada.
- Não relaxar ruff ou mypy para passar.
- Não remover testes difíceis. Corrija a implementação.

## Definição de pronto

Este plano está pronto quando a suíte padrão, ruff, mypy e o smoke real documentado validam o comportamento central do servidor.
