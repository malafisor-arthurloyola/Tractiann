---
tags: [architecture, hitl, interrupt]
aliases: [Human-in-the-loop, HITL, Interrupt, Pausa Humana]
---

# Human-in-the-loop

## O que é
Mecanismo do LangGraph (`interrupt()`) que **pausa a execução do grafo** e aguarda
confirmação humana antes de prosseguir com uma ação de impacto.

## Ciclo de vida
1. Grafo roda até o nó `act`.
2. `interrupt()` pausa — estado salvo via checkpoint.
3. Interface (Streamlit) mostra justificativa + dados + gaps.
4. Humano confirma ou cancela.
5. Grafo retoma de onde parou.

## Quando pausar
- **Orientar** → NÃO (só explicar)
- **Reprocessar análise** → SIM (ação de impacto)
- **Solicitar retreinamento** → SIM (alto impacto)
- **Alterar config** → SIM (alto impacto)
- **Escalar** → NÃO (o humano é o destinatário)

## Notas
- `interrupt()` do LangGraph.
- Checkpoint pode ser memória (dev) ou Postgres (produção).
- Conecta com [[Streamlit Interface]] e [[Observabilidade Postgres LangSmith Phoenix]].

## Relacionado
- [[Grafo LangGraph]]
- [[Camada MCP - Tools]]
