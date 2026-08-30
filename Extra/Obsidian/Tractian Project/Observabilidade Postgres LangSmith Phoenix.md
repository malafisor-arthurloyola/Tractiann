---
tags: [observability, postgres, langsmith, phoenix]
aliases: [Observabilidade, LangSmith, Phoenix, Log]
---

# Observabilidade Postgres LangSmith Phoenix

## Três níveis de observabilidade

### Postgres — Log de execuções
Tabela `execucoes` com: ticket_id, agent_version, decision, quality_verdict,
data_gaps, trace JSON, created_at. Usa-se para comparar versões e métricas agregadas.

### LangSmith — Trace detalhado por chamada
Grava cada chamada ao LLM: prompt completo, output bruto, tokens, latência, custo.
Útil para debugar **por que** o LLM respondeu algo (ex: TKT-INV-11 reprocessar vs escalar).

### Phoenix (Arize) — Dashboard visual
Lê dos dois e cria visualizações: distribuição de decisões, comparação lado-a-lado
de versões, traces interativos.

## Conexão
```
Agente → Postgres (resumo) + LangSmith (trace) → Phoenix (dashboard)
```

## Relacionado
- [[Avaliação do Agente]]
- [[Grafo LangGraph]]
