# PLAN_02: Arquitetura MCP, configuração Python e servidor mínimo

## Objetivo

Criar o esqueleto Python do projeto e um servidor MCP mínimo por HTTP local, sem implementar automação de navegador além de health básico.

## Escopo

- Criar `pyproject.toml`.
- Criar pacote em `src/pydoll_mcp_server/`.
- Criar entrypoint HTTP local com FastMCP.
- Criar configuração com Pydantic.
- Implementar autenticação local por bearer token.
- Implementar `health_check` e `server_status` mínimos.

## Fora de escopo

- Lançar browser Pydoll.
- Criar tools de tabs, navegação ou elementos.
- Implementar storage, cookies ou JS execution.

## Pré-requisitos

- `PLAN_01` concluído.
- Matriz de capacidades Pydoll disponível.
- Python local via `C:\Users\Yuri\anaconda3\python.exe`.

## Critérios de início

- `progress/` indica `PLAN_01` concluído.
- `docs/pydoll-capabilities.md` existe.
- `git status --short` revisado.

## Tarefas detalhadas

1. Registrar início em `progress/`.
2. Criar estrutura:
   - `src/pydoll_mcp_server/__init__.py`;
   - `src/pydoll_mcp_server/server.py`;
   - `src/pydoll_mcp_server/config.py`;
   - `src/pydoll_mcp_server/auth.py`;
   - `src/pydoll_mcp_server/logging.py`;
   - `src/pydoll_mcp_server/tools/health.py`;
   - `tests/`.
3. Criar `pyproject.toml` com:
   - Python `>=3.10`;
   - `mcp[cli]`;
   - `pydoll-python`;
   - `pydantic>=2`;
   - `starlette`;
   - `uvicorn`;
   - dependências dev: `pytest`, `pytest-asyncio`, `ruff`, `mypy`.
4. Definir config:
   - host padrão `127.0.0.1`;
   - porta padrão `8765`;
   - transportes `streamable_http` e `sse`;
   - `PYDOLL_MCP_AUTH_TOKEN` obrigatório;
   - `PYDOLL_MCP_ALLOW_NO_AUTH=true` apenas para desenvolvimento;
   - diretório runtime por SO.
5. Criar app FastMCP com `/mcp` e, se viável, `/sse`.
6. Implementar middleware ou hook de autenticação para bearer token.
7. Implementar `health_check`.
8. Implementar `server_status` sem expor outros clientes.
9. Criar testes mínimos de config e health.
10. Atualizar README com comando de execução local.
11. Registrar progresso e próximos passos.

## Critérios de aceite

- O servidor inicia localmente em `127.0.0.1`.
- Sem token, o servidor recusa iniciar ou recusa requests, conforme decisão implementada.
- `health_check` responde sem lançar browser.
- Testes mínimos passam.
- Não há tools de browser implementadas.

## Definição de pronto

- `pyproject.toml` existe.
- Estrutura `src/` existe.
- Health e status mínimos funcionam.
- README contém comando inicial.
- `progress/` indica conclusão.

## Como testar

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest
```

Se dependências ainda não estiverem instaladas, documentar no progresso o comando planejado, sem improvisar instalação global.

## Riscos

- FastMCP pode exigir configuração específica para montar Streamable HTTP e SSE no mesmo processo.
- Clientes podem variar no suporte a Streamable HTTP.
- Auth no transporte MCP pode exigir middleware ASGI em vez de hooks FastMCP.

## Estratégia de recuperação se o agente for interrompido

- Verificar `pyproject.toml`.
- Verificar se `src/pydoll_mcp_server/server.py` inicia.
- Rodar testes de health.
- Continuar da primeira tarefa sem arquivo correspondente.

## Artefatos esperados

- `pyproject.toml`.
- Pacote em `src/pydoll_mcp_server/`.
- Tests mínimos.
- Atualização no README.
- Registro em `progress/`.

## Notas para o próximo agente

Só avance para browser lifecycle depois que o servidor mínimo estiver testável.
