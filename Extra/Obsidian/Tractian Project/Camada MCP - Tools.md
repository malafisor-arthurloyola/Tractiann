---
tags: [mcp, tools, architecture]
aliases: [MCP, Tools, Camada de Tools]
---

# Camada MCP - Tools

## O que é
A **camada de tools** expõe as operações da API industrial como tools via **MCP**
(Model Context Protocol). O agente se conecta ao servidor MCP, não direto à API.

## Como funciona hoje

```
nós do LangGraph
      ↓  call_tool("getBaseline", assetId=...)
agent/tools/mcp_client.py     ponte síncrona + span mcp.<tool> no Phoenix
      ↓  protocolo MCP sobre stdio
agent/tools/mcp_server.py     subprocesso: 18 tools
      ↓  agent/tools/client.py  (httpx: base URL, x-user-id, erro)
API industrial (:8000)
```

## Implementação
- **`agent/tools/mcp_server.py`** — 18 tools registradas via `MCPServer`. O bloco
  `__main__` roda `mcp.run(transport="stdio")`.
- **`agent/tools/mcp_client.py`** — sobe o servidor como subprocesso, faz o handshake e
  expõe `call_tool(nome, **args)` **síncrono**.
- **`agent/tools/client.py`** — helper `tractian_request`. Continua existindo, mas agora
  é detalhe interno **do servidor MCP**: nenhum nó do grafo o importa.

### A ponte síncrona
O SDK do MCP é assíncrono; os nós do LangGraph e o Streamlit são síncronos. O
`mcp_client` mantém um event loop num thread daemon e a **sessão é persistente** — o
subprocesso sobe uma vez e é reusado por toda a execução, em vez de um processo por tool.

### Ações via tool, não via URL
`ACTION_TOOLS` em `nodes.py` mapeia a decisão do agente para a tool MCP:

| action_type | tool MCP | parâmetro do alvo |
| :--- | :--- | :--- |
| `reprocess` | `reprocessAnalysis` | `analysisId` |
| `specialist` | `requestSpecialistAnalysis` | `analysisId` |
| `retrain` | `requestRetraining` | `modelId` |
| `update_config` | `updateAssetConfig` | `assetId` |
| `escalate` | `escalateCase` | `caseId` |

## Por que MCP
- **Padronização**: suportado por todos os agentes (Claude, LangChain, OpenCode).
- **Seam**: trocar de framework não reescreve as tools.
- **Testabilidade**: `python -m agent.tools.mcp_server` sobe as tools sem o agente.

## Tools de impacto (exigem justificação)
`updateAssetConfig`, `reprocessAnalysis`, `requestSpecialistAnalysis`,
`requestRetraining`, `escalateCase`. São as únicas que a API protege com
`require_permission` — os GETs não exigem `x-user-id`.

## Nota versão
MCP v2 renomeou `FastMCP` → `MCPServer`. Import: `from mcp.server.mcpserver import MCPServer`.

> [!warning] O que estava quebrado até 06/09/2026
> O servidor existia com as 18 tools, mas **nada o usava**. Três causas:
> o pacote `mcp` nunca era instalado (ver [[Ambiente e Reprodutibilidade]]);
> não havia bloco `__main__`, então rodá-lo como módulo encerrava sem subir servidor;
> e nenhum arquivo o importava — os nós chamavam `tractian_request` direto,
> contrariando o ADR-0001.

> [!tip] Custo de observabilidade
> A requisição HTTP acontece **dentro do subprocesso**, que não é instrumentado. Por
> isso o `mcp_client` emite o span `mcp.<tool>` com o modo do envelope. Sem ele a fase
> de investigação sumiria do Phoenix.

## Registro
- [[Decisões de Arquitetura]] (ADR-0001)
- [[Evidência Compensatória]]
- [[Ambiente e Reprodutibilidade]]
