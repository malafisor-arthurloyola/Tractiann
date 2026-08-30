---
tags: [docker, postgres, observability]
aliases: [Docker, Postgres, Phoenix detalhes]
---

# Docker, Postgres e Observabilidade (Detalhes)

## Docker
Encapsula serviços isolados. No docker-compose.yml:
- postgres-agent: postgres:16-alpine :5432
- phoenix: arizephoenix/phoenix, dashboard :6006

## Comandos
- make up — sobe Postgres + Phoenix
- make postgres-init — cria tabela execucoes
- make phoenix-up — sobe Phoenix
- make compare v1 v2 — compara versões
- make compare-versions — lista versões/contagens

## Configuração de produção
- **MemorySaver**: desenvolvimento. **Postgres checkpointer**: produção (persiste HITL)
- degrade-safe: sem Postgres, log_execution retorna False silenciosamente

## Phoenix (open source, substitui LangSmith pago)
- guarda cada chamada ao LLM (prompt, output, tokens, latência)
- via opentelemetry + LangChainInstrumentor
- ativa com PHOENIX_ENABLED=1

## Relacionado
- [[Observabilidade Postgres LangSmith Phoenix]]
- [[Camada MCP - Tools]]
- [[Avaliação do Agente]]
