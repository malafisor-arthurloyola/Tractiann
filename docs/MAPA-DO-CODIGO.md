# Mapa do código — onde cada coisa mora

Glossário dos arquivos que importam. Não lista tudo: lista o que você precisa abrir para
entender ou mexer em cada parte do sistema.

> Regra de ouro para se orientar: **`agent/` é o agente, `eval/` é quem julga o agente, e
> `api/` é o mundo que o agente investiga.** Nunca deixe `eval/` influenciar `agent/` — é o
> gabarito, e o agente não pode vê-lo.

---

## O agente

### `agent/graph/nodes.py` — o cérebro
**O arquivo mais importante do projeto.** Contém os cinco nós do grafo e as regras que os
governam.

| o que procurar | onde |
| :--- | :--- |
| Quais tools o agente busca sempre | `CORE_TOOLS` |
| Como escolhe evidência compensatória | `COMPENSATION` e `_next_compensation()` |
| Se um modo de envelope é utilizável | `USABLE_MODES` / `EMPTY_MODES` |
| Classificação da força da evidência | `quality_check()` |
| O prompt que orienta a decisão | `SYSTEM_PROMPT` |
| O schema da decisão | `AgentDecision` |
| Curadoria do que vai ao LLM | `_resumir_evidencia()` e `_resumir_rms()` |
| Validação do alvo de uma ação | `_validate_action()` |
| Mapa decisão → tool MCP | `ACTION_TOOLS` |

**Mexa aqui quando:** quiser mudar o comportamento do agente — quais dados busca, como
classifica evidência, como decide, o que manda ao LLM.

### `agent/graph/agent.py` — a montagem do grafo
Pequeno e central. Define as arestas e o roteamento: `route_after_quality` decide se volta a
investigar ou segue para decidir; `route_after_decide` escolhe entre orientar, agir e escalar.
`MAX_RETRIES` limita as rodadas de compensação.

**Mexa aqui quando:** quiser mudar o *fluxo* — adicionar um nó, mudar quando o grafo faz laço.

### `agent/graph/state.py` — o contrato entre os nós
O `AgentState`: tudo que trafega de um nó a outro. Os campos com `Annotated[..., operator.add]`
acumulam em vez de sobrescrever — é assim que `trace` e `tools_called` crescem a cada passada.

**Mexa aqui quando:** um nó precisar passar um dado novo adiante.

### `agent/llm.py` — de onde vêm os modelos
A cadeia de provedores e o *fallback* automático. Dois namespaces: `OPENAI_*`/`LLM_FALLBACK_N_*`
para o agente, `JUDGE_*`/`JUDGE_FALLBACK_N_*` para o juiz. `modelo_efetivo()` lê qual modelo
de fato respondeu — essencial quando há um roteador no caminho.

**Mexa aqui quando:** trocar de provedor, adicionar fallback, ou separar o juiz do agente.

---

## A camada MCP

### `agent/tools/mcp_server.py` — as 18 tools
Uma função por operação da API, decorada com `@mcp.tool()`. O bloco `__main__` sobe o servidor
por stdio. Roda isolado com `python -m agent.tools.mcp_server` para depurar tools sem o agente.

### `agent/tools/mcp_client.py` — a ponte
Sobe o servidor como subprocesso, faz o handshake e expõe `call_tool(nome, **args)` **síncrono**
— o SDK do MCP é assíncrono e os nós do grafo não são. Mantém a sessão viva entre chamadas e
emite o span `mcp.<tool>` no Phoenix.

**Mexa aqui quando:** trocar o transporte (stdio → HTTP) ou mudar o timeout.

### `agent/tools/client.py` — o HTTP de verdade
Base URL, header `x-user-id`, e a tradução de erro HTTP em envelope. **Detalhe interno do
servidor MCP** — nenhum nó do grafo importa este arquivo.

**Mexa aqui quando:** a autenticação ou o endereço da API mudar.

---

## Observabilidade

### `agent/logging/phoenix.py` — tracing
`setup_phoenix_tracing()` instrumenta LangChain e httpx. `record_node()` emite os spans com
atributos de domínio. `log_evaluations()` manda as notas do juiz para a aba **Evaluations**.

