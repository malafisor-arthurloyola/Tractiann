---
tags: [domain, action]
aliases: [Escalamento, Escalar, Human-in-the-loop]
---

# Escalamento

## O que é
**Escalar** = encaminhar o caso para um **humano** quando o atendimento remoto não basta.

## Quando escalar (exemplos)
- Dados **indisponíveis** ou **conflitantes** (envelope `unavailable`/`conflict`).
- Baseline em `learning`/`invalidated` sem confiança.
- Ação de alto impacto sem permissão do perfil.

## Regra
Toda decisão de escalar deve explicar **por que** o caso extrapola o atendimento remoto
(instrumento: `justification`).

## Conecta
- [[Envelope de Resposta]]
- [[Quality Check Node]]
- [[Grafo LangGraph]]
