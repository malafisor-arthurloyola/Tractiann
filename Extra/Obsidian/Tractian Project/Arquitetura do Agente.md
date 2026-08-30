---
tags: [architecture, agent]
aliases: [Arquitetura, Desenho do Agente]
---

# Arquitetura do Agente

## Camadas
```
Streamlit (UI, futuro) → Agente (LangGraph) → Tools (MCP) → API Tractian
```

## Seams (costuras)
Cada camada é um *seam* — ponto onde uma peça pode ser trocada sem quebrar as outras.
Isso dá **testabilidade** e **navegabilidade de IA**.

## Fluxo do grafo
```
investigar → quality_check → decidir → (responder | agir | escalar)
                     ↓
              incompleto → investigar (loop)
              indisponível → escalar
```

## Conceitos centrais
- [[Módulo Raso vs Profundo]]
- [[Quality Check Node]]
- [[Envelope de Resposta]]

## Registro
- [[Decisões de Arquitetura]] (ADRs)
