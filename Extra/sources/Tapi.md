# Engenharia e Avaliação de Agentes Industriais

```
● Parceiro: TRACTIAN
● Instituição: Inteli
● Formato: projeto individual
● Duração estimada: 1 mês
```
## 1. Contextualização do problema

A TRACTIAN apoia indústrias no monitoramento da condição de máquinas e na gestão da
manutenção. Uma solicitação de suporte pode exigir dados do ativo, análises anteriores,
qualidade dos sinais, cobertura dos modelos e ações dentro da plataforma.
Agentes de IA podem organizar essa investigação. O modelo recebe uma solicitação,
consulta recursos especializados, interpreta os retornos e decide o próximo passo. Esse fluxo
exige integrações bem construídas e critérios claros para orientar, agir ou escalar.
Estudos como ReAct, Toolformer e TAU-bench mostram o potencial de agentes com
ferramentas e os desafios de confiabilidade, uso consistente de APIs e execução de políticas
em múltiplas interações.
O projeto oferece um ambiente controlado para explorar engenharia e avaliação de
agentes. Cada estudante trabalhará sobre uma API industrial simplificada, com dados fictícios e
cenários inspirados em situações de suporte.

## 2. Objetivo do projeto

```
Desenvolver uma solução aplicada a agentes industriais contendo:
```
1. **Construção de agente** : criar um agente capaz de interpretar solicitações, consultar a
    API fornecida e conduzir ações adequadas.
2. **Framework de avaliação de agentes** : criar um processo, utilizar biblioteca ou
    aplicação para investigar a qualidade e a confiabilidade de agentes que utilizam a API
    fornecida.
Toda entrega deverá incluir integração com a API, experimento técnico e documentação
dos resultados.

## 3. Pergunta norteadora

**Como construir ou avaliar agentes de IA capazes de usar sistemas industriais com
precisão, interpretar evidências e executar ações adequadas ao contexto?**


## 4. Contexto de uso

A solução deve atender solicitações do cliente de três formas:
● Contextualizar: acessar conhecimento e explicar ao usuário de forma responsável;
● Investigar: usar ferramentas para estudar de forma especialista as máquinas do cliente
para recomendar ações e explicar eventos;
● Executar: usar ferramentas que vão ter impacto na solução para o cliente.
As ações podem incluir:
● solicitar informações adicionais (Contextualizar);
● consultar ativos, análises e dados técnicos (Investigar);
● realizar perguntas pertinentes (Investigar);
● executar ações justificadas na plataforma (Executar);
● encaminhar o caso para análise humana (Executar).
Os dados técnicos estarão em formatos didáticos e simplificados. O desafio está na
integração, no comportamento do agente e na análise dos resultados.

## 5. Recursos fornecidos pela TRACTIAN

A TRACTIAN disponibilizará uma API funcional com contratos Swagger e dados sintéticos
gerados a partir de casos reais anonimizados.
Os casos internos servirão apenas como inspiração para criar empresas, ativos, análises e
situações simuladas. O material entregue aos estudantes não utilizará dados pessoais,
formatos internos ou informações identificáveis de clientes.
A API representará recursos de uma plataforma industrial. Categorias e exemplos:
Categoria Exemplos de recursos e operações
Contexto empresa fictícia, perfil da pessoa usuária, permissões e ativos
relacionados
Ativos cadastro, criticidade, hierarquia e configuração técnica
Análises resultados anteriores, evidências, confiança e limitações
Dados técnicos disponibilidade, qualidade, atualidade, espectros e sinais simplificados
Modelos versão, cobertura, requisitos e estado de processamento
Conhecimento procedimentos, glossário e orientações de suporte


```
Categoria Exemplos de recursos e operações
Ações solicitar análise especializada, reprocessar análise, solicitar retreinamento
e alterar configurações técnicas
A lista final de endpoints e parâmetros será apresentada no contrato da API.
```
### 5.1 Comportamento da API

Os endpoints de consulta poderão apresentar variações probabilísticas, por exemplo:
● retorno completo;
● informação parcial;
● resultado inconclusivo;
● conflito entre fontes;
● indisponibilidade temporária.
As ações de maior impacto exigirão parâmetros válidos e justificativa adequada. Uma
chamada aceita representará a execução da ação e retornará sucesso, sem ciclo adicional de
status.

## 6. Entregáveis

