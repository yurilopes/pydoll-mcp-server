# FIX_02: Compatibilidade real com as APIs da Pydoll

## Problema

O código atual usa APIs inexistentes ou assinaturas erradas da Pydoll:

- `ChromiumOptions.set_user_data_dir(...)` não existe.
- `ChromiumOptions.set_headless(...)` não existe.
- `Tab.current_url` e `Tab.title` são async properties. A sintaxe correta é `await tab.current_url` e `await tab.title`.
- `WebElement.text` é async property. A sintaxe correta é `await element.text`.
- `WebElement.get_attribute(name)` é síncrono.

## Arquivos envolvidos

- `src/pydoll_mcp_server/tools/browser.py`
- `src/pydoll_mcp_server/tools/page.py`
- `src/pydoll_mcp_server/tools/elements.py`
- `src/pydoll_mcp_server/dom/deep_traversal.py`
- `src/pydoll_mcp_server/recovery/health.py`
- `tests/unit/`
- `tests/integration/`

## Objetivo

Alinhar o servidor às APIs reais da Pydoll local em `C:\Users\Yuri\Documents\Git\pydoll`, com testes que imitam a assinatura real e falham se o erro voltar.

## Tarefas detalhadas

1. Consultar a Pydoll local antes de editar:
   - `C:\Users\Yuri\Documents\Git\pydoll\pydoll\browser\options.py`;
   - `C:\Users\Yuri\Documents\Git\pydoll\pydoll\browser\tab.py`;
   - `C:\Users\Yuri\Documents\Git\pydoll\pydoll\elements\web_element.py`.
2. Em `browser.py`, substituir:
   - `options.set_user_data_dir(profile.path)` por `options.add_argument(f'--user-data-dir={profile.path}')`;
   - `options.set_headless(True)` por `options.headless = True`.
3. Criar helpers internos, por exemplo em `browser/pydoll_compat.py`:
   - `async get_tab_url(tab) -> str`;
   - `async get_tab_title(tab) -> str`;
   - `async get_element_text(element) -> str`;
   - `get_element_attribute(element, name) -> str | None`.
4. Substituir todos os usos diretos incorretos e centralizar nos helpers:
   - manter a semântica correta de async property para `current_url`, `title` e `text`;
   - trocar `await element.get_attribute(name)` por `element.get_attribute(name)`.
5. Em `page_back` e `page_forward`, não retornar `location.href` imediatamente após `history.back()` como se a navegação tivesse terminado.
   - Preferir CDP Page history se disponível.
   - Se usar JS history, aguardar mudança de URL ou timeout.
6. Atualizar doubles e mocks de teste para refletirem assinaturas reais:
   - `current_url` como async property;
   - `title` como async property;
   - `text` como async property;
   - `get_attribute` como método síncrono.
7. Adicionar teste de `browser_launch` com mock de `ChromiumOptions` validando:
   - argumento `--user-data-dir=...`;
   - `headless=True` quando solicitado.
8. Adicionar teste de navegação que confirma URL e título são strings, não coroutine ou bound method.

## Critérios de aceite

- Não há chamadas a `set_user_data_dir` ou `set_headless`.
- `current_url`, `title` e `text` são acessados como async properties, com `await` e sem parênteses.
- Não há `await element.get_attribute(...)`.
- Os testes falham se as assinaturas erradas forem reintroduzidas.

## Como testar

```powershell
C:\Users\Yuri\anaconda3\python.exe -m pytest tests\unit tests\integration -q
C:\Users\Yuri\anaconda3\python.exe -m mypy src
```

## Erros a evitar

- Não trocar async properties da Pydoll por chamadas com parênteses.
- Não usar fakes com async methods quando a Pydoll usa async properties.
- Não confiar em mocks antigos que escondem assinatura errada.
- Não corrigir mypy com `type: ignore` antes de corrigir a integração real.

## Definição de pronto

Este plano está pronto quando as integrações com Pydoll refletem a API local verificada e `mypy` não reporta mais os erros funcionais ligados a Pydoll.
