---
tags: [production, deploy, checkpointer, security, teach]
aliases: [Produção, Deploy, Postgres Checkpointer]
---

# L16 — Produção: Deploy, Segurança e Observabilidade

## Checkpointer: MemorySaver → Postgres
- Dev: `MemorySaver` (RAM)
- Prod: **Obrigatório** `PostgresSaver` (LangGraph) para persistir HITL entre reinícios

```python
from langgraph.checkpoint.postgres import PostgresSaver
with PostgresSaver.from_conn_string(DATABASE_URL) as checkpointer:
    graph = builder.compile(checkpointer=checkpointer)
```

## Segurança
- **Secrets:** Nunca commit `agent/.env` — use variáveis de ambiente no CI/CD
- **Rate Limits:** Respeite limites da API Industrial e Groq/OpenRouter
- **Permissões:** Ações `action_high` (retrain, update_config) exigem roles específicas

## Monitoramento Contínuo
- **Phoenix:** Dashboards de latência, tokens, erros de parsing
- **Postgres:** `make compare-versions` semanal para detectar regressão
- **Alertas:** Se `escalate` rate > 20%, investigar

## CI/CD Sugerido
```yaml
# GitHub Actions
- make setup
- make test
- make eval --split train
- bump AGENT_VERSION (se passou)
- deploy container
```

## Versionamento Semântico do Agente
| Versão | Quando Bumpar |
|---|---|
| Patch (v1.0.1) | Bug fix em tool / prompt |
| Minor (v1.1.0) | Nova tool / action de leitura |
| Major (v2.0.0) | Mudança de grafo / decisão / baseline logic |

## Relacionado
- [[Docker Postgres Observabilidade Detalhes]]
- [[L15 - Extensibility]]
- [[Observabilidade Postgres LangSmith Phoenix]]