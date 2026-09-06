# Evolução do Agente — v1 a v6

Registro versionado do desempenho do agente industrial. Cada versão foi **medida**
no split de treino (13 tickets) antes e depois de cada mudança, com o gabarito
`eval/expected-paths.json` como referência.

> Metodologia: o split de teste (4 tickets) é *held-out* e não aparece aqui — só
> roda na prova final. Todo número desta página vem do treino.

---

## Resumo executivo

| versão | acurácia de decisão | o que mudou |
| :--- | ---: | :--- |
| **v1** | **4/13 — 31%** | linha de base (estado herdado) |
| v2 | 6/13 — 46% | evidência degradada deixa de bloquear |
| **v3** | **11/13 — 85%** | triagem pela intenção do cliente |
| v4 | 10/13 — 77% | correções no juiz e no idioma |
| **v5** | **11/13 — 85%** | camada MCP como interface real |
| v6 | *ver ressalva* | andaime de evidência nas respostas |

**O salto que conta a história: 31% → 85%.** A oscilação de ±1 caso entre v3, v4 e
v5 é ruído de temperatura (`temperature=0.3`), não sinal.

---

## v1 — Linha de base

Estado do agente no início da auditoria.

```
acurácia de decisão   4/13 = 31%
decisões              10 escalate · 1 act · 2 orient
gabarito esperava      8 orient · 3 act · 2 escalate
trajectory_avg_score  0.736
juiz LLM              nunca executou
traces no Phoenix     zero
chamadas via MCP      zero
testes                71
```

### O diagnóstico

**O agente virou uma máquina de escalar: 10 de 13 tickets.** Três causas empilhadas:

1. **O `quality_check` descartava evidência íntegra.** Qualquer modo diferente de
   `complete` em `baseline` ou `analyses` virava veredicto `unavailable`. Mas o
   modo `conflict` devolve o payload **inteiro** mais um flag, e `partial` só omite
   campos secundários. O caso `TKT-INV-06` tinha as duas análises conflitantes
   completas em mãos — e foram jogadas fora.

2. **O `decide` curto-circuitava.** Em `unavailable`, retornava um dossiê
   *hardcoded* e o LLM nunca era consultado. Dez tickets receberam o mesmo texto,
   que ainda afirmava fatos não verificados ("O sinal de RMS foi obtido" quando o
   RMS vinha vazio).

3. **O agente só alcançava 5 das 17 operações da API.** Nunca chamava
   `GET /assets/{id}`, `GET /models/{id}` nem `GET /analyses/{id}`. Em 6 dos 13
   casos a trajetória do gabarito passava por categorias inalcançáveis.

### A métrica escondia o problema

`trajectory_avg_score: 0.736` parecia razoável. Mas 2 dos 4 pontos eram grátis
(existir um `quality_verdict` e existir qualquer `data_gaps`): um agente que
errasse **todas** as decisões ainda tirava 0.5.

---

## v2 — Evidência degradada deixa de bloquear

```
acurácia   6/13 = 46%   (+15 p.p.)
decisões   10 orient · 3 act · 0 escalate
confusão   orient→act 3 · act→orient 2 · escalate→orient 2
```

### Mudanças
- `quality_check` passa a **anotar em vez de bloquear**. `conflict` e `partial`
  são reclassificados como evidência **utilizável**.
- Dossiê hardcoded removido — o LLM sempre decide, ciente das lacunas.
- *Structured output* no lugar do parsing por substring (`"solicitar" in text` → agir).
- Tools novas: `getAsset`, `getModel`, `getAnalysis`. Busca de conhecimento
  corrigida (antes procurava `"manutenção asset_V301"`, que nunca casava).

### O que aprendemos
O pêndulo inverteu: de escalar tudo para orientar tudo (**zero** escalonamentos).
Destravar a evidência resolveu metade do problema; a outra metade era de critério.

---

## v3 — Triagem pela intenção do cliente

```
acurácia   11/13 = 85%   (+39 p.p.)
decisões   9 orient · 3 act · 1 escalate
```

### O insight
O agente ignorava **o que o cliente pediu**. "Reprocessa a análise" virava
orientação; "isso é falso positivo?" virava ação.

O system prompt passou a começar pela intenção do ticket e só depois checar se a
evidência sustenta:

1. Pediu uma ação na plataforma? → **ACT**, se houver alvo válido.
2. Pediu intervenção humana, ou houve falha física consumada? → **ESCALATE**.
3. Fez uma pergunta? → **ORIENT**. Pergunta pede explicação, não ação.

Foi a mudança de maior retorno por linha de prompt de toda a evolução.

---

## v4 — Correções no instrumento de medição

```
acurácia      10/13 = 77%
juiz (média)  7.23   ⚠ inclui uma falha contada como zero
```

Versão de consolidação, focada em consertar a **régua**, não o agente:

- **Bug no parser do gabarito:** `expected_decision` procurava `"/specialist"` e
  `"/retrain"`, mas os endpoints reais são `request-specialist` e
  `request-retraining`. Dois casos de `act` estavam rotulados como `orient`.
- Decisão passa a valer **2 dos 4 pontos**; o ponto grátis do `quality_verdict`
  foi removido; `decision_accuracy` e matriz de confusão entram no resumo.
- Juiz LLM ganha **âncoras de calibração** (o que é 0, 5 e 10 em cada eixo) e
  recebe a `root_question` do gabarito.

> ⚠️ A média 7.23 não é comparável com a do v5: uma falha transitória do provedor
> era gravada como nota **zero**, puxando a média. Corrigido depois — falha do
> juiz virou *ausência* de nota.

---

## v5 — Camada MCP como interface real

