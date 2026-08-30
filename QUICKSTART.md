# Quickstart — Tractian Agent (Inteli × TRACTIAN)

Como executar o projeto completo: API Industrial + Agente IA + Observabilidade + UI.

---

## Requisitos

- **Python ≥ 3.11** (usado via `uv`)
- **Docker Desktop** (para Postgres + Phoenix)
- **uv** (gerenciador rápido de pacotes): `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Make** (GnuWin32 no Windows já incluído no PATH do projeto)

---

## 1. Setup Inicial (uma vez só)

```bash
make setup
# Cria venv (.venv/), instala dependências da API e do agente, gera dados sintéticos
# Gera: data/*.parquet, agent-input/cases.json, eval/expected-paths.json, eval/split.json
```

> **Dica:** Se já rodou antes e quer limpar tudo: `make clean` e depois `make setup`.

---

## 2. Subir a Stack Completa

### Opção A: Tudo junto (recomendado para desenvolvimento)
```bash
make up-all
# Sobe: API Industrial (:8000) + Streamlit UI (:8501) + Postgres (:5432) + Phoenix (:6006)
```

### Opção B: Serviços individuais
```bash
# API Industrial (obrigatória para o agente funcionar)
make up              # Sobe API em http://localhost:8000
# Swagger UI: http://localhost:8000/docs

# Streamlit Console (interface do agente)
make ui              # Sobe Streamlit em http://localhost:8501

# PostgreSQL (logging de execuções + comparação de versões)
make postgres-up     # Sobe container postgres-agent
make postgres-init   # Cria tabela `execucoes`

# Phoenix Tracing (observabilidade open-source, substitui LangSmith)
make phoenix-up      # Dashboard em http://localhost:6006
# IMPORTANTE: Set PHOENIX_ENABLED=1 no agent/.env para instrumentar traces
```

---

## 3. Verificar Saúde dos Serviços

A UI Streamlit (`make ui`) mostra badges no header:
- 🟢 **API Online** — Industrial API respondendo
- 🔵 **Postgres Conectado** — Logging de execuções ativo
- 🟣 **Phoenix Ativo** — Tracing de LLM disponível
- 🟠 **LLM Configurado** — Groq/OpenRouter/OpenAI com modelo válido

Ou via terminal:
```bash
# Health checks rápidos
curl http://localhost:8000/companies/comp_mineracao_andes
docker ps | grep -E "postgres|phoenix"
curl http://localhost:6006
```

---

## 4. Acessar PostgreSQL (Dados do Agente)

### Via CLI (psql)
```bash
# Conectar no container
docker exec -it tractian-agent-postgres psql -U tractian -d tractian_agent

# Queries úteis dentro do psql:
SELECT * FROM execucoes ORDER BY created_at DESC LIMIT 10;
SELECT agent_version, decision, COUNT(*) FROM execucoes GROUP BY agent_version, decision;
\q  # sair
```

### Via Python (programático)
```python
from agent.logging.postgres import count_by_version, compare_versions, _get_connection

# Contagem por versão
count_by_version()
# {'v1': 42, 'v2': 15}

# Comparar v1 vs v2
compare_versions("v1", "v2")
# [{'decision': 'orient', 'quality_verdict': 'ok', 'v_a': 20, 'v_b': 8}, ...]

# Conexão raw
conn = _get_connection()
cur = conn.cursor()
cur.execute("SELECT * FROM execucoes WHERE decision='escalate'")
cur.fetchall()
```

### Via Make
```bash
make compare-versions    # Lista versões e contagens
make compare v1 v2       # Compara distribuição de decisões entre v1 e v2
```

---

## 5. Acessar Phoenix (Tracing de LLM)

**Dashboard Web:** http://localhost:6006

### O que você vê lá:
- **Traces completos** de cada execução do agente
- **Prompts enviados** ao LLM (input completo)
- **Respostas brutas** do LLM (antes do parse)
- **Tokens usados**, latência, custo estimado
- **Spans por nó** do LangGraph (investigate → quality_check → decide → act/respond/escalate)

### Ativar instrumentação:
```bash
# Edite agent/.env
PHOENIX_ENABLED=1
PHOENIX_ENDPOINT=http://localhost:6006

# Reinicie a UI/API se necessário
make ui
```

### Útil para debug:
- Por que o agente escalou o TKT-INV-11?
- Quantos tokens gastou na investigação?
- O prompt incluía os gaps corretos?

---

## 5. Comandos de Avaliação & Testes

```bash
# Avaliação no TREINO (13 tickets, sem juiz LLM = rápido)
make eval
# ou: make run          # Com juiz LLM (mais lento, usa API)

# Avaliação no TESTE held-out (4 tickets, generalização)
make prova-final

