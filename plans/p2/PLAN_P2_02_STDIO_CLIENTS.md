# PLAN_P2_02: Transporte stdio e exemplos de clientes

## Objetivo

Adicionar transporte `stdio` opcional para uso local com Codex, OpenCode e Claude Code, preservando HTTP local como caminho recomendado e sem alterar o modelo de segurança do servidor HTTP.

## Escopo

- Adicionar comando CLI para `stdio`.
- Manter comando HTTP existente como padrão.
- Documentar configuração para Codex, OpenCode e Claude Code.
- Validar listagem de tools por `stdio` quando possível.

## Fora de Escopo

- Remover HTTP.
- Compartilhar estado entre processo HTTP e processo stdio.
- Criar daemon multi-processo.
- Criar autenticação bearer para `stdio`.

## Pré-requisitos

- P2.1 concluído.
- FastMCP local validado com suporte a `run("stdio")`.

## Critérios de Início

- Ler `src/pydoll_mcp_server/cli.py`.
- Ler a API instalada em `mcp.server.fastmcp.server.FastMCP.run`.
- Confirmar que HTTP ainda inicia via `pydoll-mcp-server --host 127.0.0.1 --port 8765`.

## Tarefas Detalhadas

1. Adicionar opção CLI explícita:
   - `pydoll-mcp-server --transport http`
   - `pydoll-mcp-server --transport stdio`
2. Default deve continuar sendo `http`.
3. Para `stdio`, chamar o FastMCP existente com transporte `stdio`.
4. Em `stdio`, não exigir `PYDOLL_MCP_AUTH_TOKEN` por padrão, pois o transporte é processo local controlado pelo cliente.
5. Em HTTP, manter bearer token obrigatório por padrão.
6. Documentar exemplos em `docs/clients/`:
   - `codex.md`
   - `opencode.md`
   - `claude-code.md`
7. Cada exemplo deve mostrar:
   - comando Python usando `C:\Users\Yuri\anaconda3\python.exe` para desenvolvimento local;
   - comando portátil via entry point `pydoll-mcp-server`;
   - variáveis de ambiente necessárias;
   - nota de segurança sobre perfil persistente por `client_id`.
8. Adicionar teste de contrato para listar tools com `stdio` se o SDK permitir sem subprocesso frágil.
9. Se teste real de stdio for instável no Windows, criar teste de unidade que valida CLI dispatch e documentar a limitação.

## Critérios de Aceite

- HTTP continua funcionando como antes.
- `--transport stdio` inicia transporte local sem tentar bind de porta.
- Exemplos para Codex, OpenCode e Claude Code existem.
- Catálogo de tools via stdio é validado por teste ou limitação documentada.

## Definição de Pronto

- Usuário consegue configurar um cliente MCP local via stdio a partir da documentação.
- P2 pode continuar para network e console sem mexer de novo no transporte.

## Como Testar

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest tests\contract -q
C:\Users\Yuri\anaconda3\python.exe -m pytest tests\unit -q
```

## Riscos

- `stdio` pode bloquear se um teste abrir processo sem encerrar.
- Auth HTTP pode ser enfraquecida por engano se a lógica de config for compartilhada de forma incorreta.

## Estratégia de Recuperação

Se `stdio` real via subprocesso for difícil de testar com segurança, manter implementação CLI e validar com teste unitário. Registrar a limitação em `progress/` e README.

## Artefatos Esperados

- CLI com transporte selecionável.
- Docs de clientes em `docs/clients/`.
- Testes de contrato ou unidade.
- README atualizado.

## Notas Para o Próximo Agente

Não transforme `stdio` no default. O default do ciclo P2 continua HTTP local.
