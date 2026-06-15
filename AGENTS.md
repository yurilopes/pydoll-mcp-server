# Instruções para agentes

## Contexto

Este repositório implementa um MCP server em Python para automação de navegador com
Pydoll. O objetivo é oferecer uma API previsível e segura para agentes, preservando a
natureza assíncrona da Pydoll e o isolamento entre clientes.

## Regra de ouro

Mantenha a qualidade desde a primeira alteração. Não aceite atalhos, não adie limpeza e
não presuma que um débito temporário será corrigido depois. Corrija a causa raiz enquanto
o contexto ainda está disponível.

Legibilidade humana, correção e segurança têm prioridade sobre concisão, velocidade de
implementação e abstrações engenhosas.

## Caminhos locais

- Repositório do projeto: `C:\Users\Yuri\Documents\Git\pydoll-mcp-server`.
- Repositório local da Pydoll, somente leitura: `C:\Users\Yuri\Documents\Git\pydoll`.
- Python via Anaconda: `C:\Users\Yuri\anaconda3\python.exe`.
- Documentação vendorizada da Pydoll: `references/pydoll-docs/`.

Estes caminhos são específicos deste ambiente. Não os copie para documentação pública.

## Regras não negociáveis

- Trate esta máquina com cuidado. Esta máquina é nossa casa.
- Não execute ações destrutivas sem necessidade e nunca reverta alterações de terceiros.
- Preserve UTF-8 e não use em dash.
- Não modifique o repositório `websocket_lambda`. Ele é somente referência de estilo.
- Não copie segredos, credenciais ou padrões inseguros encontrados em outros projetos.
- Não exponha `execute_cdp_cmd`, comandos do sistema operacional ou filesystem arbitrário.
- Não enfraqueça Ruff, mypy, Pyright, o LSP ou testes para ocultar um problema.
- Não use `Any`, `cast` ou `type: ignore` para silenciar tipagem. Quando uma biblioteca
  externa exigir uma fronteira dinâmica, isole, justifique e normalize o valor imediatamente.
- Não dobre o código principal para facilitar mocks ou fazer testes passarem.
- Não adicione compatibilidade retroativa artificial para preservar contratos alpha incorretos.

## Engenharia e arquitetura

- Prefira fluxo operacional direto, validação antecipada e nomes orientados ao domínio.
- Respeite separação de responsabilidades, baixo acoplamento e dependências explícitas.
- Não crie abstrações sem benefício concreto. Código legível vem antes de engenharia excessiva.
- Erros internos devem ser específicos. Converta-os para erros MCP estruturados somente na
  fronteira superior apropriada.
- `except Exception` é aceitável somente dentro de funções registradas como tools MCP, após
  exceções esperadas, para impedir a queda do servidor e converter a falha inesperada.
- Helpers e serviços internos devem capturar `PydollException` ou exceções específicas.
- Deep traversal deve reportar falhas parciais em `errors` com `partial=true`, nunca ignorá-las.
- Fallbacks best-effort devem ser explícitos no nome, seguros e documentados.

## Tamanho dos arquivos

- Meta: até 400 linhas físicas por arquivo Python.
- Limite máximo: 450 linhas físicas.
- Arquivos entre 401 e 450 linhas exigem justificativa curta na revisão ou progresso.
- Arquivos acima de 450 linhas devem ser refatorados preservando coesão lógica.
- Não fragmente lógica coesa apenas para reduzir a contagem.

## Comentários e logs

Comentários no código devem ser em inglês, curtos e explicar somente:

- regra funcional ou de negócio;
- boundary de segurança ou ownership;
- motivo de lock ou decisão de concorrência;
- risco de operação destrutiva;
- motivo de recovery ou fallback best-effort seguro.

Não narre código evidente. Logs devem registrar operações e transições relevantes sem
expor tokens, cookies, storage, código JavaScript completo ou conteúdo sensível.

## Async, concorrência e Pydoll

- Não bloqueie o event loop global.
- Toda operação potencialmente longa deve ter timeout explícito.
- A tool só retorna quando a ação termina, falha ou expira.
- Use locks por tab, browser ou perfil para mutações que possam interferir.
- Ações em recursos independentes devem continuar concorrentes.
- Respeite as APIs assíncronas reais da Pydoll. Não altere propriedades assíncronas para
  métodos apenas para satisfazer testes.
- Trate frames, iframes, OOPIFs e shadow roots como parte central da arquitetura.

## Testes

- Testes representam contratos reais. Fakes devem adaptar-se ao código de produção.
- Prefira fakes tipados pequenos a mocks genéricos e inspeção de source.
- Cubra ownership, isolamento, UTF-8, frames, shadow roots, timeout, cancelamento,
  recovery, redaction e segurança de paths.
- Nunca adicione branch de produção exclusivo para testes.

Antes de concluir, execute:

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest -q
C:\Users\Yuri\anaconda3\python.exe -m ruff check .
C:\Users\Yuri\anaconda3\python.exe -m ruff format --check .
C:\Users\Yuri\anaconda3\python.exe -m mypy --strict src tests
C:\Users\Yuri\anaconda3\python.exe -m pyright --pythonpath C:\Users\Yuri\anaconda3\python.exe
C:\Users\Yuri\anaconda3\python.exe -m pytest -m mcp_e2e -q
C:\Users\Yuri\anaconda3\python.exe -m pytest -m browser_smoke -q
C:\Users\Yuri\anaconda3\python.exe -m build
```

## Como trabalhar e retomar

1. Leia este arquivo, `README.md`, o código relevante e o último progresso aplicável.
2. Verifique `git status --short` e não reverta mudanças existentes.
3. Consulte a Pydoll local ou vendorizada antes de supor uma capacidade.
4. Faça alterações coesas e mantenha os gates verdes.
5. Registre progresso curto em `progress/YYYY-MM-DD_AGENT_<TAREFA>.md` quando necessário.

Ao encontrar dúvida, investigue primeiro no código e na documentação. Use a opção mais
segura quando a decisão continuar incerta e registre a limitação.
