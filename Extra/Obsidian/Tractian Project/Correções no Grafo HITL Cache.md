---
tags: [graph, langgraph, hitl, cache]
aliases: [Correções no Grafo, HITL, Cache]
---

# Correções no Grafo, HITL e Cache

## Correção 1: route_after_quality
- ANTES: unavailable → escalate (pule o decide) = decision=None
- DEPOIS: unavailable → decide (decide define escalate com justificativa)

## Correção 2: tools_called merge bug
- ANTES: investigate retornava lista inteira + operator.add = duplicatas
- DEPOIS: retorna só os NOVOS tools da passada

## Correção 3: Cache com invalidação
- Chave = hash(AGENT_VERSION + contexto)
- Bump manual em agent/version.py invalida o cache

## Correção 4: Nó act com ações reais
- interrupt() → HITL → tractian_request(POST/PATCH)
- Tipos: reprocess, specialist, retrain, update_config

## Estrutura AgentState
Req: ticket_id, case_id, company_id, user_id, asset_id, message
Coleta: raw, quality_verdict, data_gaps, next_tool, tools_called
Decisão: decision, decision_justification, action_type, action_target
Resultado: response, trace

## Relacionado
- [[Grafo LangGraph]]
- [[Human-in-the-loop]]
- [[Auditoria e Bugs Críticos]]
- [[Ações Reais no Nó Act]]
