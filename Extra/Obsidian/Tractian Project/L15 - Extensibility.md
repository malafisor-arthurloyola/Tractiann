---
tags: [extensibility, tools, actions, teach]
aliases: [Extensibilidade, Novas Tools]
---

# L15 — Extensibilidade: Novas Tools e Ações

## Nova Tool de Leitura (GET)
1. Criar `agent/tools/nova_tool.py` com `async def fetch_nova(...) -> dict`
2. Registrar em `agent/tools/__init__.py`
3. Adicionar caso no nó `investigate` em `agent/graph/nodes.py`
4. Testar: `make eval --split train`

## Nova Ação de Impacto (POST/PATCH)
1. Adicionar endpoint na API (`api/app/main.py`)
2. Criar tool em `agent/tools/acao_nova.py`
3. Atualizar `_extract_action()` em `nodes.py` (palavras-chave)
4. Adicionar URL em `_build_action_url()`
5. Testar HITL na UI Streamlit

## Novo Nó no Grafo
1. Criar função em `nodes.py`
2. Adicionar nó no `agent/graph/agent.py`
3. Atualizar arestas/rotas condicionais

## Relacionado
- [[Grafo LangGraph]]
- [[Ações Reais no Nó Act]]
- [[L14 - API and MCP Tools]]
- [[L16 - Production Deploy]]