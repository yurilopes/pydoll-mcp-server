# PLAN_P2_05: Multi-cliente, metadata runtime e browser_attach seguro

## Objetivo

Endurecer isolamento multi-cliente e adicionar `browser_attach` seguro apenas para browsers lançados pelo servidor e pertencentes ao mesmo `client_id`.

## Escopo

- Stress test leve com múltiplos clientes.
- Metadata runtime mínima de browsers lançados.
- Cleanup de metadata stale.
- `browser_attach` por `browser_id` registrado.
- Bloqueio explícito de endpoint, porta, PID ou URL arbitrários.

## Fora de Escopo

- Attach ao Chrome pessoal do usuário.
- Attach a browser externo.
- Matar processo de browser no startup cleanup.
- Sincronização multi-host.

## Pré-requisitos

- P2.1 concluído.
- P2.2 concluído.
- P2.3 e P2.4 não precisam estar completos, mas não devem estar quebrados.

## Critérios de Início

- Ler `browser/registry.py`, `browser/models.py`, `browser/profiles.py` e `tools/browser.py`.
- Confirmar como a Pydoll guarda `_connection_port`, `_ws_address` e `_browser_process_manager._process`.

## Tarefas Detalhadas

1. Criar metadata runtime mínima em arquivo no runtime dir, por exemplo `runtime/browsers.json`.
2. Para cada browser lançado, persistir:
   - `browser_id`
   - `client_id`
   - `profile_id`
   - `profile_mode`
   - `headless`
   - `created_at`
   - `connection_port`, se disponível
   - `pid`, se disponível
   - `server_managed=true`
3. Não persistir:
   - bearer token
   - cookies
   - storage
   - paths completos se não forem necessários
   - ws endpoint completo se isso aumentar risco
4. `browser_attach(client_id, browser_id)`:
   - aceita somente `browser_id`;
   - busca metadata server-managed;
   - valida ownership por `client_id`;
   - recusa metadata stale;
   - recusa qualquer input de endpoint, porta, PID ou URL;
   - registra tabs descobertas se attach for viável.
5. Se attach pós restart não for confiável com segurança, retornar `UNSUPPORTED` estruturado e manter metadata para diagnostics.
6. Startup cleanup:
   - remover metadata stale;
   - limpar locks stale;
   - nunca matar processo de browser.
7. Stress test leve:
   - 2 clients;
   - cada client com recursos isolados;
   - garantir que `browser_list(client_a)` não mostra browsers de `client_b`;
   - tabs de clients diferentes não compartilham lock.

## Critérios de Aceite

- Um cliente não enxerga recursos de outro.
- `browser_attach` recusa `browser_id` de outro client.
- `browser_attach` recusa endpoint arbitrário porque nem aceita esse input.
- Startup cleanup não interfere no Chrome pessoal.
- Stress test multi-cliente passa.

## Definição de Pronto

- Isolamento multi-cliente tem teste dedicado.
- Attach é seguro, limitado e documentado.

## Como Testar

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest tests\unit -q
C:\Users\Yuri\anaconda3\python.exe -m pytest tests\integration -q
```

## Riscos

- Attach a processo errado.
- Vazar dados entre clients.
- Cleanup agressivo matar browser pessoal.

## Estratégia de Recuperação

Se attach real não for seguro, implementar apenas metadata, ownership checks e erro `UNSUPPORTED`. Não aceitar endpoint arbitrário como fallback.

## Artefatos Esperados

- Metadata runtime segura.
- Tool `browser_attach`.
- Tests multi-cliente.
- Docs atualizados.

## Notas Para o Próximo Agente

Segurança é mais importante que attach funcional. Um `UNSUPPORTED` bem documentado é aceitável se attach real não for seguro.