```
acurácia         11/13 = 85%
juiz (média)     6.46   (cobertura 13/13, limpa)
  honestidade    4.69
  clareza        8.38
  fundamentação  4.31
  segurança      7.69
tokens medidos   42.071 nos 13 tickets
testes           99 (60 agente + 39 API)
```

### O ADR-0001 não estava implementado
O documento afirmava que MCP era a **única** interface entre agente e API. Na
prática: o pacote `mcp` nunca era instalado, `mcp_server.py` não tinha bloco
`__main__` (rodado como módulo, encerrava sem subir servidor) e **nenhum arquivo
o importava** — os nós chamavam `tractian_request` direto.

```
nós do LangGraph
      ↓  call_tool("getBaseline", assetId=...)
agent/tools/mcp_client.py     ponte síncrona + span mcp.<tool>
      ↓  protocolo MCP sobre stdio
agent/tools/mcp_server.py     subprocesso: 18 tools
      ↓  agent/tools/client.py
API industrial (:8000)
```

### O Phoenix nunca havia gerado um trace
Três falhas independentes: as libs de instrumentação nunca eram instaladas, a
falha era engolida num `except Exception` mudo, e a UI chamava
`agent_graph.invoke` cru. Corrigido — mais instrumentação do httpx, spans por nó
com atributos de domínio, e persistência no Postgres.

### Permissões viram cenário de primeira classe
A migração expôs um `403` no `escalateCase`: `usr_sofia` é analista de
confiabilidade e **não tem permissão de escalonamento**. Erro HTTP passou a ser
traduzido em envelope, não exceção — é resposta legítima da API, e um cenário que
o case modela de propósito.

---

## v6 — Andaime de evidência nas respostas

### O diagnóstico do juiz
Com o juiz funcionando, o padrão ficou nítido no v5:

```
clareza        8.38   ← o agente escreve bem
honestidade    4.69   ← zerou em 4 tickets
fundamentação  4.31   ← zerou em 5 tickets
```

Respostas fluentes e confiantes, **mal ancoradas**. Dois casos flagrantes:

- `TKT-CTX-01` — *"O seu motor está em bom estado, não há sinais de falha no
  rolamento"*, sem nenhum dado que sustentasse. Ainda inventou um "rolamento NU 310".
- `TKT-EXE-13` — *"valores de vibração acima dos limites, especialmente na
  frequência BPFO"*, num ticket onde o espectro **não tinha vindo**.

É a regra nº 2 do próprio system prompt do agente sendo violada.

### A correção
`AgentDecision` ganhou dois campos que o modelo é obrigado a preencher **antes**
de redigir a resposta:

```python
evidencias: list[str]   # "baseline.state = invalidated"
limitacoes: list[str]   # "rms indisponível: não confirma a tendência"
```

Mais a estrutura obrigatória da resposta (responder → fundamentar → reconhecer
lacuna → próximo passo) e a régua do juiz dentro do system prompt.

### Resultado — comparação pareada

> ⚠️ **Ressalva metodológica.** A cota diária do Groq (200k tokens) estourou no
> meio da rodada e derrubou 5 dos 13 tickets. A comparação abaixo é **pareada
> sobre os 8 tickets que completaram nas duas rodadas** — não sobre os 13.

| eixo | v5 | v6 | delta |
| :--- | ---: | ---: | ---: |
| fundamentação | 5.75 | 8.38 | **+2.62** |
| segurança | 8.75 | 10.00 | +1.25 |
| honestidade | 5.75 | 6.75 | +1.00 |
| nota geral | 7.38 | 8.25 | +0.88 |
| clareza | 8.50 | 8.12 | −0.38 |
| **acurácia** | 7/8 | 7/8 | sem custo |

Os tickets que **zeraram** honestidade no v5 (`CTX-01`, `CTX-03`, `EXE-13`) são
justamente os que faltaram no v6 por causa da cota. O ganho real em honestidade
está **subestimado**, não medido.

A queda de 0.38 em clareza é o custo plausível de respostas mais densas em
evidência. Trocar 0.38 de clareza por 2.62 de fundamentação é um bom negócio.

---

## Os 2 erros que persistem — e por que ficaram

Não foram "consertados" de propósito: ajustar o prompt para acertá-los seria
*overfitting* no treino.

- **`TKT-INV-04`** (esperado `escalate`, real `orient`) — o agente produziu a
  explicação completa: sensor offline, baseline em `learning`, modelo `delayed`,
  tipo de máquina não suportado pelo modelo. É uma fronteira de julgamento
  genuína, não um erro grosseiro.
- **`TKT-EXE-13`** (esperado `act`, real `orient`/`escalate`) — `analyses` volta
  `unavailable` para o `asset_C710`, então não existe `analysis_id` sobre o qual
  pedir especialista. O agente se recusou a agir sem alvo válido, que é a regra
  "nunca invente um id" funcionando. Nenhum endpoint da API revelaria o `an_9902`
  nesse estado.

---

## Como reproduzir

```bash
make up-obs                          # Postgres + Phoenix
make eval                            # treino, sem juiz (rápido)
make run                             # treino, com juiz
make evolucao                        # esta tabela, a partir dos dados gravados
make prova-final                     # teste held-out — uma vez só
```

Medição de custo e latência exige desligar o cache, senão não há chamada de LLM
para medir:

```bash
.venv\Scripts\python.exe -m eval.runner --split train --no-cache
```

## Limitações conhecidas

- **Variância entre rodadas.** `temperature=0.3` produz oscilação de ~1 caso
  (10–11/13). Os números são de rodada única, não média de N.
- **Cota do provedor.** O Groq gratuito tem 200k tokens/dia — cerca de 3 rodadas
  completas com juiz. A cadeia de fallback (`LLM_FALLBACK_*`) mitiga.
- **Split pequeno.** 13 tickets de treino: cada caso vale 7.7 pontos percentuais.
