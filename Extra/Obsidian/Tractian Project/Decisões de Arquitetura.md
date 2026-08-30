---
tags: [architecture, adr, decision]
aliases: [Decisões, ADR, Depth Opportunity]
---

# Decisões de Arquitetura

## O que são ADRs
*Architecture Decision Records* — registros de **por que** decidimos algo, para não
re-litigar escolhas no futuro. Vivem em `docs/adr/`.

## Decisões tomadas
- **ADR-0001** — Camada MCP via FastMCP (agora `MCPServer`) como única interface
  agente → API. → [[Camada MCP - Tools]]

## Os 3 riscos identificados (e solução)
1. **Módulo raso na MCP** → [[Módulo Raso vs Profundo]] → helper central `client.py`.
2. **Política de incompletos sem dono** → [[Quality Check Node]] dedicado.
3. **Sem registros** → criar `CONTEXT.md` (glossário) + `docs/adr/`.

## Stack escolhida
→ [[Ferramentas e Stack]]
