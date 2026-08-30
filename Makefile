# Makefile — Challenge TRACTIAN x Inteli
# Sobe tudo que você precisa para testar o agente de ponta a ponta.

API_PORT ?= 8000
AGENT_PORT ?= 8001
ROOT := .
PID_DIR := $(ROOT)/.run
MAKEFLAGS += --no-print-directory

ifeq ($(OS),Windows_NT)
    PYTHON ?= 3.11
    VENV := .venv
    PY := .venv\Scripts\python.exe
    UP_API_CMD = powershell -Command "Start-Process -FilePath '.venv\Scripts\python.exe' -ArgumentList '-m uvicorn app.main:app --host 127.0.0.1 --port $(API_PORT)' -WorkingDirectory 'api' -WindowStyle Hidden"
    STOP_CMD = powershell -Command "Get-WmiObject Win32_Process -Filter \"name='python.exe'\" -ErrorAction SilentlyContinue | Where-Object { $$_.CommandLine -like '*uvicorn*' } | ForEach-Object { Stop-Process -Id $$_.ProcessId -Force -ErrorAction SilentlyContinue }"
else
    PYTHON ?= python3
    VENV := .venv
    PY := .venv/bin/python
    UP_API_CMD = cd api && $(PY) -m uvicorn app.main:app --host 127.0.0.1 --port $(API_PORT) > $(PID_DIR)/api.log 2>&1 & echo $$! > $(PID_DIR)/api.pid
    STOP_CMD = for f in $(PID_DIR)/api.pid $(PID_DIR)/agent.pid; do if [ -f $$f ]; then kill $$(cat $$f) 2>/dev/null; rm -f $$f; fi; done
endif

.DEFAULT_GOAL := help

.PHONY: help setup deps data agent-env up up-api up-agent up-all stop logs test clean clean-data postgres-up postgres-down postgres-init eval run phoenix-up phoenix-down

help: ## Mostra esta ajuda
	@echo   setup        - Cria venv, instala dependências e gera dados
	@echo   data         - Gera data/*.parquet, agent-input/, eval/
	@echo   up           - Sobe a API industrial em :8000
	@echo   stop         - Para a API e o agente
	@echo   test         - Roda os testes unitários da API
	@echo   postgres-up  - Sobe o Postgres do agente (:5432)
	@echo   postgres-init- Cria a tabela execucoes no Postgres
	@echo   postgres-down- Para o Postgres do agente
	@echo   phoenix-up   - Sobe o Phoenix (tracing open source) :6006
	@echo   phoenix-down - Para o Phoenix
	@echo   eval         - Roda avaliação no TREINO (sem juiz LLM) — dev
	@echo   run          - Roda avaliação no treino (com juiz LLM)
	@echo   prova-final  - Roda o TESTE held-out (generalização, com juiz)

setup: deps data
	@echo "✓ Setup concluído!"

deps: ## Cria o venv e instala dependências da API
	cd api && uv venv --allow-existing --python $(PYTHON) .venv && uv pip install -e ".[dev]"
	@echo "✓ dependências instaladas em $(VENV)"

data: ## Gera data/*.parquet, agent-input/, eval/
	cd api && "$(PY)" -m seed_data
	cd api && "$(PY)" -m package_material
	@echo "✓ dados gerados (data/, agent-input/, eval/)"

agent-env: ## Cria agent/.env a partir do .env.example (edite a API key depois)
	@if [ ! -f agent/.env ]; then cp agent/.env.example agent/.env && echo "✓ agent/.env criado — edite OPENAI_API_KEY/BASE_URL/MODEL"; else echo "✓ agent/.env já existe (não sobrescrito)"; fi

up: up-api ## Sobe a API industrial (:8000) em background
	@echo ""
	@echo "✓ API no ar:"
	@echo "   Swagger UI: http://localhost:$(API_PORT)/docs"

up-api: ## Só a API industrial (:8000) em background
	$(UP_API_CMD)

up-agent: ## Sobe a interface Streamlit (:8501)
	api\.venv\Scripts\python.exe -m streamlit run app.py

up-all: up-api ## Sobe a API e inicia o Streamlit
	@echo "✓ Subindo interface do Agente..."
	api\.venv\Scripts\python.exe -m streamlit run app.py

stop: ## Para API industrial e agente
	$(STOP_CMD)
	@echo "✓ Serviços parados."

test: ## Roda os testes da API industrial
	cd api && "$(PY)" -m pytest -q

postgres-up: ## Sobe o Postgres do agente (:5432) via Docker
	docker compose up -d postgres-agent
	@echo "✓ Postgres no ar: postgresql://tractian:tractian_dev@localhost:5432/tractian_agent"

postgres-init: ## Cria a tabela execucoes no Postgres
	api\.venv\Scripts\python.exe -c "from agent.logging.postgres import init_db; print('tabela criada' if init_db() else 'FALHOU - Postgres indisponivel?')"

postgres-down: ## Para o Postgres do agente
	docker compose stop postgres-agent
	@echo "✓ Postgres parado."

phoenix-up: ## Sobe o Phoenix (tracing open source) :6006 via Docker
	docker compose up -d phoenix
	@echo "✓ Phoenix no ar: http://localhost:6006 (dashboard de tracing)"
	@echo "  Lembra de setar PHOENIX_ENABLED=1 no agent/.env para instrumentar."

phoenix-down: ## Para o Phoenix
	docker compose stop phoenix
	@echo "✓ Phoenix parado."

eval: ## Roda a avaliação NO TREINO (sem juiz LLM) — desenvolvimento
	api\.venv\Scripts\python.exe -m eval.runner --split train --no-judge

run: ## Roda a avaliação completa (com juiz LLM) no treino
	api\.venv\Scripts\python.exe -m eval.runner --split train

prova-final: ## Roda o TESTE held-out (prova de generalização) com juiz LLM
	api\.venv\Scripts\python.exe -m eval.runner --split test

compare: ## Compara decisões entre versões no Postgres (make compare versaoA versaoB)
	api\.venv\Scripts\python.exe -m eval.compare $(filter-out $@,$(MAKECMDGOALS))

compare-versions: ## Lista versões/contagens gravadas no Postgres
	api\.venv\Scripts\python.exe -m eval.compare --versions

clean-data: ## Apaga dados gerados (data/, agent-input/, eval/*-generated) — regenere com make data
	rm -rf data agent-input
	rm -f eval/expected-paths.json eval/test-scenarios.md eval/results*.json
	@echo "✓ dados apagados (rode make data para regenerar)"

clean: stop clean-data ## Para tudo e apaga dados + venv
	rm -rf api/.venv $(PID_DIR)
	@echo "✓ limpo"
