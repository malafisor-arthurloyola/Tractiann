---
tags: [streamlit, ui, interface]
aliases: [Streamlit, Interface, UI]
---

# Streamlit Interface

## O que é
Interface web em Python puro que permite ao usuário:
- Selecionar tickets de `cases.json`
- Executar o agente com um clique
- Ver resultado: quality_verdict, gaps, decisão, justificativa
- Ver trace passo-a-passo (cada nó do grafo)
- Confirmar/cancelar ações de impacto (HITL via `interrupt()`)

## Como rodar
```bash
streamlit run app.py
# Abre em http://localhost:8501
```

## Blocos
1. Seletor de ticket (dropdown)
2. Botão "Executar" (roda o grafo)
3. Cards de resultado (métricas)
4. Expander com trace completo
5. Botões de confirmação (HITL)

## Checkpoint
Para HITL, precisa de um `checkpoint_saver` (memória em dev, Postgres em prod)
para persistir o estado durante a pausa do `interrupt()`.

## Relacionado
- [[Human-in-the-loop]]
- [[Grafo LangGraph]]
- [[Observabilidade Postgres LangSmith Phoenix]]
