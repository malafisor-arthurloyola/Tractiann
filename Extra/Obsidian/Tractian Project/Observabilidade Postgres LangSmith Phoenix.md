---
tags: [observability, postgres, langsmith, phoenix]
aliases: [Observabilidade, LangSmith, Phoenix, Log]
---

# Observabilidade Postgres e Phoenix

## Dois níveis de observabilidade

### Postgres — Log de execuções (resumo agregado)
Tabela `execucoes` com: ticket_id, agent_version, decision, quality_verdict,
data_gaps, trace JSON, created_at. Usa-se para **comparar versões** e métricas
agregadas.

**Por que é a fonte da comparação entre versões:**
- A coluna `agent_version` identifica a versão do agente (de `agent/version.py`, bump manual).
- `make compare versaoA versaoB` mostra a distribuição de decisões lado a lado.
- `make compare-versions` lista quantas execuções cada versão tem.

### Phoenix (Arize) — Trace detalhado por chamada (dashboard visual)
Substituto **gratuito e open source** da LangSmith (que é paga). Grava cada chamada
ao LLM: prompt completo, output bruto, tokens, latência, custo. Dashboard em :6006.

Útil para debugar **por que** o LLM respondeu algo (ex: TKT-INV-11 reprocessar vs
escalar) — é o "raio-X" do que entrou e saiu do modelo.

## Conexão
```
Agente → Postgres (resumo, comparação de versões)
       → Phoenix (trace detalhado, debugging)
```

## Como ativar
- Postgres: `make postgres-up` + `make postgres-init`
- Phoenix: `make phoenix-up` e setar `PHOENIX_ENABLED=1` em `agent/.env`

## Relacionado
- [[Avaliação do Agente]]
- [[Grafo LangGraph]]
- [[Human-in-the-loop]]
