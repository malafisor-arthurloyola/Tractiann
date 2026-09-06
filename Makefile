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
    # Venv ÚNICO na raiz: hospeda o agente (pyproject.toml da raiz) E a API
    # (api/pyproject.toml). Criado pelo uv, que baixa o interpretador certo —
    # o Python do sistema é 3.14 e as libs de tracing ainda não o suportam.
    PY := .venv\Scripts\python.exe
    UP_API_CMD = powershell -Command "Start-Process -FilePath '$(CURDIR)\.venv\Scripts\python.exe' -ArgumentList '-m uvicorn app.main:app --host 127.0.0.1 --port $(API_PORT)' -WorkingDirectory '$(CURDIR)\api' -WindowStyle Hidden"
    STOP_CMD = powershell -Command "Get-WmiObject Win32_Process -Filter \"name='python.exe'\" -ErrorAction SilentlyContinue | Where-Object { $$_.CommandLine -like '*uvicorn*' } | ForEach-Object { Stop-Process -Id $$_.ProcessId -Force -ErrorAction SilentlyContinue }"
else
    PYTHON ?= python3
    VENV := .venv
    PY := .venv/bin/python
    UP_API_CMD = cd api && $(PY) -m uvicorn app.main:app --host 127.0.0.1 --port $(API_PORT) > $(PID_DIR)/api.log 2>&1 & echo $$! > $(PID_DIR)/api.pid
    STOP_CMD = for f in $(PID_DIR)/api.pid $(PID_DIR)/agent.pid; do if [ -f $$f ]; then kill $$(cat $$f) 2>/dev/null; rm -f $$f; fi; done
endif

# Caminho absoluto do interpretador — necessário nos alvos que fazem `cd api`,
# onde o caminho relativo $(PY) deixaria de resolver.
PY_ABS := $(CURDIR)/.venv/Scripts/python.exe

.DEFAULT_GOAL := help

.PHONY: all help setup deps data agent-env up up-api up-agent up-all stop logs test clean clean-data postgres-up postgres-down postgres-init eval run phoenix-up phoenix-down up-obs compare compare-versions prova-final evolucao evolucao-md derivados demo

all: up-all ## Alias para up-all (sobe API + Streamlit)

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
	@echo   up-obs       - Sobe Postgres + Phoenix juntos (observabilidade)
	@echo   demo         - Prepara tudo e abre a plataforma pronta para demonstrar
	@echo   eval         - Roda avaliação no TREINO (sem juiz LLM) — dev
	@echo   run          - Roda avaliação no treino (com juiz LLM)
	@echo   prova-final  - Roda o TESTE held-out (generalização, com juiz)
	@echo   evolucao     - Tabela de evolução entre versões do agente

setup: deps data
	@echo "✓ Setup concluído!"

deps: ## Cria o venv da raiz e instala agente + API
	uv venv --python $(PYTHON)
	uv pip install -e .
	uv pip install -e "api/.[dev]"
	@echo "✓ dependências (agente + API) instaladas em $(VENV)"

data: ## Gera data/*.parquet, agent-input/, eval/
	cd api && "$(PY_ABS)" -m seed_data
	cd api && "$(PY_ABS)" -m package_material
	@echo "✓ dados gerados (data/, agent-input/, eval/)"

agent-env: ## Cria agent/.env a partir do .env.example (edite a API key depois)
	@if [ ! -f agent/.env ]; then cp agent/.env.example agent/.env && echo "✓ agent/.env criado — edite OPENAI_API_KEY/BASE_URL/MODEL"; else echo "✓ agent/.env já existe (não sobrescrito)"; fi

up: up-api ## Sobe a API industrial (:8000) em background
	@echo ""
	@echo "✓ API no ar:"
	@echo "   Swagger UI: http://localhost:$(API_PORT)/docs"

up-api: ## Só a API industrial (:8000) em background
	$(UP_API_CMD)
	@powershell -Command "Start-Sleep -Seconds 2"
	@echo "✓ API iniciada em background (:8000)"

