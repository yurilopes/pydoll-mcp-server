# PLAN_P1: Estabilização final do alpha local

## Objetivo

Transformar o estado pós FIX_11 em um alpha local confiável para uso por agentes, validando contrato MCP real, fluxo agent-friendly de observar e agir, deep traversal mínimo, concorrência, lifecycle, segurança de artifacts e documentação operacional.

Este plano substitui o P1 antigo. Os bloqueadores básicos foram tratados nos ciclos FIX_08 a FIX_11 e não devem ser reimplementados.

## Estado confirmado antes deste P1

- FIX_08 concluído.
- FIX_09 concluído.
- FIX_10 concluído.
- FIX_11 concluído.
- `pytest -q`: 129 passed no relato do FIX_11.
- `ruff check .`: All checks passed no relato do FIX_11.
- `mypy src`: Success no relato do FIX_11.
- `pytest -m browser_smoke -q`: 4 passed no relato do FIX_11.
- `/mcp` e `/sse` já estão montados.
- Auth bearer já existe.
- Propriedades assíncronas da Pydoll estão corretas:
  - `await tab.current_url`
  - `await tab.title`
  - `await element.text`
- `get_shadow_root` é método async:
  - `await element.get_shadow_root(...)`
- `page_get_tree` já retorna árvore real com browser smoke.
- `return_by_value=True` já foi aplicado nos retornos JS necessários.
- `validate_artifact_path` bloqueia traversal relativo.
- `cookies_set` já usa `tab_operation_lock` e `browser_operation_lock`.

## Escopo

- Validar o transporte HTTP MCP real em `127.0.0.1`.
- Validar `/health`, `/mcp`, `/sse` e bearer token em fluxo real.
- Validar listagem de tools por SDK MCP, MCP inspector ou equivalente.
- Garantir que `page_get_tree` permita agir diretamente por `element_id`.
- Garantir fill UTF-8 real por `element_id`.
- Implementar ou endurecer `page_get_tree_deep` e `element_find_deep` para iframe simples, nested iframe e shadow DOM aberto.
- Substituir ou complementar testes de locks por testes comportamentais.
- Validar profile lock, cleanup, artifacts, redaction e logs sem segredos.
- Atualizar README para execução alpha.
- Registrar progresso em `progress/YYYY-MM-DD_AGENT_PLAN_P1.md`.

## Fora de escopo

- Iniciar P2.
- Criar wrapper stdio.
- Publicar pacote no PyPI.
- Implementar tracing avançado.
- Implementar inspeção completa de network e console.
- Expor `execute_cdp_cmd` livre.
- Criar tools de comando de sistema operacional.
- Automatizar bypass de CAPTCHA, fraude ou evasão de segurança.

## Pré-requisitos

- Ler `AGENTS.md`.
- Ler `docs/evaluation-2026-06-12-fix11-review.md`.
- Ler `progress/2026-06-12_AGENT_FIX_11.md`.
- Usar Python em `C:\Users\Yuri\anaconda3\python.exe`.
- Não reverter mudanças existentes.
- Preservar UTF-8.
- Não alterar `await tab.current_url`, `await tab.title` ou `await element.text` para chamadas com parênteses.

## Critérios de início

- `plans/PLAN_P1.md` foi atualizado para este P1 rebaseado.
- `progress/YYYY-MM-DD_AGENT_PLAN_P1.md` foi criado ou atualizado.
- O agente registrou o baseline antes de alterar código funcional.

## P1.0: Baseline e inventário

### Tarefas

1. Registrar no progresso que FIX_08 a FIX_11 estão concluídos.
2. Rodar os gates iniciais:
   - `C:\Users\Yuri\anaconda3\python.exe -m pytest -q`
   - `C:\Users\Yuri\anaconda3\python.exe -m ruff check .`
   - `C:\Users\Yuri\anaconda3\python.exe -m mypy src`
   - `C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q`
3. Se algum gate falhar, registrar a falha e corrigir antes de avançar.
4. Criar ou atualizar `progress/YYYY-MM-DD_AGENT_PLAN_P1.md`.

### Aceite

- Estado inicial registrado.
- Gates iniciais executados ou falhas documentadas antes de correção.

## P1.1: Contrato MCP real

### Tarefas

1. Validar servidor HTTP real em `127.0.0.1` com token.
2. Validar `/health` sem token.
3. Validar `/mcp` com token.
4. Validar `/mcp` sem token falha.
5. Validar `/sse` se suportado pela versão instalada.
6. Listar tools usando MCP client, MCP inspector ou teste equivalente com o SDK MCP.

### Aceite

- Transporte real validado, não apenas `create_app()`.
- `/health` responde sem autenticação.
- `/mcp` exige bearer token.
- `/mcp` aceita bearer token válido no fluxo real.
- `/sse` está funcional ou documentado como limitação.
- A lista de tools contém as tools P0 esperadas.

## P1.2: Fluxo agent-friendly observe e act

### Tarefas

1. Criar teste real com browser:
   - abrir fixture local;
   - chamar `page_get_tree`;
   - escolher botão retornado pela árvore;
   - chamar `element_click` com `element_id`;
   - validar mudança no DOM.
