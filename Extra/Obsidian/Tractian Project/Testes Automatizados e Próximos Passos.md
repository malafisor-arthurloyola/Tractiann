---
tags: [testing, pytest, evaluation]
aliases: [Testes Automatizados]
---

# Testes Automatizados e Próximos Passos

## Total: 71 testes
- 39 testes da API (api/tests/test_api.py)
- 32 testes do agente (tests/test_agent.py)

## Testes do agente (32 testes, ~2.5s)
- **TestRouteAfterQuality** (6): rotas ok/partial/unavailable/incomplete
- **TestRouteAfterDecide** (3): orient→respond, act→act, escalate→escalate
- **TestQualityCheck** (5): complete→ok, unavailable, empty→incomplete, partial
- **TestExtractAction** (4): keyword→action_type
- **TestBuildActionUrl** (5): action_type→endpoint
- **TestCacheKey** (3): invalidação por versão
- **TestExtractHelpers** (3): analyses list, first id
- **TestStateFields** (2): campos existem

## Split treino/teste
- **Treino (13 tickets)**: desenvolvimento e ajuste
- **Teste (4 tickets)**: held-out, só roda na "prova final"
- **Regra:** nunca ajustar o agente olhando o teste

## Comandos
- make eval (treino, sem juiz)
- make run (treino, com juiz)
- make prova-final (teste held-out)
- make compare v1 v2 (comparar versões)

## O que falta
- Streamlit UI (app.py não existe)
- Testes end-to-end (agent + API + Postgres juntos)
- Phoenix ativo em produção

## Relacionado
- [[Avaliação do Agente]]
- [[Auditoria e Bugs Críticos]]
- [[Correções no Grafo HITL Cache]]
