---
tags: [domain, api]
aliases: [Envelope, Modo de Resposta]
---

# Envelope de Resposta

## O que é
Toda resposta de consulta da API vem num envelope com campos de **modo**:
`complete`, `partial`, `inconclusive`, `conflict`, `unavailable`.

## Regra de ouro
**O agente é quem decide** o que fazer com modos não-completos — **não a tool**.
A tool só entrega o envelope; o agente (via [[Quality Check Node]]) interpreta.

## Tratamento
- `complete` → segue
- `partial` → aceita com ressalva
- `inconclusive` / `conflict` / `unavailable` → repetir ou [[Escalamento]]
