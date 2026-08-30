---
tags: [domain, tractian]
aliases: [Domínio, Glossário, Termos do Domínio]
---

# Domínio Industrial Tractian

## Ativo (asset)
A máquina/equipamento monitorado (ex.: motor M-605). Tem pontos de medição, análises,
[[Baseline]], série RMS, espectro e qualidade de dados.

## Ticket (case)
Solicitação de suporte: texto do cliente + contexto (empresa/usuário/ativo). É a entrada
do agente e vira um cenário de avaliação.

## Envelope de Resposta
Toda resposta da API vem num envelope com modo:
`complete`, `partial`, `inconclusive`, `conflict`, `unavailable`.
→ [[Envelope de Resposta]]

## Detection Mode
Como a falha foi detectada: `baseline` (desvio do aprendido) ou `symptom` (sintoma direto).
→ [[Detection Mode]]

## Glossário completo
Vive em `CONTEXT.md` na raiz do projeto — a fonte de verdade dos termos.
