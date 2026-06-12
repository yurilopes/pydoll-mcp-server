# Prompt para o LLM desenvolvedor

Você está trabalhando no repositório:

```text
C:\Users\Yuri\Documents\Git\pydoll-mcp-server
```

Sistema: Windows em modo nativo. Python disponível em:

```text
C:\Users\Yuri\anaconda3\python.exe
```

Repositório local da Pydoll para consulta:

```text
C:\Users\Yuri\Documents\Git\pydoll
```

Documentação vendorizada:

```text
references/pydoll-docs/
```

## O que aconteceu

Você implementou um scaffold amplo e registrou em `progress/2026-06-12_AGENT_PLAN_01_12.md` que os planos 01 a 12 estavam completos. Isso foi prematuro.

O `pytest` passou, mas os testes atuais não validavam os caminhos reais mais importantes:

- servidor MCP HTTP real;
- API real instalada do FastMCP;
- lançamento real ou mock realista do browser Pydoll;
- assinatura real de `ChromiumOptions`;
- assinatura real de `Tab.current_url`, `Tab.title`, `WebElement.text` e `WebElement.get_attribute`;
- uso de `element_id` de `page_get_tree` em `element_click`;
- traversal recursivo real de iframes;
- locks reais por recurso;
- allowlist de filesystem segura.

Você confundiu "código que importa" com "código que funciona". Também confundiu "plano coberto por arquivo" com "plano validado por comportamento".

## O que você entendeu errado

1. Você assumiu APIs da Pydoll sem checar assinatura real no código local.
   - `ChromiumOptions.set_user_data_dir` não existe.
   - `ChromiumOptions.set_headless` não existe.
   - `Tab.current_url` e `Tab.title` são async properties, não métodos comuns.
   - `WebElement.text` é async property, não método comum.
   - `get_attribute` é síncrono.

2. Você assumiu API errada do FastMCP.
   - A versão instalada tem `streamable_http_app()` e `sse_app()`.
   - Não tem `http_app()`.

3. Você declarou deep traversal, mas só detectou iframes.
   - Detectar iframe não é entrar no iframe.
   - Listar shadow roots com `deep=False` não cumpre o requisito de OOPIF e traversal profundo.

4. Você gerou `element_id` na árvore sem torná-lo acionável.
   - Um agente precisa observar a árvore e depois clicar ou preencher pelo mesmo `element_id`.
   - ID sem `_pydoll_element` e sem reaquisição por hints não serve para interação.

5. Você criou locks, mas não aplicou locks nas operações mutantes.
   - Existência de `LockManager` não garante concorrência segura.

6. Você validou segurança por intenção, mas não por tests negativos suficientes.
   - `startswith` para paths é inseguro.
   - Screenshot, download e upload precisam validar diretórios permitidos.

7. Você marcou completo sem rodar gates suficientes.
   - `pytest` passou.
   - `ruff check .` falhou.
   - `mypy src` falhou.
   - Browser smoke real não existia.

## Sua tarefa agora

Corrija os problemas seguindo estes arquivos, nesta ordem:

1. `docs/evaluation-2026-06-12.md`
2. `plans/remediation/README.md`
3. `plans/remediation/FIX_01_TRANSPORT_AND_AUTH.md`
4. `plans/remediation/FIX_02_PYDOLL_API_COMPAT.md`
5. `plans/remediation/FIX_03_ACTIONABLE_ELEMENT_IDS.md`
6. `plans/remediation/FIX_04_DEEP_TRAVERSAL.md`
7. `plans/remediation/FIX_05_CONCURRENCY_PROFILES.md`
8. `plans/remediation/FIX_06_SECURITY_AND_ARTIFACTS.md`
9. `plans/remediation/FIX_07_TEST_QUALITY_GATES.md`
10. `plans/PLAN_P1.md`

Não comece `plans/PLAN_P2.md` enquanto P1 e todos os arquivos `FIX_*.md` não estiverem completos.

## Como trabalhar

Antes de editar:

```powershell
git status --short
```

Leia:

```text
AGENTS.md
PLAN.md
docs/evaluation-2026-06-12.md
plans/remediation/README.md
```

Registre progresso em:

```text
progress/YYYY-MM-DD_AGENT_REMEDIATION.md
```

## Critério de correção por bug

Para cada bug:

1. Reproduza ou confirme o problema.
2. Corrija usando a API real da Pydoll ou do MCP SDK.
3. Adicione teste que falharia antes da correção.
4. Rode os testes relevantes.
5. Atualize progresso.

Não use `type: ignore` ou relaxamento de config para esconder problema real.

## Comandos obrigatórios de reavaliação

Depois de cada plano de correção:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
```

No final:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m mypy src
```

Também crie e documente smoke real:

```powershell
$env:PYDOLL_MCP_AUTH_TOKEN = "test-token"
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
Remove-Item Env:PYDOLL_MCP_AUTH_TOKEN -ErrorAction SilentlyContinue
```

Se o smoke real não puder rodar no ambiente, registre exatamente o motivo técnico em `progress/` e mantenha o teste marcado corretamente.

## Critérios para você declarar pronto

Você só pode dizer que terminou quando:

- `pytest -q` passa;
- `ruff check .` passa;
- `mypy src` passa;
- `create_app()` é testado com o SDK MCP instalado;
- `browser_launch` usa a API real da Pydoll;
- `page_get_tree` retorna IDs acionáveis;
- `element_click` funciona com ID vindo de `page_get_tree`;
- `page_get_tree_deep` entra em iframe simples em teste;
- locks são usados em operações mutantes;
- profile default persistente é travado;
- path allowlist não usa `startswith`;
- progresso foi registrado.

## Como não repetir os erros

- Sempre valide assinatura contra o código local antes de usar uma API.
- Sempre crie tests que exercitam o comportamento real, não só imports.
- Sempre rode `pytest`, `ruff` e `mypy`.
- Sempre diferencie scaffold, mock, integração e browser real.
- Nunca declare plano completo porque um arquivo existe.
- Nunca use o registro de progresso como prova. Prova é teste executado e comportamento validado.
- Se uma capacidade for hipótese, marque como hipótese. Não apresente como implementada.
