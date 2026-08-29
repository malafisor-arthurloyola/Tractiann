# AGENTS.md — Agente Industrial Tractian

Contexto de projeto pra qualquer agente de codificação (Claude Code, Copilot, Cursor etc.) usar como referência. Se for usar Claude Code especificamente, crie um `CLAUDE.md` com uma linha só: `@AGENTS.md`.

## Visão geral

Projeto individual dentro da liga de IA, case da Tractian (parceria Tractian x Inteli — "Engenharia e Avaliação de Agentes Industriais"). Entrega final: **08 de setembro de 2026**.

**Pergunta norteadora:** como construir um agente de IA capaz de usar a API industrial da Tractian com precisão, interpretar evidências corretamente e decidir a ação certa — orientar, agir ou escalar — diante de uma solicitação de suporte?

O agente simula um engenheiro de suporte da Tractian recebendo tickets sobre problemas relacionados a dados vindos dos sensores/dispositivos do cliente.

## Escopo

### Dentro do escopo
- Receber um ticket (dos casos em `agent-input/cases.json`) com texto do cliente + contexto (empresa/ativo/usuário)
- Investigar via camada MCP integrada aos 17 endpoints da API
- Decidir entre **orientar** (só explicar) / **agir** (executar ação na plataforma) / **escalar** (mandar pra humano)
- Confirmação humana obrigatória antes de qualquer ação de impacto (`action_high`)
- Resposta em linguagem simples pro cliente, sempre fundamentada na evidência coletada — nunca inventar o que não foi confirmado
- Cair pra humano quando o dado disponível não é suficiente
- Framework de avaliação: comparação determinística de trajetória (vs `eval/expected-paths.json`) + avaliação por juiz LLM (qualidade/segurança da resposta)
- Documentação completa (README com hipótese, metodologia, resultados, limitações)
- Discussão de custo e latência entre as escolhas técnicas, pra apresentação final

### Fora do escopo
- Dados reais de cliente Tractian — tudo é sintético (parquet)
- Treinar/melhorar o modelo de detecção de anomalia (ele já é dado como pronto, só é consumido via "Análises")
- Construir a API em si (fornecida pronta pelo parceiro)
- Virar produto de produção

## Conceitos de domínio essenciais

- **Baseline**: o "normal" aprendido *daquele ativo específico* (não é uma norma genérica). Estados: `learning` (ainda sem histórico suficiente) → `established` (confiável) → `invalidated` (mudança física invalidou o histórico, precisa reaprender).
- **Dois modos de detecção**:
  - `baseline` — desvio do normal aprendido (desbalanceamento, desalinhamento, rolamento, elétrica). Exige baseline `established`.
  - `symptom` — sintoma que já indica a falha por si só, independe do estado do baseline (ex.: lubrificação incorreta → ruído em alta frequência do espectro).
- **API é probabilística de propósito**: retorno completo, parcial, inconclusivo, conflito entre fontes ou indisponibilidade — simula a realidade de campo. O agente precisa lidar bem com isso, sem travar nem inventar.

## Arquitetura

```
Interface de demonstração (Streamlit)
        ↓
Agente (LangGraph) — loop: investigar → evidência suficiente?
        ↓ (chama tools)
Servidor MCP (17 tools, uma por operação da API)
        ↓
API Tractian (dados sintéticos em parquet)
        ↓ (retorno/evidências volta pro agente)
Decisão: orientar / agir / escalar (confirmação antes de ação de impacto)
        ↓
Trace da execução → Postgres (log)
        ↓
Avaliação: determinística (trajetória vs gabarito) + Juiz LLM (qualidade/segurança)
        ↓
Relatório de resultados (custo, latência, acurácia, trade-offs)
```

Durante o desenvolvimento, usar **LangSmith** para visualizar o trace de cada nó do grafo e debugar sem precisar ler a implementação interna do LangGraph.

## Mapeamento API → Tools MCP (17 operações, 7 categorias)

