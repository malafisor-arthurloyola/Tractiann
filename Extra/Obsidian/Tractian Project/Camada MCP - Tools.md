---
tags: [mcp, tools, architecture]
aliases: [MCP, Tools, Camada de Tools]
---

# Camada MCP - Tools

## O que é
A **camada de tools** expõe as operações da API industrial como tools via **MCP**
(Model Context Protocol). O agente se conecta ao servidor MCP, não direto à API.

## Implementação
- **`agent/tools/client.py`** — helper central `tractian_request`. Resolve o problema
  de [[Módulo Raso vs Profundo]]: a chamada HTTP + headers + envelope centralizada.
- **`agent/tools/mcp_server.py`** — **18 tools** registradas via `MCPServer` (API v2,
  antigo `FastMCP`).

## Por que MCP
- **Padronização**: suportado por todos os agentes (Claude, LangChain, OpenCode).
- **Seam**: trocar de framework não reescreve as tools.
- **Testabilidade**: cada tool testa isolada.

## Tools de impacto (exigem justificação)
`updateAssetConfig`, `reprocessAnalysis`, `requestSpecialistAnalysis`,
`requestRetraining`, `escalateCase`.

## Nota versão
MCP v2 renomeou `FastMCP` → `MCPServer`. Import: `from mcp.server.mcpserver import MCPServer`.

## Registro
- [[Decisões de Arquitetura]] (ADR-0001)
