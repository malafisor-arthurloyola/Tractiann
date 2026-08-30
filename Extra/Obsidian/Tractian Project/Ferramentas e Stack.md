---
tags: [stack, tools, technology]
aliases: [Stack, Ferramentas, Tecnologias]
---

# Ferramentas e Stack

## Definitivo
| Camada | Stack |
| :--- | :--- |
| Orquestração | **LangGraph** (loop investigar→decidir, interrupt p/ HITL) |
| Camada tools | **MCP** (MCPServer v2) |
| Modelo | **Groq** `llama-3.3-70b` (com slot p/ OpenRouter futuro) |
| Apoio ao modelo | **LangChain** (dentro dos nós) |
| Observabilidade (futuro) | **LangSmith** (dev/trace) |
| Log de execuções (futuro) | **Postgres** |
| Avaliação | **pytest** + juiz LLM + runner determinístico |
| UI demo (futuro) | **Streamlit** |
| Dados | **pandas + Plotly** |
| Linguagem | **Python 3.11** (venv `api/.venv`) |

## Instalado
`mcp`, `httpx`, `langgraph`, `langchain-core`, `langchain-openai`.

## Nota
Modelo criado de forma **lazy** no `nodes.py` (`_get_llm()`) para o grafo compilar sem
API key.

## Relacionado
- [[Grafo LangGraph]]
- [[Camada MCP - Tools]]