2. Criar teste real com input UTF-8:
   - chamar `page_get_tree`;
   - localizar input;
   - chamar `element_fill` com texto acentuado, japonês, coreano ou chinês;
   - validar valor no DOM.
3. Melhorar resolução de `element_id` vindo de `page_get_tree` se necessário.
4. Melhorar fill para preservar UTF-8 se a API de digitação da Pydoll degradar caracteres.

### Aceite

- Um agente consegue observar árvore e agir por `element_id` sem chamar `element_find` antes.
- Fill por `element_id` preserva UTF-8 em browser real.
- IDs continuam invalidados por navegação ou reload.

## P1.3: Deep traversal mínimo real

### Tarefas

1. Validar fixtures de iframe simples, nested iframe e shadow DOM aberto.
2. Fazer `page_get_tree_deep` retornar elementos internos de iframe simples.
3. Fazer `page_get_tree_deep` retornar elementos internos de nested iframe.
4. Fazer `page_get_tree_deep` retornar elementos de shadow DOM aberto.
5. Fazer `element_find_deep` encontrar elementos nesses contextos.
6. Retornar `frame_path`, `shadow_path`, `partial` e `errors` de forma consistente.

### Aceite

- Testes passam para iframe simples.
- Testes passam para nested iframe.
- Testes passam para shadow DOM aberto.
- Erros parciais não derrubam a resposta inteira.

## P1.4: Hardening de concorrência e lifecycle

### Tarefas

1. Trocar ou complementar testes de lock baseados em `inspect.getsource` por testes comportamentais.
2. Usar fakes async e context managers instrumentados para provar que a seção crítica da tool ocorre dentro do lock.
3. Cobrir pelo menos:
   - `page_goto`;
   - `element_click`;
   - `storage_set`;
   - `cookies_set`.
4. Validar que tabs diferentes não compartilham lock.
5. Validar profile lock em launch concorrente com mesmo perfil persistente.
6. Validar cleanup de browser, tab e perfil temporário no close.

### Aceite

- Concorrência é provada por comportamento, não só por string no source.
- Mutação na mesma tab serializa.
- Mutação em tabs diferentes pode prosseguir sem lock compartilhado.
- Profile lock impede launch concorrente com mesmo perfil persistente.
- Cleanup remove estado runtime apropriado.

## P1.5: Segurança, redaction e artifacts

### Tarefas

1. Confirmar que `page_screenshot` e `element_screenshot` rejeitam path absoluto proibido e traversal relativo.
2. Confirmar que `upload_files` rejeita path fora da allowlist e traversal.
3. Validar downloads dentro do runtime dir ou documentar limitação se Pydoll não permitir controle seguro ainda.
4. Validar redaction em:
   - `cookies_get`;
   - `storage_get`;
   - `element_get_attribute` para nomes sensíveis.
5. Confirmar que logs não gravam bearer token, cookies, storage completo ou código JS completo.
6. Documentar claramente `js_evaluate` como tool sensível.

### Aceite

- Testes cobrem paths proibidos, traversal relativo, redaction e logs sensíveis.
- Downloads inseguros ficam bloqueados ou documentados como limitação.
- `js_evaluate` aparece no README como sensível.

## P1.6: README alpha e handoff

### Tarefas

1. Atualizar README com:
   - status alpha;
   - instalação local;
   - variável `PYDOLL_MCP_AUTH_TOKEN`;
   - comando para iniciar servidor;
   - endpoints `/health`, `/mcp` e `/sse`;
   - comandos de teste;
   - limitações conhecidas;
   - política de `js_evaluate` sensível;
   - aviso de segurança para cookies, storage, uploads e downloads.
2. Atualizar `progress/YYYY-MM-DD_AGENT_PLAN_P1.md` com resumo curto.

### Aceite

- Outro agente consegue rodar o alpha seguindo o README.
- Estado restante para P2 está claro.

## Gates finais obrigatórios

Rodar e registrar:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
```

## Definição de pronto

- Contrato MCP real foi validado.
- Observe e act por `element_id` vindo de `page_get_tree` funciona.
- `page_get_tree_deep` cobre iframe simples, nested iframe e shadow DOM aberto.
- `element_find_deep` encontra elementos em iframe simples, nested iframe e shadow DOM aberto.
- Locks têm testes comportamentais.
- Segurança de artifacts e redaction está coberta.
- README permite rodar o alpha.
- Progresso foi registrado.
- Todos os gates finais passam.

## Estratégia de recuperação

Se o agente for interrompido:

1. Leia este plano.
2. Leia o arquivo mais recente em `progress/`.
3. Rode `git status --short`.
4. Retome pela primeira fase sem aceite confirmado.
5. Não avance para P2 enquanto algum gate final estiver falhando.

## Artefatos esperados

- `plans/PLAN_P1.md` atualizado.
- Código e testes necessários para P1 restante.
- `README.md` atualizado.
- `progress/YYYY-MM-DD_AGENT_PLAN_P1.md` atualizado.

## Notas para o próximo agente

- Não reimplemente FIX_08 a FIX_11.
- Não altere a sintaxe das propriedades async da Pydoll.
- Use `return_by_value=True` quando `execute_script` precisar retornar objeto, array ou valor serializável.
- Use `Path.resolve(strict=False)` e `relative_to` para segurança de path.
- Não exponha `execute_cdp_cmd` livre.
