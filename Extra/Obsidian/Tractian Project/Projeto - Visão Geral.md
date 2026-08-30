---
tags: [project, overview]
aliases: [Visão Geral, O que é o projeto]
---

# Projeto - Visão Geral

## O que é
Challenge **TRACTIAN × Inteli** — construir e avaliar um **agente de IA industrial** que
recebe tickets de suporte e decide entre **orientar**, **agir** ou **escalar**.

## Objetivo
Agente se conecta a uma API industrial (`18 endpoints`), investiga dados de ativos e
responde/escala chamados. Entrega final: **08/09/2026**.

## Duas partes
1. **Construção do agente** — tools MCP + grafo [[Grafo LangGraph]].
2. **Avaliação** — medir qualidade e confiabilidade (harness).

## Pergunta norteadora
Como construir/avaliar agentes que usam sistemas industriais com precisão, interpretam
evidências e executam ações seguras?

## Estado atual (ago/2026)
- ✅ [[Camada MCP - Tools]] (18 tools)
- ✅ [[Grafo LangGraph]] esqueleto
- ⏳ Harness de avaliação
- ⏳ [[Postgres Log]] e Streamlit (pós-core)

## Notas relacionadas
- [[Arquitetura do Agente]]
- [[Domínio Industrial Tractian]]