**Mexa aqui quando:** quiser rastrear um atributo novo ou mudar o destino dos traces.

### `agent/logging/postgres.py` — histórico
A tabela `execucoes` e as funções de consulta. `check_health()` diz **por que** a conexão
falhou, em vez de devolver `None` mudo.

### `agent/version.py` — a versão do agente
Uma constante. É a chave do cache de decisões e o nome do projeto no Phoenix. **Bumpe sempre
que mudar prompt, grafo ou política** — senão o cache devolve decisões da versão anterior.

---

## Avaliação

> Tudo aqui é **gabarito**. O agente não pode enxergar esta pasta.

### `eval/runner.py` — o motor
`run_graph()` trata o `interrupt()` do HITL; `run_single()` roda um ticket e avalia;
`run_all()` agrega e calcula o resumo. É quem grava no Postgres e publica as anotações no
Phoenix.

**Mexa aqui quando:** adicionar uma métrica ao resumo ou mudar como um split é carregado.

### `eval/assertions/trajectory.py` — a régua determinística
`expected_decision()` deriva do gabarito qual era a decisão certa. `classificar_erro()` separa
erro **conservador** de **arriscado**. `assert_trajectory()` dá a nota de 0 a 1.

**Mexa aqui quando:** mudar os pesos da avaliação ou a definição de acerto.

### `eval/judge/llm_judge.py` — o juiz
O prompt com âncoras de calibração e o schema `JudgeVerdict`. Registra qual modelo julgou e se
era independente do agente.

### `eval/evolucao.py` — a comparação entre versões
Junta `execucoes` (Postgres) com as anotações do Phoenix. `--modelos` agrupa pelo modelo que de
fato respondeu.

### `eval/split.json` e `eval/expected-paths*.json`
O split treino/teste e os gabaritos. O arquivo `-derivados` é separado de propósito: cenários
construídos neste projeto não podem ser somados aos do parceiro.

---

## Interface e infraestrutura

### `app.py` — o console Streamlit
Arquivo grande, mas com pontos claros: `execute_agent_stepwise()` roda o grafo,
`resume_agent_action()` retoma após a confirmação humana, `render_hitl_section()` é a UI dessa
confirmação. Os *health checks* ficam juntos, perto do topo.

### `Makefile` — todos os comandos
Se você não lembra como rodar algo, está aqui. `make help` lista.

### `docker-compose.yml` — Postgres e Phoenix
O Phoenix persiste no Postgres, em schema separado.

### `agent/.env` — configuração
Provedores de LLM, endereço da API, banco, Phoenix. Modelo em `.env.example`. **Nunca vai para
o git.**

---

## A API industrial (fornecida pelo parceiro)

### `api/app/main.py` — os endpoints
18 operações. As 5 que mudam estado exigem permissão: `PATCH /assets/{id}` e
`POST /models/{id}/request-retraining` pedem `action_high`; `reprocess` e `request-specialist`
pedem `action_low`; `escalate` pede `escalate`.

### `api/app/prob.py` — o comportamento probabilístico
**Leia este arquivo para entender o case.** `resolve_mode()` é um hash determinístico: mesma
URL devolve sempre o mesmo modo. Por isso *retry* não funciona e a estratégia é evidência
compensatória. Os `overrides` de `data/seed.json` fixam os cenários desenhados.

---

## Por onde começar, dependendo do que você quer

| quero… | abra |
| :--- | :--- |
| entender a decisão do agente | `agent/graph/nodes.py` → `quality_check` e `decide` |
| entender o fluxo | `agent/graph/agent.py` |
| entender por que a API é imprevisível | `api/app/prob.py` |
| entender como o agente é julgado | `eval/assertions/trajectory.py` |
| mudar de provedor de LLM | `agent/llm.py` + `agent/.env` |
| adicionar uma tool | `agent/tools/mcp_server.py` + `_handle_request` em `nodes.py` |
| ver os resultados | `docs/EVOLUCAO.md` |
