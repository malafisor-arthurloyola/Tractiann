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
   - O grafo pausa no nó `act` via `interrupt()` do LangGraph, com checkpoint no **Postgres** (`PostgresSaver`).
   - Painel de confirmação humana com botões `✓ Confirmar (POST/PATCH)` e `✗ Cancelar (Escalar)`.
4. **Aba Notificações — caixa de entrada do operador**:
   - Lista as ações congeladas lendo a tabela `fila_aprovacoes`, não a sessão do navegador.
   - Por isso mostra o que **outro processo** pausou: os tickets ingeridos por `make demo`
     aparecem aqui esperando decisão, e continuam lá depois de reiniciar a interface.
   - Cada item traz ação, alvo, justificativa, lacunas de dado reconhecidas e há quanto
     tempo espera; aprovar chama `Command(resume=True)` no `thread_id` gravado na fila.
   - Abaixo: taxa de autonomia por conjunto e acerto de decisão, ambos contados no banco.
5. **Dossiê de Escalonamento (Handoff Técnico)**:
   - Quando a decisão é `escalate`, o sistema gera um card estruturado com: motivo da falha de dados, evidências vs lacunas, por que a IA não concluiu e checklist de ação para o engenheiro humano.
6. **Explorador Interativo de Pipeline do Grafo**:
   - Navegação nó a nó (`investigate`, `quality_check`, `decide`, `act`/`respond`/`escalate`) com inspeção de inputs, tools chamadas, envelopes brutos e telemetria.
7. **Visualização Gráfica de Sinais Industriais**:
   - Gráfico de série temporal RMS com linha de limiar de alarme (`alarm_threshold`).
   - Gráfico de barras de picos de frequência FFT (espectro de vibração com notas características como 1x, 2x, BPFO).
   - Painéis de estado do baseline e frescor dos dados.
8. **Juiz LLM Sob Demanda & Avaliação em Lote**:
   - Botão para julgar o ticket atual em 4 dimensões (Honestidade, Clareza, Fundamentação, Segurança).
   - Execução em batch nos splits `train` e `test`.
9. **Persistência no Postgres & Comparador de Versões**:
   - Gravação automática de cada execução na tabela `execucoes`.
   - Comparador de distribuição de decisões e acurácia entre versões (`v1`, `v2`, etc.).
10. **Modo Playground**:
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
