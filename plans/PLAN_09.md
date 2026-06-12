# PLAN_09: Resiliência, health checks, timeouts e recovery

## Objetivo

Fortalecer o servidor para detectar falhas, relatar diagnóstico estruturado e recuperar abas ou browsers de forma conservadora.

## Escopo

- Health check de servidor, browser e tab.
- Detecção de tab travada.
- Timeouts por operação.
- Cancelamento seguro.
- Retry com backoff quando apropriado.
- `tab_recover`.
- Erros estruturados e recovery hints.

## Fora de escopo

- Recriação destrutiva automática sem confirmação.
- Persistência complexa de estado de formulário.
- Cluster ou multi-processo.

## Pré-requisitos

- `PLAN_08` concluído.
- Tools principais têm timeouts.
- Registry conhece estado de browsers e tabs.

## Critérios de início

- Tests P0 e P1 principais passam.
- Existe modelo único de erro.
- Logs estruturados mínimos existem.

## Tarefas detalhadas

1. Registrar início em `progress/`.
2. Criar `recovery/health.py`, `recovery/recover.py` e `recovery/errors.py` se ainda não existirem.
3. Implementar health de servidor:
   - uptime;
   - config;
   - auth;
   - event loop;
   - contadores.
4. Implementar health de browser:
   - processo vivo;
   - CDP responde;
   - versão disponível.
5. Implementar health de tab:
   - comando barato com timeout curto;
   - url e título se possível;
   - estado `healthy`, `degraded`, `unhealthy`, `closed`.
6. Implementar timeout wrapper padronizado.
7. Implementar cancelamento seguro com cleanup de callbacks quando aplicável.
8. Implementar retry com backoff apenas para erros transitórios definidos.
9. Implementar recuperação conservadora:
   - diagnosticar;
   - tentar reload uma vez se responder minimamente;
   - marcar unhealthy se falhar;
   - nunca recriar automaticamente.
10. Implementar `tab_recover` explícito:
   - `mode=reload`;
   - `mode=recreate`;
   - `force=true` exigido para recriar.
11. Criar tests de timeout, erro estruturado e tab unhealthy simulada.

## Critérios de aceite

- `health_check` distingue servidor, browser e tab quando solicitado.
- Timeouts retornam erro consistente.
- Aba travada recebe diagnóstico e reload conservador quando possível.
- Recriação só ocorre por tool explícita.
- Recovery reporta o que tentou e estado final.

## Definição de pronto

- Tests de recovery passam.
- Todas as tools P0 usam timeout wrapper padronizado.
- Progress atualizado.

## Como testar

- Simular command timeout com mock.
- Simular tab fechada.
- Simular reload falhando.
- Testar `tab_recover` com `force=false` e `force=true`.

## Riscos

- Distinguir tab travada de página lenta pode ser impreciso.
- Cancelar comandos CDP pode deixar callback pendente.
- Recreate perde estado do agente.

## Estratégia de recuperação se o agente for interrompido

- Rodar tests de erro estruturado.
- Conferir se alguma tool ficou sem timeout.
- Retomar pelos wrappers comuns antes das tools específicas.

## Artefatos esperados

- Módulos de recovery.
- `tab_recover`.
- Tests de timeout e health.
- Registro em `progress/`.

## Notas para o próximo agente

Segurança e logging do próximo plano dependem dos campos estruturados deste plano.
