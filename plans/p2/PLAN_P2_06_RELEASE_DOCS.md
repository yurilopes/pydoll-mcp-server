# PLAN_P2_06: Packaging, documentação e release experimental

## Objetivo

Preparar o projeto para uma release experimental revisável, com build de pacote, instalação em ambiente temporário, documentação de segurança e checklist de release.

## Escopo

- Versão `0.1.0a1`.
- `LICENSE`.
- `CHANGELOG.md`.
- `docs/security.md`.
- README atualizado com P2.
- Build sdist e wheel.
- Instalação de wheel em ambiente temporário.
- Release checklist sem publicação automática.

## Fora de Escopo

- Publicar no PyPI.
- Criar GitHub release real.
- Assinar artifacts.
- Criar CI completo se ainda não existir.

## Pré-requisitos

- P2.1 a P2.5 concluídos ou com limitações documentadas.
- Gates principais verdes.

## Critérios de Início

- Ler `pyproject.toml`.
- Confirmar se `LICENSE` já existe.
- Confirmar se `CHANGELOG.md` já existe.
- Confirmar se docs vendorizadas da Pydoll entram ou não no pacote.

## Tarefas Detalhadas

1. Ajustar versão para `0.1.0a1`.
2. Criar `LICENSE` MIT se ausente.
3. Criar `CHANGELOG.md` com:
   - Added
   - Changed
   - Security
   - Known limitations
4. Criar `docs/security.md` com:
   - threat model local;
   - bearer token;
   - cookies e storage;
   - JS execution;
   - uploads e downloads;
   - profiles;
   - network e console;
   - diagnostics e trace;
   - runtime cleanup.
5. Atualizar README:
   - `stdio`;
   - tools P2;
   - exemplos de clientes;
   - comandos de build;
   - aviso alpha.
6. Criar `docs/release-checklist.md`.
7. Rodar build:
   - `C:\Users\Yuri\anaconda3\python.exe -m pip install build`
   - `C:\Users\Yuri\anaconda3\python.exe -m build`
8. Instalar wheel em ambiente temporário:
   - criar venv temporária fora do repo ou dentro de diretório ignorado;
   - instalar wheel;
   - rodar import smoke e CLI help;
   - não publicar.
9. Registrar resultados em `progress/YYYY-MM-DD_AGENT_PLAN_P2.md`.

## Critérios de Aceite

- Wheel e sdist são gerados.
- Wheel instala em ambiente temporário.
- Entry point `pydoll-mcp-server` responde a `--help`.
- Docs de segurança existem.
- Release checklist existe.
- README reflete estado P2.

## Definição de Pronto

- Release experimental está pronta para revisão humana.
- Nada foi publicado automaticamente.

## Como Testar

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
C:\Users\Yuri\anaconda3\python.exe -m build
```

## Riscos

- Incluir documentação vendorizada pesada no pacote.
- Build passar, mas wheel não conter entry point.
- Exemplo de config incentivar desabilitar auth.

## Estratégia de Recuperação

Se build falhar por metadata, corrigir apenas packaging. Não mexer em features P2 nesta fase, salvo se bloquearem import básico.

## Artefatos Esperados

- `LICENSE`
- `CHANGELOG.md`
- `docs/security.md`
- `docs/release-checklist.md`
- README atualizado
- Build local validado
- Progresso registrado

## Notas Para o Próximo Agente

Não publique pacote. Pare em release pronta para revisão.
