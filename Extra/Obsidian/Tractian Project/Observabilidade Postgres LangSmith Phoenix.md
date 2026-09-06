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

## O episódio: o Phoenix nunca gerou um único trace

> [!bug] Descoberto na auditoria de observabilidade
> Durante semanas o projeto acreditou ter tracing. Não tinha. Nenhum span jamais saiu.

Três falhas independentes, empilhadas:

1. **As dependências nunca foram instaladas.** O `make deps` rodava só
   `pip install -e "api/.[dev]"`. O `pyproject.toml` da raiz — onde `opentelemetry-*`
   e `openinference-*` estavam declarados — nunca era instalado. Ver [[Ambiente e Reprodutibilidade]].
2. **A falha era silenciosa.** `setup_phoenix_tracing()` engolia o `ImportError` num
   `except Exception`, imprimia uma linha discreta e devolvia `False`. Falha silenciosa
   aqui é indistinguível de "não há o que tracear" — foi assim que passou despercebido.
   Hoje o módulo **levanta `RuntimeError`** quando `PHOENIX_ENABLED=1` e algo quebra.
3. **A UI nunca instrumentava.** `app.py` chamava `agent_graph.invoke` cru, sem
   `run_in_phoenix_trace`. A demo final não geraria trace mesmo com tudo instalado.

## O que mudou

| antes | depois |
| :--- | :--- |
| wiring manual de `TracerProvider` + `BatchSpanProcessor` + `OTLPSpanExporter` | uma chamada a `phoenix.otel.register()` |
| só LangChain instrumentado | LangChain **+ httpx** — as chamadas à API industrial ficam visíveis |
| `service.name` fixo | projeto versionado `tractian-agent-{AGENT_VERSION}` — comparação de versões dentro do dashboard |
| spans perdidos ao fim de `make eval` | `atexit` + `force_flush()` explícito no runner |
| nós sem atributos | `quality.verdict`, `evidence.usable`, `decision`, `cache.hit`, `envelope.mode.<categoria>` |
| falha muda | erro alto, com a causa e o comando para corrigir |

### Persistência
O `docker-compose.yml` montava `phoenix_data:/data` mas não definia `PHOENIX_WORKING_DIR`
— o Phoenix gravava em `/root/.phoenix`, **fora do volume**, e perdia tudo no restart.
Hoje ele persiste no **mesmo Postgres** da tabela `execucoes`, em schema `phoenix`:

```yaml
PHOENIX_SQL_DATABASE_URL: postgresql://tractian:tractian_dev@postgres-agent:5432/tractian_agent
PHOENIX_SQL_DATABASE_SCHEMA: phoenix
PHOENIX_WORKING_DIR: /data
```

Vantagem colateral: traces e execuções no mesmo banco dá para cruzar em SQL.

## O cache que apagava o LLM do trace
O cache de decisões em disco retorna **antes** de `_get_llm()`. Quando bate cache não
há chamada de LLM — e portanto nenhum span de LLM, nenhum token, nenhuma latência.
Como o contexto é determinístico, a partir da 2ª execução *todo* ticket batia cache.

Hoje o hit aparece como atributo `cache.hit` no span, e a medição de custo/latência
da entrega final roda com `--no-cache`.

## Conexão
```
Agente → Postgres (resumo, comparação de versões)
       → Phoenix  (trace detalhado: HTTP + nós + LLM)
```

## Como ativar
```bash
make up-obs                    # Postgres + Phoenix + tabela execucoes
# agent/.env → PHOENIX_ENABLED=1
```

## Relacionado
- [[Avaliação do Agente]]
- [[Ambiente e Reprodutibilidade]]
- [[Grafo LangGraph]]
- [[Auditoria e Bugs Críticos]]
