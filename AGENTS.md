# Instruções para agentes

## Contexto

Este repositório planeja e implementará um MCP server em Python para a biblioteca Pydoll. O objetivo é criar uma alternativa ao Playwright MCP Server baseada em Pydoll, com foco em automação de navegador para agentes.

O projeto ainda está em fase de planejamento inicial. Não implemente código antes de seguir os planos em ordem.

## Caminhos importantes

- Repositório do projeto: `C:\Users\Yuri\Documents\Git\pydoll-mcp-server`.
- Repositório local da Pydoll: `C:\Users\Yuri\Documents\Git\pydoll`.
- Documentação vendorizada da Pydoll: `references/pydoll-docs/`.
- Planos detalhados: `plans/`.
- Registros de progresso: `progress/`.
- Python via Anaconda: `C:\Users\Yuri\anaconda3\python.exe`.

## Regras do ambiente

- Estamos no Windows em modo nativo.
- Trate esta máquina com cuidado. Esta máquina é nossa casa.
- Não execute comandos destrutivos sem necessidade.
- Não apague arquivos sem solicitação explícita.
- Não modifique arquivos fora deste repositório, exceto leitura do repositório local da Pydoll.
- Antes de qualquer ação potencialmente destrutiva, registre a justificativa no plano ou progresso e escolha uma alternativa segura.
- Nunca reverta alterações de outro agente ou do usuário sem pedido explícito.
- Use UTF-8.
- Não use em dash.

## Como começar trabalho

1. Leia `PLAN.md`.
2. Leia o plano detalhado atual em `plans/PLAN_XX.md`.
3. Leia o último arquivo relevante em `progress/`, se existir.
4. Consulte `QUESTIONS.md` para decisões e pendências.
5. Consulte `references/pydoll-docs/` e, quando necessário, o código local em `C:\Users\Yuri\Documents\Git\pydoll`.
6. Execute os planos em sequência estrita.

## Como registrar progresso

Crie ou atualize um arquivo:

```text
progress/YYYY-MM-DD_AGENT_PLAN_XX.md
```

Use conteúdo curto:

- plano atual;
- tarefas concluídas;
- arquivos alterados;
- testes executados;
- bloqueios;
- próximo passo.

Não seja excessivamente verboso. O objetivo é permitir retomada rápida por outro agente.

## Como retomar trabalho interrompido

- Leia o plano detalhado correspondente.
- Leia o progresso mais recente.
- Verifique `git status --short`.
- Confirme quais critérios de aceite já foram atendidos.
- Continue da primeira tarefa incompleta.
- Se encontrar divergência entre plano e código real, registre em `progress/` e ajuste somente se for necessário para cumprir o plano.

## Python e ambiente

Use o Python do Anaconda quando precisar executar comandos locais:

```powershell
C:\Users\Yuri\anaconda3\python.exe --version
```

Futuramente, o projeto deve ser portável para Windows, macOS e Unix. Não introduza dependências específicas de Windows sem motivo claro e sem fallback.

## Async e Pydoll

- A Pydoll é assíncrona por padrão.
- Não bloqueie o event loop global.
- Use `asyncio` com timeouts explícitos.
- Tools MCP devem parecer síncronas para o cliente: retornar apenas quando a ação terminar, falhar ou expirar.
- Ações longas em uma aba não devem bloquear abas independentes.
- Use locks por recurso para operações mutantes em uma mesma aba, browser, perfil ou janela.

## Frames, iframes e shadow root

Trate frames, iframes, OOPIFs e shadow roots como parte central da arquitetura.

- Pydoll permite interagir com iframes como `WebElement`.
- A documentação local informa suporte a OOPIF e shadow roots inclusive closed via CDP.
- XPath não atravessa shadow boundaries de forma geral.
- Dentro de shadow roots, prefira CSS selector quando a Pydoll exigir.
- Tools profundas devem retornar `frame_path`, `shadow_path`, selector hints, xpath hints, bounding box, estado visible/enabled/clickable e texto resumido.
- Métodos rápidos devem ser compactos e baratos.
- Métodos robustos devem ser explícitos, limitados e com timeout próprio.

## Segurança

- Não exponha `execute_cdp_cmd` livre.
- Não crie tool para executar comandos do sistema operacional.
- Não crie leitura ou escrita arbitrária de filesystem.
- Cookies, storage, headers Authorization, tokens e valores de formulário são sensíveis.
- Logs devem redigir segredos.
- `js_evaluate` e `js_evaluate_readonly` são sensíveis e precisam de limites, timeout, auditoria resumida e redaction.
- Uploads e downloads devem usar diretórios permitidos.
- Modo seguro deve ser o padrão.

## Testes futuros

Quando a implementação começar:

- Use fixtures HTML locais.
- Cubra UTF-8 com caracteres acentuados, chinês, japonês e coreano.
- Cubra iframes simples, nested iframes, OOPIF quando viável e shadow DOM aberto ou fechado.
- Cubra timeout, cancelamento e recovery.
- Cubra isolamento multi-cliente por `client_id`.
- Cubra contrato MCP com cliente real ou MCP inspector quando aplicável.

## Dúvidas

Se uma decisão estiver ausente:

1. Consulte `PLAN.md`, `QUESTIONS.md` e o plano atual.
2. Verifique se a resposta está no código ou docs da Pydoll.
3. Se continuar incerto, registre como `PENDENTE` em `QUESTIONS.md` e em `progress/`.
4. Use a opção mais segura por padrão.
