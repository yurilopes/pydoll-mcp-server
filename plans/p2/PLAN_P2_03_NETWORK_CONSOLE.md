# PLAN_P2_03: Network e console inspection

## Objetivo

Adicionar inspeção segura de network e console para agentes, usando APIs reais da Pydoll e redigindo dados sensíveis por padrão.

## Escopo

- Implementar `network_enable`, `network_disable`, `network_list`, `network_get_response`.
- Implementar `console_enable`, `console_disable`, `console_list` se viável.
- Limitar retenção por tab.
- Redigir headers, cookies, tokens e valores sensíveis.
- Criar fixtures locais para network e console.

## Fora de Escopo

- Interceptar, modificar ou bloquear requests.
- Expor Fetch domain para manipulação.
- Gravar HAR completo com payload sensível por padrão.
- Expor CDP livre.

## Pré-requisitos

- P2.1 concluído.
- P2.2 concluído ou documentado.
- Pydoll local consultada.

## Critérios de Início

- Confirmar no código local da Pydoll:
  - `Tab.enable_network_events`
  - `Tab.disable_network_events`
  - `Tab.get_network_logs`
  - `Tab.get_network_response_body`
  - `Tab.enable_runtime_events`
  - `Tab.on(Runtime.consoleAPICalled, callback)`

## Tarefas Detalhadas

1. Criar módulo de estado de inspeção por tab, por exemplo `browser/inspection.py`.
2. Network:
   - `network_enable(client_id, tab_id, max_events=1000)`
   - `network_disable(client_id, tab_id)`
   - `network_list(client_id, tab_id, filter_url="", limit=100, include_headers=false)`
   - `network_get_response(client_id, tab_id, request_id, max_bytes=65536, redact=true)`
3. `network_enable` deve chamar `await tab.enable_network_events()`.
4. `network_list` deve usar `await tab.get_network_logs(filter)` e normalizar:
   - `request_id`
   - `url`
   - `method`
   - `resource_type`
   - `timestamp`
   - `headers`, redigidos se incluídos
5. `network_get_response` deve:
   - exigir network habilitado;
   - usar `await tab.get_network_response_body(request_id)`;
   - limitar tamanho;
   - indicar `truncated`;
   - redigir padrões sensíveis quando `redact=true`.
6. Console:
   - habilitar Runtime domain com `await tab.enable_runtime_events()`;
   - registrar callback para `Runtime.consoleAPICalled`;
   - reter eventos por tab até `max_events`;
   - normalizar `level`, `text`, `timestamp`, `args_count`, `stack`;
   - redigir conteúdo sensível.
7. Se console não funcionar com a Pydoll instalada, tools devem retornar `UNSUPPORTED` estruturado.
8. Criar fixtures:
   - página que faz fetch local;
   - página que emite console.log, console.warn e console.error.
9. Criar testes unitários de redaction e retenção.
10. Criar smoke real com browser local para network e console quando estável.

## Critérios de Aceite

- Network é opt-in por tab.
- `network_list` não retorna headers sensíveis sem redaction.
- `network_get_response` limita tamanho e indica truncamento.
- Console funciona ou retorna `UNSUPPORTED` estruturado com documentação.
- Retenção não cresce sem limite.

## Definição de Pronto

- Agentes podem diagnosticar requests e console sem expor segredos.
- Falhas de suporte são explícitas e recuperáveis.

## Como Testar

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest tests\unit -q
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
```

## Riscos

- Network logs podem conter tokens em URL, headers ou payload.
- Response body pode ser binário ou grande demais.
- Console args podem conter objetos sensíveis.

## Estratégia de Recuperação

Se uma API Pydoll falhar, retornar `UNSUPPORTED` ou `EXECUTION_ERROR` estruturado. Não usar CDP livre como escape.

## Artefatos Esperados

- Tools registradas no MCP.
- Módulo de inspeção por tab.
- Fixtures locais.
- Testes de redaction, retenção e smoke.
- README atualizado.

## Notas Para o Próximo Agente

Não implemente request interception neste plano. Apenas observação.
