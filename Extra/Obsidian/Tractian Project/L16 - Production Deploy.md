---
tags: [production, deploy, checkpointer, security, teach]
aliases: [Produção, Deploy, Postgres Checkpointer]
---

# L16 — Produção: Deploy, Segurança e Observabilidade

## Checkpointer: MemorySaver → Postgres — **implementado**

Deixou de ser recomendação e virou o padrão do projeto (`agent/graph/checkpointer.py`).
O `MemorySaver` sobrou só como fallback, e os testes o forçam com `CHECKPOINTER=memory`.

O motivo é mais forte do que "sobreviver a reinícios": com o estado na RAM, uma ação
pausada no `interrupt()` **só existe para o processo que a pausou**. A ingestão
(`make ingest`) pausa num processo e a interface Streamlit roda em outro — sem
persistência, a fila de aprovações da interface nasce vazia por construção, não por bug.

```python
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

# autocommit=True e row_factory=dict_row sao exigidos pelo PostgresSaver.
pool = ConnectionPool(conninfo=DATABASE_URL, open=False,
                      kwargs={"autocommit": True, "row_factory": dict_row})
pool.open(wait=True, timeout=5)   # falha rapido em vez de reconectar em background
saver = PostgresSaver(pool)
saver.setup()                     # cria as tabelas de checkpoint (idempotente)
graph = builder.compile(checkpointer=saver)
```

Dependências: `langgraph-checkpoint-postgres` e `psycopg[binary]` — sem o `[binary]`,
o psycopg 3 não acha a libpq no Windows e o checkpointer cai para memória em silêncio.

Retomar de outro processo precisa só do `thread_id`, que fica gravado em
`fila_aprovacoes`:

```python
agent_graph.invoke(Command(resume=True),
                   config={"configurable": {"thread_id": thread_id}})
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