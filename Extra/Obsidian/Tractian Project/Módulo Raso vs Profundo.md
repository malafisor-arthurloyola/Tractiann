---
tags: [architecture, concept]
aliases: [Módulo Raso, Deep Module, Shallow Module]
---

# Módulo Raso vs Profundo

## Conceito
- **Módulo raso (shallow)**: a interface (jeito de usar) é quase tão complexa quanto o
  que o módulo faz por dentro. Ex.: muitas tools repetindo a mesma chamada HTTP + headers.
- **Módulo profundo (deep)**: interface simples escondendo complexidade útil. A parte
  simples é fácil de usar; a complexa vive num só lugar.

## O problema que resolveu
As 17+ tools da [[Camada MCP - Tools]] repetiam a mesma mecânica (URL, header
`x-user-id`, envelope). Isso era um **módulo raso**.

## Solução aplicada
Helper central `client.py` (função `tractian_request`) que centraliza a chamada e o
tratamento. As tools ficam curtas: dizem qual operação querem, recebem o envelope
tratado.

## "Deletion test"
Se você pode deletar um módulo e o resto continua funcionando, ele era raso/redundante.
O helper pode ser deletado e as tools param — mas ele traz coesão real.
