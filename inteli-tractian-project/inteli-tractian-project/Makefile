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

.PHONY: help setup deps data agent-env up up-api up-agent up-all stop logs test clean clean-data

help: ## Mostra esta ajuda
	@echo   setup      - Cria venv, instala dependências e gera dados
	@echo   data       - Gera data/*.parquet, agent-input/, eval/
	@echo   up         - Sobe a API industrial em :8000
	@echo   stop       - Para a API e o agente
	@echo   test       - Roda os testes unitários da API

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

stop: ## Para API industrial e agente
	$(STOP_CMD)
	@echo "✓ Serviços parados."

test: ## Roda os testes da API industrial
	cd api && "$(PY)" -m pytest -q

clean-data: ## Apaga dados gerados (data/, agent-input/, eval/) — regenere com make data
	rm -rf data agent-input eval
	@echo "✓ dados apagados (rode make data para regenerar)"

clean: stop clean-data ## Para tudo e apaga dados + venv
	rm -rf api/.venv $(PID_DIR)
	@echo "✓ limpo"
