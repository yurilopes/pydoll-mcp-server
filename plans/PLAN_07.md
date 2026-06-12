# PLAN_07: Frames, iframes, OOPIFs e shadow DOM

## Objetivo

Implementar observação e busca robustas através de iframes, OOPIFs e shadow roots, incluindo caminhos completos para agentes.

## Escopo

- `page_get_tree_deep`.
- `element_find_deep`.
- Traversal recursivo de iframes.
- Traversal de shadow roots.
- Metadados `frame_path` e `shadow_path`.
- Estratégias rápidas versus robustas.

## Fora de escopo

- Bypass de CAPTCHA.
- Dependência em estruturas internas de user-agent shadow roots.
- Network inspection.

## Pré-requisitos

- `PLAN_06` concluído.
- Capacidade Pydoll para iframes e shadow roots validada no `PLAN_01`.
- Fixtures de iframe e shadow DOM disponíveis ou copiadas de exemplos locais, sem alterar Pydoll.

## Critérios de início

- `element_find` funciona no DOM principal.
- `page_get_tree` compacto funciona.
- Tests de elementos passam.

## Tarefas detalhadas

1. Registrar início em `progress/`.
2. Criar `dom/deep_traversal.py`.
3. Definir defaults:
   - `timeout=20`;
   - `max_depth=10`;
   - `max_nodes=1000`;
   - `include_shadow=true`;
   - `include_iframes=true`;
   - `include_closed_shadow=true` quando Pydoll suportar.
4. Implementar detecção de iframes no DOM principal.
5. Para iframe, usar modelo Pydoll de `WebElement` como escopo.
6. Para nested iframes, recursão com `frame_path`.
7. Para OOPIF, usar suporte Pydoll validado e registrar partial result se falhar.
8. Para shadow roots, usar `get_shadow_root` ou `find_shadow_roots`.
9. Dentro de shadow roots, usar CSS selector. Registrar limitação de XPath.
10. Retornar nós com:
   - `element_id`;
   - `frame_path`;
   - `shadow_path`;
   - selector hints;
   - xpath hints quando aplicável;
   - bounding box;
   - visible/enabled/clickable;
   - text;
   - role/aria/name.
11. Implementar `element_find_deep`.
12. Integrar cache de elementos com frame e shadow path.
13. Criar tests:
   - iframe simples;
   - nested iframe;
   - shadow DOM aberto;
   - closed shadow root se viável;
   - combinação iframe mais shadow root.

## Critérios de aceite

- `page_get_tree_deep` retorna árvore parcial mesmo se uma subárvore falhar.
- O output indica `partial=true` e erros por frame quando aplicável.
- `element_find_deep` encontra elemento dentro de iframe simples.
- Shadow root aberto funciona.
- Limitações de closed shadow e OOPIF estão testadas ou documentadas.

## Definição de pronto

- Tools P1 deep funcionam com fixtures locais.
- Tests principais passam.
- Documentação das limitações foi atualizada.

## Como testar

- Reusar fixtures de `tests/integration/pages` da Pydoll como referência, copiando apenas se necessário para este projeto.
- Não depender de sites externos.
- Incluir timeout curto para traversal caro.

## Riscos

- OOPIF pode ser difícil de reproduzir localmente.
- Closed shadow root pode variar por versão Chromium.
- Traversal profundo pode gerar outputs grandes.

## Estratégia de recuperação se o agente for interrompido

- Conferir tests de iframe antes de shadow.
- Se OOPIF falhar, marcar como hipótese a validar e manter partial result.
- Retomar pelo traversal que tem fixture local mais simples.

## Artefatos esperados

- `dom/deep_traversal.py`.
- Tools deep.
- Fixtures de iframe e shadow.
- Tests deep.
- Registro em `progress/`.

## Notas para o próximo agente

Não use `execute_cdp_cmd` livre para resolver lacunas. Crie helpers internos bem delimitados.