**Construção do Agente**
O estudante construirá a camada de integração entre a API e o agente. São aceitas tools,
servidor MCP ou abordagem equivalente.
A solução poderá explorar:
● interpretação dos contratos HTTP;
● definição de tools e schemas;
● seleção de funções;
● construção dos argumentos;
● planejamento e política de parada;
● tratamento de retornos incompletos e falhas;
● fundamentação das respostas;
● memória e contexto entre interações;
● decisão entre orientar, agir ou escalar; e
● rastreabilidade da execução.
O agente pode operar em atendimento direto, como copiloto ou em fluxos autônomos com
escopo definido.


```
Framework de avaliação de agentes
Nesta trilha, o estudante investigará formas de avaliar agentes que usam a API fornecida.
O formato da entrega permanece aberto. Exemplos:
● suíte de testes;
● biblioteca de métricas;
● runner de cenários;
● aplicação para inspeção de traces;
● geração de casos adversariais;
● avaliação de robustez e consistência; e
● processo de captura, anonimização e reprodução de execuções.
Objetos de análise:
```
1. escolha das funções;
2. acurácia dos argumentos;
3. trajetória de execução;
4. uso das evidências;
5. qualidade da resposta;
6. segurança;
7. desempenho diante de falhas;
8. estabilidade entre execuções; e
9. comportamento em ações de maior impacto.
Cada estudante deverá formular uma hipótese, justificar os métodos escolhidos e analisar
as limitações do experimento.
**Documentação comum**
O README deverá apresentar:
● problema escolhido;
● trilha e recorte da solução;
● arquitetura;
● instalação e execução;
● modelos e configurações;
● metodologia experimental;
● resultados;
● limitações; e
● possibilidades de evolução.


```
None
```
## 8. Arquitetura de referência

Solicitação ou objetivo
↓
Agente ou sistema avaliado
↓
Tools, MCP ou integração equivalente
↓
API industrial Tractian
↓
Consultas e ações na plataforma
↓
Resposta, orientação, execução ou escalonamento
↓
Trace e resultados do experimento
A arquitetura pode usar um agente único ou componentes especializados. A implementação
deve permitir inspeção das chamadas e dos resultados.

## 9. Tecnologias sugeridas

A referência de viabilidade são modelos abertos, execução local e opções gratuitas. Cada
estudante deverá registrar o modelo, a versão, as configurações e as limitações observadas.
● Python: implementação principal.
● FastAPI, Flask ou cliente HTTP equivalente: consumo e exploração dos contratos da
API.
● LangGraph, LangChain, Pydantic AI ou SDK equivalente: orquestração e chamadas de
ferramentas.
● MCP SDK: criação de uma camada MCP, caso essa abordagem seja escolhida.
● Pydantic ou JSON Schema: validação de entradas e saídas.
● pytest: automação de testes e experimentos.
● pandas e Plotly: análise e visualização de resultados.
● Streamlit ou Gradio: interface de demonstração.
● Modelos abertos ou roteadores gratuitos: execução dos agentes e avaliações.
RAG, busca híbrida, reranking e observabilidade podem complementar a solução quando
contribuírem para o experimento.


## 11. Critérios gerais de avaliação

A avaliação acadêmica utilizará uma rubrica flexível, compatível com a trilha e o escopo
declarados.
Critérios gerais:
● qualidade da integração com a API;
● coerência técnica da solução;
● clareza da hipótese e do experimento;
● qualidade da análise dos resultados;
● tratamento de limitações e riscos;
● reprodutibilidade;
● documentação; e
● qualidade da demonstração.

## 12. Materiais recomendados

```
● ReAct: raciocínio intercalado com ações e observações.
● Toolformer: aprendizado de quando e como usar APIs externas.
● TAU-bench: avaliação de agentes em conversas com tools e políticas de domínio.
● LangGraph: construção de fluxos com estado e transições condicionais.
● LangChain Agents: definição e execução de agentes com ferramentas.
● Model Context Protocol: padrão aberto para conectar aplicações de IA a sistemas
externos.
● OpenAI Evals: exemplos de estruturas de avaliação.
● promptfoo: testes e comparação de aplicações com LLMs.
● DeepEval: métricas e testes para sistemas com LLMs.
● Phoenix: traces, observabilidade e avaliação.
● Eval-driven development: Lessons from evaluating GenAI at scale: Artigo do Airbnb
Tech Blog
```
## 13. Datas importantes

```
● Onboarding e discussão com o parceiro: 13 de agosto de 2026
● Apresentação e entrega final: 08 de setembro de 2026
```

