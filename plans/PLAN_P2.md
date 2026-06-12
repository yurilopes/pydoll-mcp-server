# PLAN_P2: Rebase para capacidades avançadas e release experimental

## Objetivo

Executar o P2 sobre o estado real pós P1, com foco em interoperabilidade local, diagnóstico avançado, inspeção segura, robustez multi-cliente, attach controlado e preparação de release experimental.

Este plano substitui o P2 antigo. O P1 rebaseado já concluiu o alpha local com HTTP real, bearer auth, `page_get_tree`, `element_id`, fill UTF-8, deep traversal mínimo, locks comportamentais, redaction, artifacts seguros e README operacional.

## Estado confirmado antes do P2

- P1 rebaseado concluído.
- `C:\Users\Yuri\anaconda3\python.exe -m pytest -q`: 150 passed, 2 warnings de dependência.
- `C:\Users\Yuri\anaconda3\python.exe -m ruff check .`: All checks passed.
- `C:\Users\Yuri\anaconda3\python.exe -m mypy src`: Success, 33 source files.
- `C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q`: 9 passed.
- HTTP local em `127.0.0.1` é o transporte principal.
- `/health`, `/mcp` e `/sse` já existem.
- `execute_cdp_cmd` livre não existe e não deve ser criado.

## Princípios do P2

- Executar fases em sequência estrita.
- Não avançar se o aceite da fase atual falhar.
- Preferir capacidades reais da Pydoll local em vez de inferências.
- Implementar erro estruturado `UNSUPPORTED` quando uma capacidade não for viável com segurança.
- Não criar workaround que exponha CDP livre, filesystem arbitrário ou comandos de sistema.
- Preservar HTTP local como caminho recomendado.
- Adicionar `stdio` como compatibilidade opcional.
- Toda tool nova deve retornar `success=true` ou erro estruturado com `error_code`.
- Logs e artifacts não podem vazar bearer token, cookies, storage, Authorization headers ou código JS completo.

## Planos Detalhados

1. `plans/p2/PLAN_P2_01_API_CONTRACT.md`
   - `schema_version`, `server_status.capabilities`, contrato consistente de outputs e catálogo MCP.
2. `plans/p2/PLAN_P2_02_STDIO_CLIENTS.md`
   - Transporte `stdio` opcional e exemplos para Codex, OpenCode e Claude Code.
3. `plans/p2/PLAN_P2_03_NETWORK_CONSOLE.md`
   - Network inspection, console inspection, redaction e retenção limitada.
4. `plans/p2/PLAN_P2_04_DIAGNOSTICS_TRACE.md`
   - `diagnostics_snapshot`, trace leve, artifacts e cleanup.
5. `plans/p2/PLAN_P2_05_MULTI_CLIENT_ATTACH.md`
   - Stress multi-cliente, metadata runtime, cleanup stale e `browser_attach` seguro.
6. `plans/p2/PLAN_P2_06_RELEASE_DOCS.md`
   - Packaging, wheel, `LICENSE`, `CHANGELOG.md`, `docs/security.md` e release checklist.

## Gates Obrigatórios

Rodar no início e no fim do P2:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
```

## Critérios Globais de Sucesso

- Artefatos Markdown do P2 foram criados ou atualizados.
- `server_status` expõe `schema_version` e `capabilities`.
- `stdio` opcional funciona ou tem limitação documentada com teste.
- Network inspection funciona com redaction.
- Console inspection funciona ou retorna `UNSUPPORTED` estruturado.
- `diagnostics_snapshot` existe e não vaza segredos.
- Trace leve existe com cleanup seguro.
- Multi-cliente e isolamento passam em teste.
- `browser_attach` só aceita browsers lançados pelo servidor e do mesmo `client_id`.
- Wheel instala em ambiente temporário.
- Release experimental fica pronta para revisão humana, sem publicação automática.

## Fora de Escopo

- Publicar pacote sem aprovação humana.
- Abrir bind público por padrão.
- Expor `execute_cdp_cmd` livre.
- Expor comandos do sistema operacional.
- Leitura ou escrita arbitrária de filesystem.
- Automação furtiva, fraude, CAPTCHA bypass ou evasão de segurança.
- Sincronização distribuída multi-host.

## Recuperação Após Interrupção

1. Ler `AGENTS.md`.
2. Ler este arquivo.
3. Ler o plano detalhado P2 atual.
4. Ler o arquivo mais recente em `progress/`.
5. Rodar `git status --short`.
6. Retomar pela primeira fase sem aceite confirmado.
7. Registrar progresso curto em `progress/YYYY-MM-DD_AGENT_PLAN_P2.md`.
