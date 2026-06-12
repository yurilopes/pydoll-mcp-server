# PLAN_04: Navegação, waits robustos e semântica Playwright-like

## Objetivo

Criar wrappers de navegação e espera que tornem a Pydoll previsível para agentes MCP.

## Escopo

- `page_goto`.
- `page_reload`.
- `page_back`.
- `page_forward`.
- `page_wait`.
- Waits pós-ação que serão usados por tools futuras.
- Timeouts e cancelamento seguro.

## Fora de escopo

- Interação com elementos.
- Deep traversal.
- Network idle perfeito.
- Replay de navegação após crash.

## Pré-requisitos

- `PLAN_03` concluído.
- `tab_id` resolve para objeto Pydoll válido.
- Locks por tab implementados.

## Critérios de início

- `browser_launch` abre browser e tab inicial.
- `tab_list` retorna a tab do cliente.
- Tests de ownership passam.

## Tarefas detalhadas

1. Registrar início em `progress/`.
2. Criar `browser/waits.py` ou módulo equivalente.
3. Definir timeouts padrão:
   - goto 30s;
   - reload 30s;
   - back/forward 15s;
   - wait_for_selector 15s;
   - click pós-ação 10s para uso futuro.
4. Definir timeout máximo configurável, sugerido 120s.
5. Implementar wrapper de `Tab.go_to(url, timeout=30)`.
6. Implementar reload via `Tab.refresh` ou comando validado.
7. Implementar back e forward se Pydoll/CDP suportar. Se não suportar diretamente, registrar hipótese e usar JS history apenas se aceitável e documentado.
8. Implementar `page_wait` para:
   - load state;
   - selector;
   - text;
   - fixed delay controlado;
   - função futura para heurística pós-clique.
9. Padronizar erro de timeout.
10. Invalidar element cache após navegação, reload, back e forward.
11. Criar fixtures HTML locais simples.
12. Testar navegação para arquivo local ou servidor local de teste.

## Critérios de aceite

- `page_goto` retorna só após conclusão, falha ou timeout.
- Nenhuma navegação fica sem timeout.
- Element cache é invalidado em mudança de documento.
- Timeout retorna erro estruturado com recovery hint.
- Ações em tabs diferentes podem rodar em paralelo.

## Definição de pronto

- Tools de navegação P0 funcionam.
- Tests com página local passam.
- Back/forward estão implementados ou marcados como P1 com validação clara.

## Como testar

- Página local simples com título e texto.
- Página com atraso via script para testar timeout.
- Duas tabs navegando em paralelo para validar locks.

## Riscos

- Pydoll já aguarda load em `go_to`, mas a semântica pode não cobrir SPA.
- Network idle pode ser caro ou impreciso.
- Back/forward podem exigir CDP Page commands não encapsulados.

## Estratégia de recuperação se o agente for interrompido

- Rodar tests de navegação.
- Conferir cache de elementos após navegação.
- Retomar pela primeira tool incompleta.

## Artefatos esperados

- Módulo de waits.
- Tools de page navigation.
- Fixtures locais.
- Tests de timeout e navegação.
- Registro em `progress/`.

## Notas para o próximo agente

As tools de elementos devem reutilizar os waits deste plano, não criar loops próprios divergentes.
