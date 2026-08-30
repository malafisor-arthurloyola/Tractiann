---
tags: [evaluation, testing, judge-llm]
aliases: [Avaliação, Juiz LLM, Métricas, Eval]
---

# Avaliação do Agente

## Duas dimensões
1. **Determinística** (pytest): o agente fez as chamadas certas à API, na ordem certa?
   Compara trace vs `eval/expected-paths.json`.
2. **Subjetiva** (juiz LLM): a resposta é clara, honesta, fundamentada?
   O LLM simula o que um engenheiro humano pensaria.

## Métricas principais
| Métrica | Tipo |
| :--- | :--- |
| Acurácia da causa-raiz | Determinística |
| Uso de evidências | Determinística |
| Honestidade sob incerteza | Subjetiva |
| Taxa de over-escalation | Determinística |
| Taxa de under-escalation | Determinística |
| Qualidade da justificativa | Subjetiva |
| Consistência (5x mesmo ticket) | Determinística |

## Exemplo real
TKT-INV-11: avaliação determinística PASSOU (chamadas corretas),
avaliação subjetiva FALHOU (decidiu reprocessar em vez de escalar,
sem dado suficiente). Sem as duas, só veríamos uma metade.

## Relacionado
- [[Grafo LangGraph]]
- [[Quality Check Node]]
- [[Observabilidade Postgres LangSmith Phoenix]]
