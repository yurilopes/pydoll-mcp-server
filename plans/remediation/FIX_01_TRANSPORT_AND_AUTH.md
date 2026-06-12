# FIX_01: Transporte MCP HTTP e autenticação real

## Problema

`src/pydoll_mcp_server/server.py` usa `mcp.http_app()`, mas a versão instalada do MCP SDK expõe `streamable_http_app()` e `sse_app()`. Isso indica que `create_app()` pode falhar em runtime.

Além disso, os testes de contrato atuais não exercitam a aplicação ASGI real nem validam os endpoints MCP.

## Arquivos envolvidos

- `src/pydoll_mcp_server/server.py`
- `src/pydoll_mcp_server/auth.py`
- `src/pydoll_mcp_server/cli.py`
- `tests/contract/test_mcp_contract.py`
- `tests/unit/test_auth.py`
- `README.md`

## Objetivo

Garantir que o servidor HTTP local inicia com o SDK MCP instalado, monta `/mcp` e `/sse` quando disponível, exige bearer token por padrão e tem testes que validam a aplicação ASGI.

## Tarefas detalhadas

1. Confirmar a API instalada do FastMCP:

```powershell
@'
from mcp.server.fastmcp import FastMCP
m = FastMCP("probe")
print(hasattr(m, "streamable_http_app"))
print(hasattr(m, "sse_app"))
print(hasattr(m, "http_app"))
'@ | C:\Users\Yuri\anaconda3\python.exe -
```

2. Em `server.py`, trocar o mount principal:
   - usar `mcp.streamable_http_app()` em `/mcp`;
   - usar `mcp.sse_app()` em `/sse` se existir;
   - se `sse_app()` não existir, não criar rota falsa. Registrar em status que SSE está indisponível.
3. Ajustar `create_app()` para não avaliar config antes de testes poderem injetar env vars.
4. Criar teste que chama `create_app()` com `PYDOLL_MCP_AUTH_TOKEN=test-token`.
5. Criar teste com `starlette.testclient.TestClient` para `GET /health`.
6. Criar teste que acessa endpoint MCP sem token e espera falha de autenticação.
7. Criar teste que confirma `Authorization: Bearer test-token` é aceito.
8. Revisar `BearerTokenBackend`:
   - não usar token truncado como `client_id` operacional;
   - autenticação e identidade de cliente são conceitos separados;
   - o `client_id` deve continuar vindo dos inputs das tools.
9. Atualizar README com endpoints corretos:
   - `/mcp`: Streamable HTTP;
   - `/sse`: SSE quando disponível;
   - `/health`: health HTTP simples.

## Critérios de aceite

- `create_app()` funciona com token configurado.
- `/health` responde sem exigir token e sem vazar segredo.
- Rotas MCP exigem token quando auth está habilitada.
- `/mcp` usa `streamable_http_app()`.
- `/sse` existe ou está documentado como indisponível com motivo técnico.
- Não existe uso de `mcp.http_app()`.

## Como testar

```powershell
$env:PYDOLL_MCP_AUTH_TOKEN = "test-token"
C:\Users\Yuri\anaconda3\python.exe -m pytest tests\contract tests\unit\test_auth.py -q
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
Remove-Item Env:PYDOLL_MCP_AUTH_TOKEN -ErrorAction SilentlyContinue
```

## Erros a evitar

- Não marque como concluído apenas porque `from pydoll_mcp_server.server import mcp` funciona.
- Não desabilite auth para fazer teste passar.
- Não monte rota SSE falsa.
- Não use o token como `client_id` de recursos.

## Definição de pronto

Este plano está pronto quando o servidor ASGI é construído em teste, a rota `/mcp` existe com a API correta do SDK e a autenticação falha fechada por padrão.