demo: ## Prepara TUDO e abre a plataforma pronta para demonstrar
	@echo "1/4  API industrial"
	$(UP_API_CMD)
	@powershell -Command "Start-Sleep -Seconds 3"
	@echo "2/4  Postgres + Phoenix"
	docker compose up -d postgres-agent phoenix
	@powershell -Command "$$ok=$$false; for($$i=0;$$i -lt 40;$$i++){ try{ Invoke-WebRequest -Uri http://localhost:6006 -UseBasicParsing -TimeoutSec 2 | Out-Null; $$ok=$$true; break }catch{ Start-Sleep -Seconds 2 } }"
	$(PY) -c "from agent.logging.postgres import init_db; init_db()"
	@echo "3/4  Avaliacao (popula metricas, autonomia e traces no Phoenix)"
	$(PY) -m eval.runner --split train --no-judge
	@echo "4/4  Console Streamlit"
	@echo ""
	@echo "    A fila de aprovacoes vive na sessao do navegador — rodar por aqui nao a"
	@echo "    preenche. Na aba Aprovacoes ha um botao que processa so os tickets que"
	@echo "    exigem confirmacao (~40s), para demonstrar o HITL."
	@echo ""
	$(PY) -m streamlit run app.py

up-agent: ## Sobe a interface Streamlit (:8501)
	$(PY) -m streamlit run app.py

up-all: up-api ## Sobe a API e inicia o Streamlit
	@echo ""
	@echo "✓ Subindo interface do Agente (Streamlit :8501)..."
	@echo "   Se não abrir automaticamente, acesse http://localhost:8501"
	@echo ""
	$(PY) -m streamlit run app.py

stop: ## Para API industrial e agente
	$(STOP_CMD)
	@echo "✓ Serviços parados."

test: ## Roda os testes da API industrial
	cd api && "$(PY_ABS)" -m pytest -q

postgres-up: ## Sobe o Postgres do agente (:5432) via Docker
	docker compose up -d postgres-agent
	@echo "✓ Postgres no ar: postgresql://tractian:tractian_dev@localhost:5432/tractian_agent"

postgres-init: ## Cria a tabela execucoes no Postgres
	$(PY) -c "from agent.logging.postgres import init_db; print('tabela criada' if init_db() else 'FALHOU - Postgres indisponivel?')"

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

up-obs: ## Sobe a stack de observabilidade inteira (Postgres + tabela + Phoenix)
	docker compose up -d postgres-agent phoenix
	@echo "Aguardando o Phoenix aceitar traces..."
	@powershell -Command "$$ok=$$false; for($$i=0;$$i -lt 40;$$i++){ try{ Invoke-WebRequest -Uri http://localhost:6006 -UseBasicParsing -TimeoutSec 2 | Out-Null; $$ok=$$true; break }catch{ Start-Sleep -Seconds 2 } }; if($$ok){ Write-Host '  Phoenix pronto.' }else{ Write-Host '  AVISO: Phoenix nao respondeu em 80s.' }"
	$(PY) -c "from agent.logging.postgres import init_db; print('tabela execucoes: ok' if init_db() else 'FALHOU')"
	@echo "✓ Postgres :5432 e Phoenix :6006 no ar"
	@echo "  Phoenix persiste os traces no MESMO Postgres — sobrevivem a restart."
	@echo "  Lembra de setar PHOENIX_ENABLED=1 no agent/.env."

eval: ## Roda a avaliação NO TREINO (sem juiz LLM) — desenvolvimento
	$(PY) -m eval.runner --split train --no-judge

run: ## Roda a avaliação completa (com juiz LLM) no treino
	$(PY) -m eval.runner --split train

prova-final: ## Roda o TESTE held-out (prova de generalização) com juiz LLM
	$(PY) -m eval.runner --split test

compare: ## Compara decisões entre versões no Postgres (make compare versaoA versaoB)
	$(PY) -m eval.compare $(filter-out $@,$(MAKECMDGOALS))

derivados: ## Roda os cenarios DERIVADOS (construidos por mim) — reporte sempre separado
	$(PY) -m eval.runner --split derivados

evolucao: ## Tabela de evolução entre versões (acurácia + eixos do juiz)
	$(PY) -m eval.evolucao

evolucao-md: ## Mesma tabela em markdown, para colar na apresentação
	$(PY) -m eval.evolucao --md

compare-versions: ## Lista versões/contagens gravadas no Postgres
	$(PY) -m eval.compare --versions

clean-data: ## Apaga dados gerados (data/, agent-input/, eval/*-generated) — regenere com make data
	rm -rf data agent-input
	rm -f eval/expected-paths.json eval/test-scenarios.md eval/results*.json
	@echo "✓ dados apagados (rode make data para regenerar)"

clean: stop clean-data ## Para tudo e apaga dados + venv
	rm -rf $(VENV) $(PID_DIR)
	@echo "✓ limpo"
