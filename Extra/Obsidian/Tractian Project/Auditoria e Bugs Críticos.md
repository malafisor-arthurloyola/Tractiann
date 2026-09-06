---
tags: [audit, architecture, bugs]
aliases: [Auditoria, Bugs Críticos]
---

# Auditoria e Bugs Críticos

## Auditoria 1 — grafo e fluxo

### O que foi auditado
Todos os arquivos-chave do agente (agent/, eval/, api/), a compilação do grafo,
o venv, o fluxo de dados e o código morto.

### Bugs encontrados

#### Críticos
- **act node nunca executava** — só fazia interrupt(), não chamava API
- **unavailable → decision=None** — route_after_quality pulava o decide

#### Altos
- **Cache sem invalidação** — prompt mudou mas cache antigo continuava
- **tools_called duplicava** — operator.add + lista inteira = entries duplicados
- **Trajectory assertions incompletas** — não cobria knowledge, models, POST

#### Médios
- **Código morto** — tools.py antigo, is_within_trace, 5 campos dead no state
- **pyproject.toml ausente** — clone limpo = import error
- **env.example errado** — Makefile procurava .env.example mas arquivo era env.example

---

## Auditoria 2 — observabilidade e qualidade de resolução

Motivada por duas suspeitas: "o Phoenix não parece estar mostrando nada" e "será que
os tickets estão sendo resolvidos da melhor forma?". As duas se confirmaram, medidas:

```
acurácia de decisão: 4/13 = 31%   (10 de 13 tickets escalavam)
[phoenix] Instrumentação não ativada (No module named 'opentelemetry')
```

### Críticos

- **O Phoenix nunca gerou um único trace.** As deps do agente nunca eram instaladas
  (o `make deps` só instalava `api/[dev]`), e a falha era engolida num `except Exception`
  mudo. Detalhes em [[Observabilidade Postgres LangSmith Phoenix]] e [[Ambiente e Reprodutibilidade]].
- **O `quality_check` jogava fora evidência completa.** `conflict` devolve o payload
  íntegro **mais** um flag, e era tratado como ausência de dado → veredicto
  `unavailable` → escalonamento hardcoded, sem consultar o LLM. Ver [[Quality Check Node]].
- **Dossiê de escalonamento hardcoded.** Texto idêntico para 10 tickets, afirmando
  fatos não verificados ("O sinal de RMS foi obtido" quando o RMS vinha vazio) —
  violando a regra nº 2 do próprio system prompt do agente.

### Altos

- **Parsing da decisão por substring.** `"solicitar" in text` → agir; `"humano" in text`
  → escalar. Palavras que aparecem em prosa comum. Substituído por structured output.
- **O agente só alcançava 5 das 17 tools.** Nunca chamava `GET /assets/{id}`,
  `GET /models/{id}` nem `GET /analyses/{id}`. Ver [[Evidência Compensatória]].
- **O nó `escalate` nunca escalava.** Só escrevia no trace; `POST /cases/{id}/escalate`
  jamais era chamado, embora o gabarito o espere.
- **A métrica dava 2 dos 4 pontos de graça**, mascarando a acurácia real. Ver [[Avaliação do Agente]].
- **A UI nunca instrumentava o Phoenix** — `agent_graph.invoke` cru, sem `run_in_phoenix_trace`.
- **Busca de conhecimento impossível de casar** — `q="manutenção {asset_id}"` contra um
  `contains` de título/corpo.

### Médios

- **`expected_decision` procurava `/specialist` e `/retrain`**, mas os endpoints são
  `request-specialist` e `request-retraining`. Dois casos de `act` mal rotulados.
- **Playground quebrado** — `render_response(res)` com 1 argumento; a assinatura pede 2.
- **`thread_id` fixo na UI** — "Limpar Cache e Re-executar" não invalidava o checkpoint
  do MemorySaver, e a re-execução caía num checkpoint já pausado.
- **Execuções pausadas no HITL não eram logadas** no Postgres.
- **`_get_connection` engolia a causa da falha** — driver ausente, banco fora do ar e
  senha errada eram indistinguíveis. Hoje há `check_health() -> (ok, motivo)`.
- **Volume do Phoenix era no-op** — sem `PHOENIX_WORKING_DIR`, gravava fora do volume.
- **`test_agent.py` na raiz** não é teste: é script que roda o agente no import, e o
  pytest o coletaria.
- **`st.info` com tags HTML literais**; imports mortos em `compare.py` e `postgres.py`.

### Pendente de decisão

- **A camada MCP é código morto e contradiz o ADR-0001.** `agent/tools/mcp_server.py`
  não importa (`from mcp.server.mcpserver import MCPServer` não é o caminho do SDK —
  é `mcp.server.fastmcp.FastMCP`), o pacote não está instalado, e o grafo chama
  `tractian_request` (httpx) direto. O ADR afirma que MCP é a *única* interface entre
  agente e API: o documento descreve uma arquitetura que não existe. Ou se faz o
  servidor MCP valer, ou se marca o ADR como Substituída. Ver [[Camada MCP - Tools]]
  e [[Decisões de Arquitetura]].

## Processo de auditoria
1. Leitura de todos os arquivos-chave
2. Testes de compilação e importação
3. **Execução real medida** (baseline antes de mudar qualquer coisa)
4. Inspeção dos payloads reais da API, não só do código
5. Trace do fluxo de dados e controle
6. grep/ls para código morto
7. Lista de bugs por severidade
8. Correção em ordem de impacto, com re-medição a cada passo

> [!tip] A lição do baseline
> Medir **antes** foi o que revelou que o `trajectory_avg_score: 0.74` era um artefato
> da métrica, não desempenho. Sem o número de partida, as correções não teriam como
> ser justificadas.

## Relacionado
- [[Correções no Grafo HITL Cache]]
- [[Ações Reais no Nó Act]]
- [[Evidência Compensatória]]
- [[Ambiente e Reprodutibilidade]]
- [[Testes Automatizados e Próximos Passos]]
