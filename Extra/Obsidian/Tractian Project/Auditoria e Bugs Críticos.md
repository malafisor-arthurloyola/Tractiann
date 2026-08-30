---
tags: [audit, architecture, bugs]
aliases: [Auditoria, Bugs Críticos]
---

# Auditoria e Bugs Críticos

## O que foi auditado
Todos os arquivos-chave do agente (agent/, eval/, api/), a compilação do grafo,
o venv, o fluxo de dados e o código morto.

## Bugs encontrados

### Críticos
- **act node nunca executava** — só fazia interrupt(), não chamava API
- **unavailable → decision=None** — route_after_quality pule o decide

### Altos
- **Cache sem invalidação** — prompt mudou mas cache antigo continuava
- **tools_called duplicava** — operator.add + lista inteira = entries duplicados
- **Trajectory assertions incompletas** — não cobria knowledge, models, POST

### Médios
- **Código morto** — tools.py antigo, is_within_trace, 5 campos dead no state
- **pyproject.toml ausente** — clone limpo = import error
- **env.example errado** — Makefile procurava .env.example mas arquivo era env.example

## Processo de auditoria
1. Leitura de todos os arquivos-chave
2. Testes de compilação e importação
3. Análise do venv e dependências
4. Trace do fluxo de dados e controle
5. grep/ls para código morto
6. Lista de bugs por severidade
7. Branch feature/fix-critical-issues
8. Correção em ordem de prioridade
9. Testes + merge na main

## Relacionado
- [[Correções no Grafo HITL Cache]]
- [[Ações Reais no Nó Act]]
- [[Testes Automatizados e Próximos Passos]]
