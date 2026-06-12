# PLAN_05: Observação de página, árvores, UTF-8 e extração semântica

## Objetivo

Implementar tools para observar páginas, extrair texto e construir árvores compactas com IDs de elementos reutilizáveis.

## Escopo

- `page_get_text`.
- `page_get_tree`.
- Cache de elementos e invalidação.
- UTF-8 e textos internacionais.
- Metadados agent-friendly.

## Fora de escopo

- Deep traversal por iframes e shadow roots.
- Interação mutante com elementos.
- Accessibility tree real se Pydoll não oferecer suporte validado.

## Pré-requisitos

- `PLAN_04` concluído.
- Element cache invalida em navegação.
- Matriz de capacidades indica como obter DOM, texto, atributos e bounds.

## Critérios de início

- `page_goto` funciona com página local.
- Existe registry de tabs e locks.
- Existe modelo de erro estruturado.

## Tarefas detalhadas

1. Registrar início em `progress/`.
2. Criar módulos:
   - `dom/tree.py`;
   - `dom/element_cache.py`;
   - `dom/serialization.py`;
   - `tools/observation.py`.
3. Definir defaults:
   - `page_get_tree`: `max_depth=6`, `max_nodes=300`;
   - `page_get_text`: `max_chars=20000`;
   - truncation sempre indicado.
4. Definir node shape:
   - `element_id`;
   - tag;
   - role ou aria quando disponível;
   - name ou label;
   - text curto;
   - attributes filtrados;
   - selector hints;
   - xpath hints;
   - bounding box;
   - visible, enabled, clickable quando viável;
   - children.
5. Gerar `element_id` para nós interativos e nós relevantes.
6. Guardar no cache:
   - objeto Pydoll quando válido;
   - tab_id;
   - frame path;
   - shadow path;
   - hints de reaquisição;
   - geração do documento.
7. Implementar `page_get_text` preservando UTF-8.
8. Criar fixtures com acentos, chinês, japonês, coreano e emojis se necessário para validar Unicode. O arquivo pode conter Unicode real.
9. Criar tests de truncation e limites.
10. Documentar que `page_get_tree` é compacto e não atravessa OOPIF ou shadow deep por padrão.

## Critérios de aceite

- Texto UTF-8 é preservado.
- Tree retorna JSON serializável.
- Limites de profundidade e nós são respeitados.
- `element_id` pode ser usado por tools futuras até invalidação.
- Outputs não incluem valores sensíveis completos de inputs por padrão.

## Definição de pronto

- `page_get_text` e `page_get_tree` funcionam em fixtures locais.
- Tests de Unicode e truncation passam.
- Cache de elementos tem tests unitários.

## Como testar

- Fixture HTML com múltiplos idiomas.
- Fixture com muitos nós para validar truncation.
- Navegar, obter tree, navegar de novo e verificar invalidação.

## Riscos

- Bounds e clickability podem exigir JS ou CDP adicional.
- Accessibility-like tree pode ser incompleta.
- Cache de objetos Pydoll pode ficar stale em SPAs.

## Estratégia de recuperação se o agente for interrompido

- Conferir tests de cache.
- Verificar se a geração de documento está sendo incrementada.
- Continuar pela serialização da tree.

## Artefatos esperados

- Módulos DOM.
- Tools de observação.
- Fixtures Unicode.
- Tests de tree e texto.
- Registro em `progress/`.

## Notas para o próximo agente

As tools de interação dependem da qualidade do `element_id` e dos hints deste plano.
