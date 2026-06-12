# PLAN_06: Busca e interação com elementos

## Objetivo

Implementar busca e interação com elementos por seletores técnicos e referências agent-friendly.

## Escopo

- `element_find`.
- `element_click`.
- `element_type`.
- `element_fill`.
- `element_get_text`.
- `element_get_attribute`.
- Reaquisição de elementos stale por hints.

## Fora de escopo

- Busca deep por iframes e shadow roots.
- Upload de arquivos.
- Screenshot de elemento.
- Drag and drop.

## Pré-requisitos

- `PLAN_05` concluído.
- Cache de elementos funcionando.
- Pydoll `find`, `query`, `click`, `type_text`, `clear`, `insert_text` e atributos validados.

## Critérios de início

- `page_get_tree` retorna `element_id`.
- Element cache invalida corretamente.
- Timeouts de espera existem.

## Tarefas detalhadas

1. Registrar início em `progress/`.
2. Criar `tools/elements.py`.
3. Definir `element_find` com:
   - `strategy=css|xpath|text|agent`;
   - selector ou critérios;
   - `timeout=15`;
   - `find_all=false`;
   - retorno limitado.
4. Para CSS/XPath, usar Pydoll `query` quando possível.
5. Para critérios agent-friendly, mapear para Pydoll `find` quando possível.
6. Implementar `element_click`:
   - resolver `element_id`;
   - validar visible/interactable quando possível;
   - scroll into view se necessário;
   - clicar;
   - aplicar wait pós-ação configurável.
7. Implementar `element_type` preservando UTF-8 e sem logar texto completo.
8. Implementar `element_fill` com clear antes de escrever.
9. Implementar getters de texto e atributo com truncation e redaction.
10. Implementar stale handling:
   - detectar falha;
   - tentar reaquisição por hints uma vez quando seguro;
   - retornar erro estruturado se falhar.
11. Adicionar locks mutantes por tab para click/type/fill.
12. Testar com fixtures de inputs, botões e Unicode.

## Critérios de aceite

- Elementos encontrados recebem `element_id`.
- `element_click` aguarda conclusão ou falha estruturada.
- `element_type` e `element_fill` preservam caracteres especiais.
- Stale element retorna hint claro.
- Logs não contêm valores completos de campos sensíveis.

## Definição de pronto

- Tools P0 de elementos funcionam em DOM principal.
- Tests de CSS, XPath, texto, click, type, fill e stale básico passam.
- Progress atualizado.

## Como testar

- Fixture com botão que altera texto.
- Fixture com input e textarea.
- Fixture com caracteres acentuados e CJK.
- Fixture que remove e recria elemento para stale handling.

## Riscos

- XPath em shadow root não será suportado no plano deep.
- Páginas SPA podem recriar nós entre find e click.
- Clickability pode ser heurística.

## Estratégia de recuperação se o agente for interrompido

- Rodar tests de elements.
- Conferir se locks mutantes estão cobrindo click/type/fill.
- Continuar pela primeira tool incompleta.

## Artefatos esperados

- `tools/elements.py`.
- Tests de elementos.
- Fixtures HTML.
- Registro em `progress/`.

## Notas para o próximo agente

Não implemente busca deep neste plano. Ela pertence ao `PLAN_07`.
