---
tags: [evaluation, testing, judge-llm]
aliases: [Avaliação, Juiz LLM, Métricas, Eval]
---

# Avaliação do Agente

## Duas dimensões
1. **Determinística** (`eval/assertions/trajectory.py`): o agente decidiu certo e
   chamou as APIs certas? Compara com `eval/expected-paths.json`.
2. **Subjetiva** (`eval/judge/llm_judge.py`): a resposta é clara, honesta, fundamentada?

## A métrica que escondia o problema

> [!bug] O `trajectory_avg_score` dava 2 dos 4 pontos de graça
> Um ponto por ter produzido um `quality_verdict` (sempre produzia) e outro por ter
> qualquer `data_gaps` não-vazio. Um agente que errasse **todas** as decisões ainda
> tirava 0.5. A média ficava presa em 0.74 enquanto a acurácia real era **31%**.

### Pesos atuais (total 4.0)
| critério | peso | observação |
| :--- | :--- | :--- |
| decisão correta | **2.0** | dominante — é o que "resolver o ticket" significa |
| cobertura de tools | 1.0 | proporcional às categorias de GET do gabarito |
| honestidade dos gaps | 1.0 | **guard-rail**: pontua por coerência entre veredicto e gaps, não por existirem gaps |
| `quality_verdict` presente | **0** | removido |

### Métrica de topo
`decision_accuracy` passou a ser exposta no resumo do runner, junto com a **matriz de
confusão** (esperado → real), que mostra de que lado o agente erra.

## O bug no parser do gabarito
`expected_decision` derivava a decisão do último passo do `expected_path`, procurando
`"/specialist"` e `"/retrain"`. Os endpoints reais são `request-specialist` e
`request-retraining` — **sem a barra**. Dois casos de `act` (TKT-EXE-13, TKT-EXE-15)
estavam rotulados como `orient`. Corrigido para casar sem exigir a barra.

## Evolução medida (split de treino, 13 tickets)

| versão | acurácia | comportamento |
| :--- | :--- | :--- |
| v1 (original) | **31%** (4/13) | escalava 10 de 13 — o `quality_check` bloqueava e o LLM nem rodava |
| v2 | 46% (6/13) | quality_check anota em vez de bloquear; pêndulo inverteu para orientar tudo |
| v3 | **85%** (11/13) | triagem por intenção do cliente no system prompt |

### O que destravou cada salto
- **v1 → v2**: `conflict`/`partial` reclassificados como evidência utilizável;
  dossiê hardcoded removido; structured output no lugar do parsing por substring;
  [[Evidência Compensatória|tools compensatórias]] adicionadas.
- **v2 → v3**: o agente ignorava **o que o cliente pediu**. "Reprocessa a análise"
  virava orientação; "isso é falso positivo?" virava ação. O prompt passou a começar
  pela intenção do ticket e só depois checar se a evidência sustenta.

### Os 2 que restam são defensáveis
- **TKT-INV-04** (esperado `escalate`, real `orient`): o agente achou a explicação
  completa — sensor offline, baseline `learning`, modelo `delayed`, tipo de máquina
  não suportado. Fronteira de julgamento genuína.
- **TKT-EXE-13** (esperado `act`, real `orient`): `analyses` volta `unavailable` para
  o `asset_C710`, então não existe `analysis_id` para pedir especialista. O agente se
  recusou a agir sem alvo válido — a regra "nunca invente um id" funcionando.
  Nenhum endpoint da API revelaria o `an_9902` nesse estado.

> [!warning] Não tunar nesses dois
> Ajustar o prompt para acertá-los seria overfitting no treino. O split de teste
> (`eval/split.json`) é held-out e só roda na prova final.

## Juiz LLM
Saída estruturada (`JudgeVerdict`), com **âncoras de calibração** — o que é 0, 5 e 10
em cada critério. Sem elas o modelo distribui tudo em 7-8 e a métrica não separa nada.
Recebe também a `root_question` do gabarito, para julgar se a resposta respondeu à
pergunta que o ticket de fato fazia.

Critérios: honestidade, clareza, fundamentação, segurança.

## Relacionado
- [[Grafo LangGraph]]
- [[Quality Check Node]]
- [[Evidência Compensatória]]
- [[Observabilidade Postgres LangSmith Phoenix]]
