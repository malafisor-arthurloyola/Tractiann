---
tags: [evaluation, llm-judge, teach]
aliases: [Avaliação, Juiz LLM]
---

# L13 — Avaliação e Juiz LLM

## Pirâmide de Avaliação
1. **Testes Unitários** — lógica determinística (rotas, parsing, helpers)
2. **Trajetória** — `eval/runner.py` verifica passos do grafo vs ground truth
3. **Juiz LLM** — `eval/judge/llm_judge.py` avalia qualidade textual (0-10)

## Critérios do Juiz
- **Honestidade:** não inventou dados
- **Fundamentação:** baseou-se nas tools consultadas
- **Segurança:** respeitou limites (não sugeriu ações fora do escopo)

## Comandos
- `make eval` — treino sem juiz (rápido)
- `make run` — treino com juiz
- `make prova-final` — teste held-out com juiz

## Relacionado
- [[Avaliação do Agente]]
- [[L12 - Testing and Next]]
- [[L14 - API and MCP Tools]]