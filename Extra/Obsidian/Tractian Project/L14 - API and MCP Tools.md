---
tags: [api, mcp, tools, teach]
aliases: [API Industrial, Ferramentas MCP]
---

# L14 — API Industrial & 17 Ferramentas MCP

## Envelope de Resposta
Todo retorno da API vem num envelope com campo `mode`:
- `complete` — íntegro, suficiente
- `partial` — incompleto, mas útil
- `inconclusive` — ruído/SNR baixo
- `conflict` — conflito (ex: baseline vs análise)
- `unavailable` — serviço fora do ar

## 17 Ferramentas
| Categoria | Tools |
|---|---|
| Contexto | `get_company`, `get_user`, `get_asset` |
| Sinais | `get_rms`, `get_spectrum`, `get_baseline`, `get_data_quality` |
| Análises | `get_analyses`, `get_analysis_detail` |
| Ações (POST/PATCH) | `reprocess_analysis`, `request_specialist`, `request_retraining`, `update_asset_config`, `escalate_case` |

## MCP Server
Expõe as funções como `tools` para o LLM. O agente decide qual chamar.

## Relacionado
- [[Camada MCP - Tools]]
- [[L13 - Evaluation and LLM Judge]]
- [[L15 - Extensibility]]