# PLAN_12: Documentação, exemplos e release experimental

## Objetivo

Preparar documentação de uso, exemplos práticos e checklist para primeira release experimental via GitHub e pip.

## Escopo

- README completo.
- Exemplos para Codex, OpenCode e Claude Code.
- Guia de instalação.
- Guia de segurança.
- Guia de troubleshooting.
- Checklist de release experimental.

## Fora de escopo

- Publicar release sem aprovação de Yuri.
- Garantir compatibilidade com todos os clientes MCP existentes.
- Criar site de documentação completo.

## Pré-requisitos

- `PLAN_11` concluído.
- Tests mínimos verdes.
- API P0 documentada.

## Critérios de início

- `pytest` padrão passa.
- Tools P0 estão implementadas e documentadas.
- Segurança básica está validada.

## Tarefas detalhadas

1. Registrar início em `progress/`.
2. Atualizar README com:
   - instalação local;
   - execução HTTP;
   - configuração de token;
   - diretórios runtime;
   - exemplo de client_id;
   - lista resumida de tools;
   - aviso de segurança.
3. Criar `docs/usage.md`.
4. Criar `docs/security.md`.
5. Criar `docs/troubleshooting.md`.
6. Criar exemplos:
   - `examples/codex.md`;
   - `examples/opencode.md`;
   - `examples/claude-code.md`;
   - fluxo básico de launch, goto, tree, click.
7. Documentar compatibilidade com Pydoll e versão testada.
8. Documentar limitações:
   - OOPIF;
   - closed shadow root;
   - JS execution sensível;
   - cookies e storage redigidos por padrão;
   - stdio em P2.
9. Criar checklist de release:
   - versionamento;
   - changelog;
   - build sdist e wheel;
   - tests;
   - smoke test em Windows;
   - revisão de secrets;
   - tag GitHub.
10. Garantir que nenhum artifact runtime está trackeado.
11. Atualizar `progress/` com estado final.

## Critérios de aceite

- Usuário consegue entender objetivo, instalar e iniciar experimentalmente.
- Há exemplos para os três clientes prioritários.
- Segurança e limites estão claros.
- Checklist de release não exige decisões do implementador.

## Definição de pronto

- Documentação mínima completa.
- Examples revisados.
- Release checklist criado.
- Progress atualizado com recomendação final.

## Como testar

- Seguir README do zero em ambiente limpo.
- Executar smoke test de health.
- Executar exemplo básico com uma página local.
- Conferir `git status --short` para artifacts acidentais.

## Riscos

- Instruções de clientes MCP podem mudar.
- Packaging pode ter diferença entre Windows e Unix.
- Usuários podem tentar expor o servidor fora de localhost.

## Estratégia de recuperação se o agente for interrompido

- Conferir checklist de release.
- Continuar pela primeira documentação ausente.
- Não publicar nada sem aprovação.

## Artefatos esperados

- README atualizado.
- Documentos em `docs/`.
- Exemplos em `examples/`.
- Checklist de release.
- Registro final em `progress/`.

## Notas para o próximo agente

Ao concluir este plano, peça revisão humana antes de publicar qualquer pacote ou release.
