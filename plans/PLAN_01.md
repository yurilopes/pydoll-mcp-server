# PLAN_01: Levantamento da Pydoll, documentação local e validação de capacidades

## Objetivo

Validar as capacidades reais da Pydoll que serão usadas pelo MCP server e garantir que a documentação local está disponível, rastreada e consultável.

## Escopo

- Conferir documentação vendorizada em `references/pydoll-docs/`.
- Conferir código local da Pydoll em `C:\Users\Yuri\Documents\Git\pydoll`.
- Registrar matriz de capacidades verificadas, hipóteses e lacunas.
- Criar ou atualizar documento de levantamento técnico, por exemplo `docs/pydoll-capabilities.md`.

## Fora de escopo

- Criar código do servidor MCP.
- Instalar dependências.
- Alterar o repositório local da Pydoll.
- Baixar documentação externa se a documentação local for suficiente.

## Pré-requisitos

- `PLAN.md` lido.
- `AGENTS.md` lido.
- Documentação em `references/pydoll-docs/` existente.
- Repositório Pydoll local acessível.

## Critérios de início

- `git status --short` revisado.
- Último progresso em `progress/` revisado, se existir.
- Confirmado que `references/pydoll-docs/SOURCE.md` existe.

## Tarefas detalhadas

1. Registrar em `progress/` que o `PLAN_01` foi iniciado.
2. Conferir `references/pydoll-docs/SOURCE.md`.
3. Verificar no repositório Pydoll:
   - `pydoll/browser/tab.py`;
   - `pydoll/browser/chromium/base.py`;
   - `pydoll/elements/web_element.py`;
   - `pydoll/elements/mixins/find_elements_mixin.py`;
   - docs de iframe, shadow DOM, screenshots, cookies, storage, downloads e event system.
4. Criar matriz com colunas:
   - capacidade;
   - API Pydoll verificada;
   - arquivo ou doc de origem;
   - status: verificada, hipótese a validar ou não suportada;
   - impacto no MCP;
   - plano que implementará.
5. Registrar como verificadas, se confirmadas no código:
   - `Tab.go_to`;
   - eventos de load por Page domain;
   - `Tab.execute_script`;
   - iframes como `WebElement`;
   - shadow roots inclusive closed via CDP;
   - browser contexts;
   - tabs;
   - cookies;
   - screenshots;
   - downloads;
   - user data dir;
   - user-agent override.
6. Registrar hipóteses a validar:
   - viewport por CDP ou helper Pydoll;
   - storage local/session via commands;
   - network e console inspection;
   - comportamento real de OOPIF em fixtures locais.
7. Atualizar `QUESTIONS.md` se surgir uma pendência de produto.
8. Atualizar `progress/` com resultado e próximo plano.

## Critérios de aceite

- Documento de capacidades criado em `docs/pydoll-capabilities.md` ou nome equivalente.
- Cada capacidade usada por planos P0 tem uma fonte local citada.
- Hipóteses não verificadas estão marcadas claramente.
- Nenhuma capacidade foi inventada sem fonte.

## Definição de pronto

- O próximo agente consegue abrir o documento de capacidades e saber quais APIs Pydoll usar ou validar.
- `progress/` indica que `PLAN_01` foi concluído.
- Nenhum código de servidor MCP foi implementado.

## Como testar

- Conferir que os links e caminhos citados existem.
- Rodar apenas comandos de leitura, como `rg`, `Get-Content` e `git status`.
- Não executar browser ainda, exceto se o agente registrar justificativa e for necessário para validar uma hipótese específica.

## Riscos

- Documentação local pode estar divergente do código.
- APIs Pydoll podem ser privadas ou instáveis.
- Recursos de shadow DOM e OOPIF podem depender de versão do Chromium.

## Estratégia de recuperação se o agente for interrompido

- Ler o documento de capacidades parcialmente criado.
- Conferir a última seção preenchida.
- Continuar pela primeira capacidade sem fonte.
- Registrar no progresso quais capacidades ainda estão pendentes.

## Artefatos esperados

- `docs/pydoll-capabilities.md`.
- Atualização em `progress/YYYY-MM-DD_AGENT_PLAN_01.md`.
- Atualização em `QUESTIONS.md`, se houver pendências.

## Notas para o próximo agente

Não avance para `PLAN_02` sem uma matriz mínima de capacidades P0 verificadas.
