# PLAN_03: Lifecycle de browser, sessões, perfis, janelas e abas

## Objetivo

Implementar o gerenciamento de browsers, perfis, tabs, janelas, IDs estáveis, ownership por `client_id` e locks por recurso.

## Escopo

- `browser_launch`, `browser_list`, `browser_close`.
- `tab_list`, `tab_activate`, `tab_close`.
- Estruturas de registry.
- Perfis persistentes por `client_id`.
- Perfis temporários.
- Locks por browser, tab, janela e perfil.

## Fora de escopo

- Navegação robusta.
- Interação com elementos.
- Deep traversal.
- Recovery avançado.

## Pré-requisitos

- `PLAN_02` concluído.
- Servidor MCP mínimo funcional.
- Capacidade Pydoll de `Chrome().start`, `new_tab`, `get_opened_tabs`, `get_window_id_for_tab` validada.

## Critérios de início

- Tests de health passam.
- Config runtime e auth existem.
- `client_id` está definido como campo obrigatório nas tools de lifecycle.

## Tarefas detalhadas

1. Registrar início em `progress/`.
2. Criar módulos:
   - `browser/registry.py`;
   - `browser/models.py`;
   - `browser/profiles.py`;
   - `browser/locks.py`;
   - `tools/browser.py`;
   - `tools/tabs.py`.
3. Definir modelos Pydantic para browser, tab, context, profile e window.
4. Definir formato de IDs:
   - prefixos curtos, por exemplo `br_`, `tab_`, `ctx_`, `win_`;
   - IDs opacos para clientes;
   - map interno para objetos Pydoll.
5. Implementar profile path:
   - default persistente por `client_id`;
   - temporário quando `profile_mode=temporary`;
   - nomeado quando `profile_id` informado.
6. Implementar lock exclusivo por perfil persistente.
7. Implementar `browser_launch` com Chrome visível por padrão e headless opcional.
8. Garantir que argumentos Pydoll usem `--user-data-dir` controlado pelo servidor.
9. Implementar `browser_list` filtrado por `client_id`.
10. Implementar `browser_close` com cleanup seguro.
11. Implementar listagem e ativação de tabs.
12. Implementar fechamento de tab.
13. Adicionar testes unitários do registry e ownership.
14. Adicionar teste de integração opcional para launch se ambiente permitir.

## Critérios de aceite

- Um cliente só lista browsers e tabs do próprio `client_id`.
- Dois `client_id` diferentes não compartilham registry por padrão.
- Perfil persistente default fica fora do repositório.
- Perfil persistente nomeado não permite uso concorrente sem lock.
- Fechar browser limpa registry e libera lock de perfil.

## Definição de pronto

- Tools P0 de browser e tab lifecycle funcionam.
- Tests de registry, ownership e locks passam.
- Progress atualizado.

## Como testar

- Unit tests sem abrir browser para registry e locks.
- Integração manual ou marcada com `pytest -m integration` para launch e close.
- Verificar que nenhum perfil é criado dentro do repositório.

## Riscos

- Chrome pode não estar no caminho esperado pela Pydoll.
- Perfil persistente pode ficar locked se processo cair.
- Janelas em modo headless podem não ter bounds úteis.

## Estratégia de recuperação se o agente for interrompido

- Verificar registry em memória e arquivos de lock.
- Fechar browsers lançados pelo teste, se ainda existirem e forem do projeto.
- Continuar pelos tests de ownership antes de retomar features.

## Artefatos esperados

- Módulos de browser lifecycle.
- Tools de browser e tab lifecycle.
- Tests de registry e locks.
- Registro em `progress/`.

## Notas para o próximo agente

Não implemente navegação antes de lifecycle e ownership estarem confiáveis.