# Testes unitários do agente (32 testes, sem LLM, ~2s)
.\api\.venv\Scripts\python.exe -m pytest tests/test_agent.py -v

# Testes da API Industrial (39 testes)
make test
# ou: cd api && .venv\Scripts\python.exe -m pytest -q
```

**Total: 71 testes** (32 agente + 39 API)

---

## 6. Versionamento do Agente (Cache Invalidation)

O cache do LLM usa `AGENT_VERSION` como parte da chave. Para invalidar cache e forçar re-avaliação:

```bash
# Edite agent/version.py
AGENT_VERSION = "v2"  # ou v3, v4...

# Ou via Python:
from agent.version import AGENT_VERSION
print(AGENT_VERSION)  # v1
```

> **Regra:** Sempre que mudar lógica do grafo, prompts ou tools → bump a versão.

---

## 7. Parar Tudo

```bash
make stop         # Para API + Agent (processos Python)
make postgres-down  # Para Postgres
make phoenix-down   # Para Phoenix
# Ou tudo de uma vez:
make clean        # Para tudo + apaga venv + dados gerados
```

---

## 8. Estrutura de Pastas (Resumo)

```
Tractiann/
├── app.py                    # Streamlit UI (make ui)
├── api/                      # API Industrial (FastAPI)
│   ├── app/main.py           # 5 endpoints de mutação (reprocess, specialist, retrain, update_config, escalate)
│   └── seed_data.py          # Gera dados sintéticos
├── agent/                    # Agente IA (LangGraph)
│   ├── graph/                # Nós, Estado, Grafo compilado
│   ├── logging/              # Postgres + Phoenix
│   ├── tools/                # 17 MCP tools (wrappers da API)
│   └── version.py            # AGENT_VERSION para cache
├── eval/                     # Avaliação
│   ├── runner.py             # run_graph, run_all, split train/test
│   ├── assertions/           # Trajectory + LLM Judge
│   └── split.json            # 13 train / 4 test (held-out)
├── agent-input/cases.json    # 17 tickets de entrada
├── docker-compose.yml        # Postgres + Phoenix
├── Makefile                  # Todos os comandos acima
├── pyproject.toml            # Deps do agente
└── Extra/learning/lessons/   # Aulas Teach (L1-L12)
```

---

## 9. Próximos Passos Recomendados

| Objetivo | Comando / Arquivo |
|----------|-------------------|
| Entender domínio (Ativo, Baseline, Insight, Envelope) | `CONTEXT.md` |
| Ver arquitetura do grafo (nós, HITL, cache) | `Extra/learning/lessons/0010-graph-fixes.html` |
| Ver infraestrutura (Docker, Postgres, Phoenix) | `Extra/learning/lessons/0011-docker-postgres-observability.html` |
| Ver testes e avaliação | `Extra/learning/lessons/0012-testing-and-next.html` |
| Customizar agente | `agent/graph/nodes.py`, `agent/graph/state.py` |
| Adicionar nova tool MCP | `agent/tools/` + registrar em `agent/graph/nodes.py` |
| Ver decisões no Postgres | `make compare-versions` ou `make compare v1 v2` |
| Debug de LLM | `make phoenix-up` + `PHOENIX_ENABLED=1` |

---

## Erros Comuns & Fixes

| Erro | Causa | Solução |
|------|-------|---------|
| `make: *** No rule to make target` | Rodou `make` fora da raiz | `cd Tractiann && make ...` |
| `uv: command not found` | uv não instalado | Instale uv + reabra terminal |
| `ModuleNotFoundError: agent` | PYTHONPATH errado | Rode `make setup` ou use `make ui`/`make eval` |
| `Connection refused: localhost:5432` | Postgres não subiu | `make postgres-up && make postgres-init` |
| `Phoenix shows no traces` | PHOENIX_ENABLED=0 | Edite `agent/.env` → `PHOENIX_ENABLED=1` |
| `seed=complete` não funciona | Parâmetro só existe em endpoints GET | Use Swagger UI ou `curl '...?seed=complete'` |

---

## Links Rápidos

| Serviço | URL | Credenciais |
|---------|-----|-------------|
| **Streamlit Console** | http://localhost:8501 | — |
| **API Industrial (Swagger)** | http://localhost:8000/docs | — |
| **Phoenix Tracing** | http://localhost:6006 | — |
| **PostgreSQL** | localhost:5432 | user: `tractian`, pass: `tractian_dev`, db: `tractian_agent` |

---

> **Dica de Ouro:** Abra 3 terminais: (1) `make up` (API), (2) `make ui` (Streamlit), (3) livre para `make eval`, `make compare`, logs, etc.