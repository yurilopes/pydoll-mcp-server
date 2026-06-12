# PLAN_11: Testes, fixtures locais, contrato MCP e concorrência

## Objetivo

Completar a estratégia de testes em camadas, cobrindo contrato MCP, browser automation, deep traversal, segurança, recovery e multi-cliente.

## Escopo

- Unit tests.
- Async tests.
- Fixtures HTML locais.
- Tests de MCP.
- Tests de concorrência.
- Tests manuais guiados.
- Marcação de tests lentos e integração.

## Fora de escopo

- Dependência obrigatória em sites externos.
- CI avançado com matrix completa, salvo se simples.
- Performance benchmarking profundo.

## Pré-requisitos

- `PLAN_10` concluído.
- Tools P0 e P1 principais implementadas.
- Segurança aplicada.

## Critérios de início

- Tests existentes passam ou falhas estão documentadas.
- Fixtures básicas existem.
- Comando de test está documentado.

## Tarefas detalhadas

1. Registrar início em `progress/`.
2. Organizar tests:
   - `tests/unit/`;
   - `tests/integration/`;
   - `tests/fixtures/pages/`;
   - `tests/contract/`.
3. Criar fixtures:
   - página simples;
   - Unicode;
   - input e botão;
   - iframe simples;
   - nested iframe;
   - shadow DOM aberto;
   - closed shadow root se viável;
   - página com atraso;
   - página com muitos nós.
4. Criar unit tests para:
   - config;
   - IDs;
   - registry;
   - locks;
   - errors;
   - redaction;
   - permissions;
   - element cache.
5. Criar async tests para waits e timeouts.
6. Criar integration tests para browser launch, navigation, observation e elements.
7. Criar tests deep para iframe e shadow.
8. Criar tests de contrato MCP:
   - listar tools;
   - chamar health;
   - chamar fluxo básico.
9. Criar tests de concorrência:
   - dois `client_id`;
   - duas tabs independentes;
   - lock na mesma tab.
10. Documentar tests manuais com MCP inspector ou cliente equivalente.
11. Adicionar marcadores pytest:
   - `unit`;
   - `integration`;
   - `browser`;
   - `slow`;
   - `contract`.

## Critérios de aceite

- Unit tests passam sem abrir browser.
- Integration tests são marcados e podem ser executados separadamente.
- Fixtures locais cobrem iframe e shadow.
- Test de multi-cliente prova isolamento básico.
- Test de contrato MCP lista tools esperadas.

## Definição de pronto

- Estratégia de tests documentada.
- Suite padrão é rápida e confiável.
- Browser tests não rodam sem marcador explícito ou configuração apropriada.
- Progress atualizado.

## Como testar

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest
C:\Users\Yuri\anaconda3\python.exe -m pytest -m integration
```

Adapte comandos conforme ambiente virtual definido no `pyproject.toml`.

## Riscos

- Browser tests podem ser instáveis em CI.
- OOPIF pode exigir servidor local com origens diferentes.
- MCP client tests podem depender de versão do SDK.

## Estratégia de recuperação se o agente for interrompido

- Rodar unit tests primeiro.
- Marcar tests instáveis como integração ou slow, não remover.
- Registrar falhas conhecidas em `progress/`.

## Artefatos esperados

- Estrutura de tests completa.
- Fixtures locais.
- Documentação de execução.
- Registro em `progress/`.

## Notas para o próximo agente

Release experimental só pode ser preparada com tests mínimos verdes.