| Categoria | Tool (operationId) | Endpoint | ⚠️ Impacto |
|---|---|---|---|
| Contexto | `getCompany` | `GET /companies/{id}` | |
| Contexto | `listAssetsByCompany` | `GET /companies/{id}/assets` | |
| Contexto | `getCurrentUser` | `GET /users/me` | |
| Ativos | `listAnalyses` | `GET /assets/{id}/analyses` | |
| Ativos | `updateAssetConfig` | `PATCH /assets/{id}` | ⚠️ exige `action_high` |
| Análises | `getAnalysis` | `GET /analyses/{id}` | |
| Análises | `reprocessAnalysis` | `POST /analyses/{id}/reprocess` | ⚠️ exige justificativa |
| Análises | `requestSpecialistAnalysis` | `POST /analyses/{id}/request-specialist` | ⚠️ exige justificativa |
| Dados técnicos | `getBaseline` | `GET /assets/{id}/baseline` | |
| Dados técnicos | `getRmsSeries` | `GET /assets/{id}/rms` | |
| Dados técnicos | `getSpectrum` | `GET /assets/{id}/spectrum` | |
| Dados técnicos | `getDataQuality` | `GET /assets/{id}/data-quality` | |
| Modelos | `getModel` | `GET /models/{id}` | |
| Modelos | `requestRetraining` | `POST /models/{id}/request-retraining` | ⚠️ alto impacto, justificativa forte |
| Conhecimento | `searchKnowledge` | `GET /knowledge/search` | |
| Conhecimento | `getKnowledgeDoc` | `GET /knowledge/{id}` | |
| Ações | `escalateCase` | `POST /cases/{id}/escalate` | ⚠️ exige justificativa |

## Stack e decisões técnicas

- **Orquestração**: LangGraph — controla o loop de decisão (investigar → decidir → responder/agir/escalar). LangChain **não** é usado como orquestrador concorrente — entra só como biblioteca de apoio (wrappers de modelo, decorators de tool) dentro dos nós do LangGraph. É assim que o próprio ecossistema funciona hoje (LangGraph roda em cima do LangChain).
- **Human-in-the-loop**: `interrupt()` do LangGraph, disparado antes de qualquer tool marcada com ⚠️ (ação de impacto) — pausa a execução até confirmação humana
- **Camada de tools**: MCP — expõe as 17 operações da API de forma padronizada
- **Log de execuções**: Postgres — tabela `execucoes` (ticket, versão do agente, trace completo, decisão final, timestamp) pra comparar métricas entre versões
- **Observabilidade em dev**: LangSmith — trace visual node-a-node (parte do plano principal, não opcional — essencial pra debugar sem precisar ler log bruto)
- **Avaliação**: parte determinística (trajetória vs `eval/expected-paths.json`) + juiz LLM (qualidade/segurança), rodando os 17 cenários de `docs/test-scenarios.md`
- **Interface de demo**: Streamlit

## Convenções (preencher conforme o projeto avança)

- Linguagem: Python
- **LLM**: Groq (`llama-3.3-70b-versatile`, gratuito, ~30 req/min) e modelos gratuitos via OpenRouter como alternativa — sem assinatura paga. Ambos expõem endpoint compatível com a API da OpenAI.
- Como rodar a API: `make up` (a partir do README do case fornecido)
- **Estrutura descoberta no Makefile**: o projeto espera uma pasta `agent/` na raiz, com `agent/server.py` (entrada do agente/UI, sobe na porta 8001) e `agent/.env` (criado via `make agent-env` a partir de um `agent/.env.example` que você mesmo cria, com `OPENAI_API_KEY`/`BASE_URL`/`MODEL`). Nenhuma dessas pastas/arquivos existe ainda — é o aluno quem cria.
- Testes: _a definir_

## Status atual / próximos passos

- [ ] Criar pasta `agent/` com `.env.example`
- [x] Primeira tool MCP (`get_baseline`) — esqueleto andante
- [ ] Demais 16 tools MCP
- [ ] Grafo LangGraph (nós: investigar, decidir, responder/agir/escalar)
- [ ] Human-in-the-loop (`interrupt()`) antes de ações `action_high`
- [ ] Integração de tracing (LangSmith)
- [ ] Schema Postgres pra log de execuções
- [ ] Harness de avaliação (determinístico + juiz LLM)
- [ ] Interface de demo (Streamlit)
- [ ] README final com metodologia, resultados e limitações