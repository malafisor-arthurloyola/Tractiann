---
tags: [langgraph, graph, architecture]
aliases: [LangGraph, Grafo, Nodes]
---

# Grafo LangGraph

## O que é
Framework que orquestra o **loop** do agente: estado compartilhado + nós + arestas.
Cada "nó" é uma função que lê/escreve o estado.

## Nós do nosso agente
1. **investigate** — coleta dados da API via [[Camada MCP - Tools]].
2. **quality_check** — dono único da política de [[Envelope de Resposta]].
3. **decide** — usa o LLM (via [[Ferramentas e Stack]]) para escolher
   orientar/agir/escalar.
4. **respond / act / escalate** — executa a decisão.

## Estrutura de arquivos
- `agent/graph/state.py` — `AgentState` (Tipado, estado compartilhado).
- `agent/graph/nodes.py` — implementação dos nós.
- `agent/graph/agent.py` — montagem + `compile()`.

## Padrões usados
- **Roteamento condicional** — `add_conditional_edges` decide o próximo nó.
- **Estado tipado** — `TypedDict` para o estado.

## Conecta com
- [[Quality Check Node]]
- [[Módulo Raso vs Profundo]]
