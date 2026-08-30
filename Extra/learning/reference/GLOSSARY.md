# GLOSSÁRIO DE DOMÍNIO TRACTIAN

## Agente
Um sistema de IA que simula um engenheiro de suporte, capaz de interpretar solicitações, usar ferramentas (tools) para investigar dados, e decidir entre [[Orientar]], [[Agir]] ou [[Escalar]] um chamado.

## Agir (Ação de Impacto)
Decisão do agente de executar uma operação na plataforma que altera o estado (ex: [[Reprocessar Análise]], [[Solicitar Retreinamento]]). Exige [[Justificativa]] e, para algumas, permissão adequada.

## Análise (Insight)
Diagnóstico automático do modelo para um [[Ativo]]. Contém tipo, severidade, confiança, evidência, limitações e [[Detection Mode]].

## Ativo (Asset)
A máquina ou equipamento monitorado (ex: motor M-605, bomba B-204). Possui [[Pontos de Medição]], [[Análises]], [[Baseline]], [[Série RMS]], [[Espectro]] e [[Qualidade e Frescor dos Dados]].

## Baseline
O "estado normal" aprendido do [[Ativo]] a partir de um histórico sadio. Seu estado pode ser `learning` (dados insuficientes), `established` (confiável) ou `invalidated` (histórico não mais válido).

## Camada de Tools (MCP)
Um conjunto de 18 operações da API Tractian expostas como funções (_tools_) através do [[MCP (Model Context Protocol)]]. É a forma padronizada de o agente interagir com o sistema industrial.

## Case (Ticket)
Uma solicitação de suporte. Contém o texto do cliente + contexto (empresa, usuário, ativo). É a entrada principal do agente.

## Cliente (Usuário)
A pessoa que abriu o [[Case]]. O agente deve sempre responder de forma clara e honesta para o cliente final.

## Contexto Inicial
As informações fornecidas junto com o [[Case]] (empresa, usuário, ativo), essenciais para o agente começar a investigação.

## Decisão do Agente
O resultado final do [[Grafo LangGraph]]: [[Orientar]], [[Agir]] ou [[Escalar]].

## Detection Mode
Define como uma falha foi detectada:
- `baseline`: Por desvio do [[Baseline]] (ex: desalinhamento, desbalanceamento). Exige baseline `established`.
- `symptom`: Por sintoma direto, independente do [[Baseline]] (ex: lubrificação).

## Envelope de Resposta
Estrutura padrão (`{mode, notes, data}`) que a API retorna em cada consulta. O campo `mode` indica a qualidade e completude da resposta: `complete`, `partial`, `inconclusive`, `conflict`, `unavailable`.

## Escalar
Decisão do agente de encaminhar o [[Case]] para um analista humano quando o problema extrapola a capacidade de atendimento remoto do agente. Exige [[Justificativa]].

## Espectro (FFT)
Gráfico que revela falhas por frequência característica (ex: 1× desbalanceamento, 2× desalinhamento, BPFO/BPFI/BSF/FTF para rolamentos, 2× f-linha elétrica para falha elétrica).

## Grafo LangGraph
A estrutura de orquestração do agente. Define o fluxo de decisão: investigar → [[Quality Check Node]] → decidir → orientar/agir/escalar.

## Justificativa
Explicação obrigatória para toda [[Ação de Impacto]] ou [[Escalamento]] executado pelo agente. Garante rastreabilidade e responsabilidade.

## LLM (Large Language Model)
O modelo de linguagem (ex: Groq Llama 3.1) que o agente utiliza para processar texto, raciocinar e tomar decisões, chamando as [[Camada de Tools (MCP)]].

## MCP (Model Context Protocol)
Um padrão aberto para conectar aplicações de IA a sistemas externos, usado aqui para expor as operações da API Tractian como _tools_ ao agente.

## Orientar
Decisão do agente de explicar algo ao [[Cliente]] sem alterar o estado na plataforma.

## Pontos de Medição
Locais específicos em um [[Ativo]] onde os dados (ex: [[Série RMS]], [[Espectro]]) são coletados.

## Postgres Log
Um banco de dados Postgres (futuro) para registrar cada [[Execução do Agente]] (trace completo, decisão, timestamp) para fins de [[Avaliação do Agente]] e métricas.

## Quality Check Node
Um nó dedicado no [[Grafo LangGraph]] responsável por decidir o que fazer com respostas não-`complete` do [[Envelope de Resposta]] (aceitar, repetir, buscar dado faltante, ou [[Escalar]]). É o dono único dessa política de resiliência.

## Qualidade e Frescor dos Dados
Atributos como completude, relação sinal-ruído e atualidade dos dados. Afetam a capacidade dos modelos de inferir e a confiabilidade do [[Baseline]].

## Reprocessar Análise
[[Ação de Impacto]] que dispara um novo processamento de dados para uma análise existente, atualizando seu estado.

## Série RMS
Um tipo de dado de vibração de um [[Ativo]] ao longo do tempo, usado para monitorar a energia total da vibração. O [[Limiar de Alarme de RMS]] deriva do [[Baseline]].

## Solicitar Retreinamento
[[Ação de Impacto]] que solicita que um [[LLM]] seja retreinado com novos dados ou configurações, para melhorar sua performance.

## Stack
O conjunto de tecnologias usadas no projeto (ex: Python, LangGraph, MCP, Groq, FastAPI, Streamlit).

## Streamlit UI
Uma interface de usuário (futura) construída com Streamlit para demonstrar o agente em tempo real e visualizar suas interações. Ações de impacto exigirão confirmação humana aqui.

## Ticket (Case)
(Ver [[Case]])

## Trace da Execução
O registro detalhado de todas as etapas que o agente percorreu (chamadas de tools, decisões, pensamentos) durante a resolução de um [[Case]]. Essencial para depuração e [[Avaliação do Agente]].

## Venv (Virtual Environment)
Um ambiente Python isolado, onde as dependências do projeto são instaladas sem conflitar com outras instalações globais do Python.
