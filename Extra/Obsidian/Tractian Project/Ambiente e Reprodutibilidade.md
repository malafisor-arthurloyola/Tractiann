---
tags: [infra, setup, reprodutibilidade]
aliases: [Venv, Ambiente, Setup, Reprodutibilidade]
---

# Ambiente e Reprodutibilidade

## O problema

O projeto tinha **dois** `pyproject.toml` (raiz para o agente, `api/` para a API
industrial) mas **um só** venv — e o `make deps` instalava apenas o da API:

```make
deps:
	C:\Python314\python.exe -m venv api\.venv --clear
	api\.venv\Scripts\python.exe -m pip install -e "api\.[dev]"
```

Consequências:

- As dependências do agente (`opentelemetry-*`, `openinference-*`, `mcp`) **nunca eram
  instaladas**. É a causa raiz de o [[Observabilidade Postgres LangSmith Phoenix|Phoenix nunca ter gerado um trace]].
- `langgraph`, `streamlit`, `psycopg2` só existiam porque alguém os instalou à mão.
  Um clone limpo + `make setup` produzia um ambiente que não roda o agente.
- O venv da API hospedando o agente é confuso conceitualmente: `make eval` rodava
  `api\.venv\Scripts\python.exe -m eval.runner`.

## A solução: venv único na raiz

```make
deps:
	uv venv --python 3.11
	uv pip install -e .
	uv pip install -e "api/.[dev]"
```

Um ambiente só, hospedando agente **e** API, com ambos os `pyproject.toml` instalados.
Todos os alvos do Makefile passaram a usar `$(PY) = .venv\Scripts\python.exe`.

## A armadilha da versão do Python

O Python do sistema nesta máquina é **3.14**, e as bibliotecas de instrumentação ainda
não o suportam:

```
ERROR: Ignored the following versions that require a different python version:
  ... Requires-Python >=3.9,<3.14
```

Por isso o `deps` delega ao `uv`, que baixa e fixa a versão certa. O comentário antigo
no Makefile dizia que o `uv` estava bloqueado por AppLocker — **estava obsoleto**,
`uv venv --python 3.11` funciona normalmente.

> [!tip] Use 3.11 ou 3.12
> Não vá para 3.13+ enquanto o ecossistema OpenInference/Phoenix não acompanhar.

## Nota sobre nomes de pacote

`openinference-instrumentation-httpx` **não existe**. O OpenInference cobre frameworks
de LLM (langchain, openai, llamaindex); clientes HTTP são cobertos pelo OpenTelemetry
padrão — o pacote certo é `opentelemetry-instrumentation-httpx`.

## Coleta de testes

`test_agent.py` na **raiz** não é uma suíte de teste: é um script ad-hoc que executa o
agente inteiro no import. O pytest o coletaria (e o executaria) ao rodar da raiz. O
`pyproject.toml` agora restringe a coleta:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

É candidato a remoção — `eval/runner.py` faz estritamente mais.

## Relacionado
- [[Observabilidade Postgres LangSmith Phoenix]]
- [[Docker Postgres Observabilidade Detalhes]]
- [[Ferramentas e Stack]]
- [[Testes Automatizados e Próximos Passos]]
