# PLAN_P2: Capacidades avançadas, interoperabilidade e release experimental

## Objetivo

Depois que o P1 estiver pronto, expandir o servidor para recursos avançados de diagnóstico, interoperabilidade com clientes MCP, packaging e primeira release experimental.

## Escopo

- Compatibilidade adicional com `stdio`.
- Attach controlado a instâncias lançadas pelo servidor.
- Console e network inspection.
- Tracing e artifacts de diagnóstico.
- Persistência de registry leve para recuperação de processo.
- Testes multi-cliente mais fortes.
- Documentação final e release experimental.

## Fora de escopo

- Expor `execute_cdp_cmd` livre.
- Expor servidor em rede pública por padrão.
- Bypass de CAPTCHA, fraude ou evasão de segurança.
- Sincronização distribuída multi-host.

## Critérios de início

- P1 concluído.
- `pytest`, `ruff` e `mypy` passam.
- Browser smoke real passa em Windows.
- README documenta execução alpha.
- Não há bloqueadores em `docs/evaluation-2026-06-12.md`.

## Fase P2.1: Interoperabilidade de transportes e clientes

### Tarefas

1. Criar wrapper `stdio` opcional sem mudar o padrão HTTP.
2. Garantir que HTTP local continua padrão em README.
3. Criar exemplos de configuração para:
   - Codex;
   - OpenCode;
   - Claude Code.
4. Validar nomes de tools e schemas em cliente real ou MCP inspector.
5. Criar teste de contrato que lista tools por transporte quando possível.

### Aceite

- HTTP continua sendo caminho recomendado.
- `stdio` funciona como wrapper local, sem estado concorrente compartilhado fora do processo.
- Os três clientes prioritários têm exemplo documentado.

## Fase P2.2: Attach seguro a browsers do servidor

### Tarefas

1. Persistir metadados mínimos de browsers lançados pelo servidor:
   - `browser_id`;
   - `client_id`;
   - profile;
   - ws endpoint, se seguro;
   - created_at;
   - pid, se disponível.
2. Implementar `browser_attach` somente para instâncias lançadas pelo servidor.
3. Bloquear attach ao Chrome pessoal do usuário.
4. Validar ownership por `client_id`.
5. Criar cleanup de metadados stale.

### Aceite

- Cliente só anexa a browsers do próprio `client_id`.
- Attach a endpoint arbitrário falha.
- Metadados não vazam tokens nem paths sensíveis.

## Fase P2.3: Network e console inspection

### Tarefas

1. Validar APIs Pydoll para network logs:
   - `enable_network_events`;
   - `get_network_logs`;
   - response body quando seguro.
2. Implementar `network_enable`, `network_list`, `network_get_response`.
3. Redigir headers sensíveis:
   - Authorization;
   - Cookie;
   - Set-Cookie;
   - Proxy-Authorization.
4. Validar APIs Pydoll ou CDP helper específico para console logs.
5. Implementar `console_enable` e `console_list`, se viável.
6. Limitar retenção por tab, por exemplo 1000 eventos.

### Aceite

- Network inspection é opt-in por tab.
- Headers sensíveis são redigidos.
- Eventos têm `request_id`, url, method, status, resource_type e timing quando disponível.
- Console logs não travam a tab e têm limites de retenção.

## Fase P2.4: Tracing, diagnostics e artifacts

### Tarefas

1. Criar `diagnostics_snapshot`:
   - server status;
   - browsers do cliente;
   - tabs;
   - health;
   - últimos erros redigidos;
   - paths de artifacts.
2. Criar `trace_start` e `trace_stop` se Pydoll/CDP suportar tracing seguro.
3. Se tracing CDP for complexo, implementar trace leve próprio:
   - tool calls;
   - screenshots opcionais;
   - network resumido quando habilitado;
   - console resumido quando habilitado.
4. Empacotar artifacts em diretório permitido.
5. Criar política de retenção e limpeza.

### Aceite

- Diagnostics não inclui segredos.
- Trace leve ajuda a reproduzir falhas de agente.
- Artifacts têm TTL ou comando de cleanup.

## Fase P2.5: Robustez multi-cliente e recuperação de processo

### Tarefas

1. Testar dois clientes reais simultâneos contra HTTP.
2. Adicionar stress test leve:
   - 2 clientes;
   - 2 browsers;
   - 4 tabs;
   - navegação e observação paralelas.
3. Persistir registry leve para detecção de browsers órfãos.
4. Implementar startup cleanup:
   - detectar locks stale;
   - detectar metadata stale;
   - nunca matar processo de browser sem confirmar que foi criado pelo servidor.
5. Adicionar métricas simples por cliente.

### Aceite

- Clientes não veem recursos uns dos outros.
- Locks não ficam presos após close normal.
- Startup não interfere no Chrome pessoal do usuário.

## Fase P2.6: API polish e compatibilidade agent-friendly

### Tarefas

1. Revisar todos os schemas de input e output para consistência.
2. Garantir que toda tool retorna `success=true` ou erro estruturado com `error_code`.
3. Padronizar nomes:
   - `tab_id`;
   - `browser_id`;
   - `client_id`;
   - `timeout`.
4. Adicionar `schema_version` nos outputs principais.
5. Adicionar `capabilities` em `server_status`.
6. Criar documentação de exemplos de fluxos:
   - login simples;
   - formulário Unicode;
   - iframe;
   - shadow DOM;
   - download;
   - storage redigido.

### Aceite

- Um agente consegue escolher tools a partir de `server_status.capabilities`.
- Outputs são previsíveis e documentados.
- Exemplos não dependem de site externo.

## Fase P2.7: Packaging e release experimental

### Tarefas

1. Definir versão `0.1.0a1` ou `0.1.0`.
2. Criar `LICENSE` se ainda não existir.
3. Criar `CHANGELOG.md`.
4. Garantir que docs vendorizadas não tornam o pacote pesado demais.
5. Definir `MANIFEST.in` ou config Hatch se necessário.
6. Rodar build:
   - sdist;
   - wheel.
7. Instalar wheel em ambiente limpo.
8. Rodar smoke do pacote instalado.
9. Preparar GitHub release draft.
10. Não publicar sem aprovação humana.

### Aceite

- Wheel instala em ambiente limpo.
- Entry point `pydoll-mcp-server` funciona.
- README tem aviso alpha e segurança.
- Release checklist está completo.

## Fase P2.8: Documentação final de segurança

### Tarefas

1. Criar `docs/security.md` completo.
2. Documentar ameaças:
   - cliente local malicioso;
   - vazamento de token;
   - cookies e storage;
   - JS execution;
   - uploads/downloads;
   - browser profile reuse.
3. Documentar defaults seguros.
4. Documentar como rotacionar token.
5. Documentar como limpar runtime dir.

### Aceite

- Usuário entende riscos antes de habilitar tools sensíveis.
- Nenhum exemplo recomenda desabilitar auth fora de desenvolvimento.

## Definição de pronto do P2

- P1 continua verde.
- `stdio` opcional funciona ou está documentado como fora do release.
- `browser_attach` só aceita browsers lançados pelo servidor.
- Network e console inspection funcionam ou têm unsupported estruturado.
- Diagnostics snapshot existe.
- Stress multi-cliente básico passa.
- Wheel instala em ambiente limpo.
- Release experimental está pronto para revisão humana.

## Notas para recuperação

P2 deve ser executado em ordem. Se network, console ou tracing forem bloqueados por limitação real da Pydoll, registre como `UNSUPPORTED` em documentação e implemente erro estruturado em vez de workaround inseguro.
