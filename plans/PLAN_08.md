# PLAN_08: JavaScript execution e helpers seguros CDP-backed

## Objetivo

Implementar execução JavaScript sensível, helpers seguros baseados em CDP e operações delimitadas de cookies, storage, upload e download.

## Escopo

- `js_evaluate_readonly`.
- `js_evaluate`.
- `user_agent_set`.
- `viewport_set`.
- `cookies_get` e `cookies_set`.
- `storage_get` e `storage_set`.
- `download_expect`.
- `upload_files`.

## Fora de escopo

- `execute_cdp_cmd` livre.
- Execução de comandos do sistema operacional.
- Leitura ou escrita arbitrária de arquivos.
- Bypass de CAPTCHA ou segurança.

## Pré-requisitos

- `PLAN_07` concluído.
- Políticas de redaction e logging do `PLAN_10` pelo menos rascunhadas, se ainda não implementadas.
- Capacidade Pydoll para execute_script, cookies, storage, downloads, upload e user-agent validada.

## Critérios de início

- Tools de navegação e elementos funcionam.
- Erro estruturado existe.
- Diretórios permitidos para artifacts estão definidos.

## Tarefas detalhadas

1. Registrar início em `progress/`.
2. Criar `tools/javascript.py`, `tools/storage.py`, `tools/files.py` e `browser/cdp_helpers.py`.
3. Implementar limites JS:
   - timeout default 5s;
   - timeout máximo 15s;
   - código máximo 20.000 caracteres;
   - resultado máximo 256 KiB.
4. Implementar scanner simples para padrões perigosos:
   - loops óbvios;
   - `fetch(` para domínios externos;
   - `document.cookie`;
   - `localStorage` e `sessionStorage` em readonly;
   - `form.submit`;
   - `location =` ou `location.href`.
5. Implementar `js_evaluate_readonly` com `throw_on_side_effect` quando suportado por Pydoll/CDP.
6. Implementar `js_evaluate` com aviso documental e auditoria resumida.
7. Garantir JSON serializável e truncation.
8. Implementar `user_agent_set` com helper CDP delimitado, usando APIs ou commands Pydoll validados.
9. Implementar `viewport_set` apenas se capacidade for validada. Se não, marcar como unsupported estruturado.
10. Implementar cookies com escopo obrigatório e redaction por padrão.
11. Implementar storage com origem explícita e redaction por padrão.
12. Implementar download em diretório permitido.
13. Implementar upload apenas de paths explicitamente permitidos.
14. Adicionar tests de limites, bloqueios, redaction e paths.

## Critérios de aceite

- `js_evaluate_readonly` bloqueia padrões mutantes conhecidos.
- `js_evaluate` registra auditoria sem conteúdo sensível completo.
- Cookies e storage exigem escopo.
- Upload fora de allowlist falha.
- Download grava somente em diretório permitido.
- Nenhuma tool expõe CDP livre.

## Definição de pronto

- Tools sensíveis funcionam com limites e tests.
- Documentação de segurança atualizada.
- Progress atualizado.

## Como testar

- JS simples retornando JSON.
- JS com loop óbvio bloqueado.
- JS com resultado grande truncado.
- Cookies e storage em origem local.
- Upload/download com fixtures e diretórios temporários permitidos.

## Riscos

- Detectar side effects em JS é imperfeito.
- Cookies e storage podem vazar dados se redaction falhar.
- Upload/download dependem de comportamento do browser.

## Estratégia de recuperação se o agente for interrompido

- Desabilitar temporariamente tools sensíveis incompletas por config.
- Rodar tests de segurança antes de seguir.
- Retomar uma categoria por vez.

## Artefatos esperados

- Tools JS, storage e files.
- Helpers CDP seguros.
- Tests de segurança.
- Atualização documental.
- Registro em `progress/`.

## Notas para o próximo agente

Se uma capacidade CDP for necessária, encapsule em helper específico e testado. Não crie pass-through genérico.
