---
tags: [streamlit, ui, interface, hitl, observabilidade]
aliases: [Streamlit, Interface, UI, Diagnostic Console]
---

# Streamlit Interface (Diagnostic Console)

## O que é
Interface web em Python puro (`app.py`) que atua como console de diagnóstico, demonstração e avaliação do Agente Industrial Tractian.

## Principais Recursos Implementados
1. **Monitoramento em Tempo Real (Header)**:
   - Badges dinâmicas de conectividade com API (`:8000`), Postgres (`:5432`), Phoenix Tracing (`:6006`) e provedor LLM (`Groq/OpenRouter`).
2. **Barra Lateral Reativa**:
   - Filtro de modalidade (`Todos`, `CTX`, `INV`, `EXE`) posicionado antes do dropdown para reatividade em tempo real.
   - Contadores estatísticos de tickets por tipo.
3. **Human-in-the-Loop (HITL) Interativo Real**:
   - O grafo pausa no nó `act` via `interrupt()` do LangGraph (`MemorySaver`).
   - Painel de confirmação humana com botões `✓ Confirmar (POST/PATCH)` e `✗ Cancelar (Escalar)`.
4. **Dossiê de Escalonamento (Handoff Técnico)**:
   - Quando a decisão é `escalate`, o sistema gera um card estruturado com: motivo da falha de dados, evidências vs lacunas, por que a IA não concluiu e checklist de ação para o engenheiro humano.
5. **Explorador Interativo de Pipeline do Grafo**:
   - Navegação nó a nó (`investigate`, `quality_check`, `decide`, `act`/`respond`/`escalate`) com inspeção de inputs, tools chamadas, envelopes brutos e telemetria.
6. **Visualização Gráfica de Sinais Industriais**:
   - Gráfico de série temporal RMS com linha de limiar de alarme (`alarm_threshold`).
   - Gráfico de barras de picos de frequência FFT (espectro de vibração com notas características como 1x, 2x, BPFO).
   - Painéis de estado do baseline e frescor dos dados.
7. **Juiz LLM Sob Demanda & Avaliação em Lote**:
   - Botão para julgar o ticket atual em 4 dimensões (Honestidade, Clareza, Fundamentação, Segurança).
   - Execução em batch nos splits `train` e `test`.
8. **Persistência no Postgres & Comparador de Versões**:
   - Gravação automática de cada execução na tabela `execucoes`.
   - Comparador de distribuição de decisões e acurácia entre versões (`v1`, `v2`, etc.).
9. **Modo Playground**:
   - Sandbox para criar e testar tickets livres com qualquer empresa, ativo e mensagem.

## Como rodar
```bash
make up-all       # Sobe API + Streamlit
make up-agent     # Sobe apenas o Streamlit (:8501)
```

## Relacionado
- [[Human-in-the-loop]]
- [[Grafo LangGraph]]
- [[Escalamento]]
- [[Observabilidade Postgres LangSmith Phoenix]]
- [[Avaliação do Agente]]
