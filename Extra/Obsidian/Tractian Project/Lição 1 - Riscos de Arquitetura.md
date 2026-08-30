---
tags: [learning, lesson, architecture]
aliases: [Lição 1, Riscos de Arquitetura]
---

# Lição 1 - Riscos de Arquitetura

> Nota resumo da lição criada pela skill **Teach**. A versão "completa" (HTML interativo)
> vive em `Extra/learning/lessons/0001-architecture-risks.html`.

## Os 3 riscos da nossa arquitetura

### 1. Camada MCP rasa → [[Módulo Raso vs Profundo]]
17+ tools repetindo a mesma chamada HTTP + envelope. **Fix**: helper central `client.py`.

### 2. Política de incompletos sem dono → [[Quality Check Node]]
Regra de [[Envelope de Resposta]] precisava de **um nó dono**, senão se espalhava.

### 3. Sem registros → [[Decisões de Arquitetura]]
Faltava glossário (`CONTEXT.md`) + ADRs (`docs/adr/`).

## Fixação (retrieval practice)
1. O que é um módulo raso?
2. Onde a regra de resposta incompleta deve morar?
3. Diferença entre `CONTEXT.md` e um ADR?

## Relacionado
- [[Aprendizado - Missão]]
- [[Arquitetura do Agente]]
