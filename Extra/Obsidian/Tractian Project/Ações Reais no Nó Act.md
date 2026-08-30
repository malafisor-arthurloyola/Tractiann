---
tags: [actions, act, api, hitl]
aliases: [Ações Reais, Nó Act, POST/PATCH]
---

# Ações Reais no Nó Act

## O que mudou
O nó `act` agora **executa** ações na API industrial, não só faz `interrupt()`.

## Fluxo completo
1. `decide` detecta "AGIR" e usa `_extract_action()` para determinar:
   - `action_type` (reprocess/specialist/retrain/update_config)
   - `action_target` (analysis_id, model_id, asset_id)
2. `act` chama `interrupt()` → pausa grafo (HITL)
3. Humano confirma via Streamlit → `Command(resume=True)`
4. `act` executa `tractian_request(method, path, user_id, json_data)`

## Mapeamento action_type → endpoint
| action_type | method | endpoint | permissão |
|---|---|---|---|
| reprocess | POST | /analyses/{id}/reprocess | action_low |
| specialist | POST | /analyses/{id}/request-specialist | action_low |
| retrain | POST | /models/{id}/request-retraining | action_high |
| update_config | PATCH | /assets/{id} | action_high |
| escalate | POST | /cases/{id}/escalate | escalate |

## `_extract_action()` - regra de palavras-chave
- "reprocessar" → reprocess (alvo = 1º analysis_id disponível)
- "especialista" → specialist (alvo = 1º analysis_id)
- "retreinamento" → retrain (alvo = model_id ou fallback mdl_vib_v3)
- "config"/"criticidade" → update_config (alvo = asset_id)

## Relacionado
- [[Grafo LangGraph]]
- [[Human-in-the-loop]]
- [[Correções no Grafo HITL Cache]]