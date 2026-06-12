# Entrevista e decisões

Data: 2026-06-12.

## Respostas de Yuri

### Transporte MCP

Pergunta: O servidor MCP deve ser pensado primeiro para uso local via stdio, HTTP/SSE ou ambos?

Resposta inicial: stdio.

Decisão revisada: usar HTTP/SSE por padrão para facilitar suporte a múltiplos clientes. Streamable HTTP em `/mcp`, SSE em `/sse` quando viável, bind seguro em `127.0.0.1`.

### Clientes prioritários

Resposta: Codex, OpenCode e Claude Code.

### Múltiplos clientes

Resposta: deve suportar múltiplos clientes MCP simultâneos.

### Modelo de navegador

Resposta: lançar nova instância de navegador controlado pela Pydoll. Instâncias lançadas pelo MCP server devem ser descobertas por agentes, mas cada agente só deve ver suas próprias instâncias. Não deve haver interferência com o Chrome normal do usuário.

### Perfis

Resposta: lançamento por cliente deve usar perfil de navegação padrão persistido. O cliente pode pedir perfil temporário ou criar perfil novo persistente.

Decisão complementar: perfil persistente padrão por `client_id`; perfis nomeados por `profile_id`; locks exclusivos por perfil.

### Headless

Resposta: navegador visível por padrão, headless configurável pelo cliente.

### JavaScript

Resposta: `js_evaluate` deve existir, mas ser sensível.

Políticas:

- exigir `tab_id`;
- timeout obrigatório e curto por padrão;
- limitar tamanho do código e do resultado;
- retornar JSON serializável;
- não registrar código completo nem resultado completo por padrão;
- redigir padrões sensíveis;
- separar `js_evaluate_readonly` e `js_evaluate`;
- bloquear ou alertar padrões perigosos;
- permitir desabilitar em modo seguro;
- registrar auditoria resumida.

### Cookies e storage

Resposta: `cookies_get/set` e `storage_get/set` devem entrar no planejamento.

### Upload e download

Resposta: devem ser planejados agora.

### Nomes de tools

Resposta: API própria orientada a agentes.

### Árvores de página

Resposta: `page_get_tree` deve ser compacta e limitada por padrão, com opção explícita para mais profundidade.

### Element IDs

Resposta: elementos devem ter IDs reutilizáveis entre chamadas, com validade controlada e mecanismo de invalidação.

### Traversal profundo

Resposta: deve existir tool separada como caminho recomendado e também opção dentro das tools normais.

### Timeouts padrão

- `goto`: 30s.
- `click`: 10s.
- `wait_for_selector`: 15s.
- `page_get_tree_deep`: 20s.

Todos devem aceitar override por chamada, com máximos configuráveis. Nenhuma operação deve ficar sem timeout.

### Aba travada

Resposta: diagnosticar e tentar recuperação conservadora.

Regra:

1. Detectar e reportar diagnóstico estruturado.
2. Tentar reload uma vez, se a aba ainda responder minimamente.
3. Se falhar, marcar a aba como unhealthy.
4. Não recriar automaticamente por padrão.
5. Recriação só como ação explícita, por exemplo `tab_recover` ou `tab_recreate` com `force=true`.

### QUESTIONS.md

Resposta: criar este arquivo.

### Ordem de execução

Resposta: DeepSeek v4 Pro deve executar plano por plano em sequência estrita.

### Stack

Resposta: recomendar stack Python e portável. O projeto deve rodar em Windows, Unix e macOS com mínimo ruído. Será distribuído via pip e release no GitHub.

## Decisões adicionais fechadas

- Autenticação local: bearer token obrigatório por padrão.
- Diretório runtime: app data do usuário por SO, fora do repositório.
- Identidade: `client_id` explícito.

## Pendências

Não há pendências bloqueantes para iniciar `PLAN_01`.

Pendências técnicas devem ser validadas no plano correspondente:

- versão exata do MCP Python SDK a fixar no `pyproject.toml`;
- melhor forma de expor SSE e Streamable HTTP no mesmo processo com FastMCP;
- comandos CDP específicos da Pydoll para viewport, storage e network inspection;
- limites finais para tamanho de árvore, resultado JS e retenção de cache de elementos.
