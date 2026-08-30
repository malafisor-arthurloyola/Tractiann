---
tags: [architecture, quality, node]
aliases: [Quality Check, Nó de Qualidade]
---

# Quality Check Node

## O que é
Nó dedicado no [[Grafo LangGraph]] que decide o que fazer com respostas **não-completas**.
É o **dono único** dessa política.

## Decisões possíveis
- **aceitar** — resposta `complete` (ou `partial` com ressalva)
- **repetir** — buscar dado faltante
- **buscar dado faltante** — chamar outra tool
- **escalar** — quando `unavailable`/`conflict`

## Por que um nó só
Se a regra de "resposta incompleta" estivesse espalhada em vários nós, ela ficaria
inconsistente. Centralizar permite mudar a política num lugar só.

## Roteamento
```
quality_check → ok/partial → decide
             → incompleto → investigar (loop)
             → indisponível → escalar
```

## Relacionado
- [[Envelope de Resposta]]
- [[Grafo LangGraph]]
