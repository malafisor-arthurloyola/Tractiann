# CONTEXT.md — Glossário de Domínio do Agente Industrial Tractian

> Este arquivo dá nomes estáveis aos conceitos do domínio. Todo código, ADR e revisão de
> arquitetura deve usar exatamente estas definições — nunca variantes vagas como
> "o serviço", "o componente" ou "a API" quando um termo abaixo se aplica.

## Papel do agente
Trata-se de um **engenheiro de suporte simulado**: recebe um ticket (texto do cliente +
contexto de empresa/ativo/usuário) e precisa **orientar**, **agir** ou **escalar**.

## Termos do domínio

- **Ticket (case)** — solicitação de suporte. Contém texto do cliente + contexto
  (empresa, usuário, ativo). É a entrada do agente. Na avaliação, cada ticket vira um cenário.

- **Ativo (asset)** — a máquina/equipamento monitorado (ex.: motor M-605, bomba B-204).
  Tem pontos de medição, análises, baseline, série RMS, espectro e qualidade de dados.

- **Baseline** — o "estado normal" aprendido **do próprio ativo** a partir de histórico sadio.
  Estado é `learning` (dados insuficientes) → `established` (confiável) → `invalidated`
  (mudança física invalidou o histórico; exige reaprendizado). O limiar de alarme de RMS
  **deriva do baseline** (referência + tolerância), não de norma ISO.

- **Insight / Análise** — diagnóstico automático do modelo para um ativo. Contém tipo,
  severidade, confiança, evidência, limitações e `detection_mode`.

- **Detection mode** — como a falha foi detectada:
  - `baseline` — desvio do aprendido (desalinhamento, desbalanceamento, rolamento, elétrica).
    Exige baseline `established`.
  - `symptom` — sintoma por si só já indica a falha (ex.: lubrificação). Independe do baseline.

- **Espectro (FFT)** — revela falhas por frequência característica
  (1× desbalanceamento, 2× desalinhamento, BPFO/BPFI/BSF/FTF rolamentos, 2× f-linha elétrica).

- **Qualidade e frescor dos dados** — completude, relação sinal-ruído e atualidade. Afetam a
  capacidade de inferir e a confiabilidade do baseline.

- **Envelope de resposta** — toda resposta de consulta da API vem num envelope com campos
  de modo. Os modos possíveis: `complete`, `partial`, `inconclusive`, `conflict`,
  `unavailable`. **O agente é quem decide** o que fazer com modos não-completos — não a tool.

- **Ação de impacto** — operação que altera estado na plataforma (reprocessar análise,
  solicitar análise especialista, solicitar retreinamento, alterar config, escalar caso).
  Exige justificativa e, para algumas, perfil/permissão adequada.

- **Decisão do agente** — resultado do grafo:
  - **orientar** — explicar, sem alterar nada;
  - **agir** — executar ação justificada na plataforma;
  - **escalar** — encaminhar para humano quando o caso extrapola o atendimento remoto.

## Estruturas do fluxo
- **Camada de tools (MCP)** — as 17 operações da API expostas como tools via FastMCP.
  Consumidas pelo agente para investigar e agir.
- **Grafo (LangGraph)** — orquestra o loop: investigar → (quality check) → decidir →
  orientar/agir/escalar.
- **Quality check node** — nó responsável por decidir o que fazer com respostas não-completas
  (aceitar / repetir / buscar dado faltante / escalar). É o dono único dessa política.
