# PLAN_10: Segurança, permissões, logging e métodos proibidos

## Objetivo

Endurecer o servidor contra vazamento de dados, abuso de tools sensíveis e ações fora dos limites de browser automation.

## Escopo

- Bearer token obrigatório.
- Redaction.
- Allowlist de arquivos.
- Política de logs.
- Política para JavaScript.
- Política para CDP-backed helpers.
- Métodos proibidos.
- Riscos multi-agente.

## Fora de escopo

- OAuth remoto.
- Gestão de usuários multi-tenant em rede pública.
- Sandbox de sistema operacional.

## Pré-requisitos

- `PLAN_09` concluído.
- Tools sensíveis implementadas ou stubadas com segurança.
- Logging estruturado existe.

## Critérios de início

- Tests de health e recovery passam.
- `PYDOLL_MCP_AUTH_TOKEN` é exigido por padrão.
- Redaction mínima existe ou será criada neste plano.

## Tarefas detalhadas

1. Registrar início em `progress/`.
2. Criar `security/redaction.py`, `security/permissions.py` e `security/policy.py`.
3. Garantir auth por bearer token em todos os endpoints MCP HTTP.
4. Garantir que modo sem auth exige variável explícita de desenvolvimento.
5. Implementar redaction para:
   - cookies;
   - tokens;
   - Authorization;
   - localStorage e sessionStorage;
   - campos com nomes como password, secret, token, api_key.
6. Aplicar redaction em logs e outputs sensíveis.
7. Definir allowlist de arquivos:
   - downloads e artifacts do app data;
   - paths extras configurados explicitamente;
   - uploads apenas de paths permitidos.
8. Bloquear escrita fora de diretórios permitidos.
9. Bloquear leitura arbitrária.
10. Documentar métodos proibidos:
    - `execute_cdp_cmd` livre;
    - comandos de OS;
    - filesystem arbitrário;
    - exfiltração ampla de cookies e storage;
    - bypass de CAPTCHA, fraude ou abuso.
11. Adicionar tests de redaction e permissões.
12. Revisar todas as tools sensíveis.

## Critérios de aceite

- Sem token, acesso falha por padrão.
- Logs não contêm tokens, cookies ou valores sensíveis em tests.
- Upload e download respeitam allowlist.
- Tools sensíveis são auditadas.
- Métodos proibidos estão documentados e não existem na API.

## Definição de pronto

- Tests de segurança passam.
- README e docs indicam postura segura por padrão.
- Progress atualizado.

## Como testar

- Teste com headers Authorization falsos.
- Teste redaction em strings com tokens e cookies.
- Teste path traversal em upload/download.
- Teste que `execute_cdp_cmd` não aparece em lista de tools.

## Riscos

- Redaction pode não cobrir todo padrão sensível.
- Clientes locais maliciosos podem tentar usar token se tiverem acesso ao ambiente.
- Allowlist mal configurada pode bloquear uso legítimo.

## Estratégia de recuperação se o agente for interrompido

- Rode tests de segurança primeiro.
- Se alguma tool sensível estiver sem redaction, desabilite por config até completar.
- Registre pendências em `progress/`.

## Artefatos esperados

- Módulos de segurança.
- Tests de redaction e permissions.
- Documentação atualizada.
- Registro em `progress/`.

## Notas para o próximo agente

Não aceite atalhos de segurança para passar tests de contrato MCP.
