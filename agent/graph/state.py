from typing import TypedDict, Literal, Annotated
import operator


class AgentState(TypedDict):
    """Estado compartilhado entre todos os nós do grafo.
    
    Cada nó lê e escreve neste estado. O LangGraph garante
    que as atualizações são feitas de forma thread-safe.
    """
    # --- Entrada ---
    ticket_id: str
    case_id: str
    company_id: str
    user_id: str
    asset_id: str
    message: str  # Texto do cliente

    # --- Contexto coletado pela investigação ---
    # Envelopes brutos, por categoria (category -> envelope {mode, notes, data})
    raw: dict[str, dict]
    # Recursos específicos extraídos (para o nó de decisão usar)
    baseline: dict | None
    analyses: list[dict]
    rms_data: dict | None
    spectrum_data: dict | None
    data_quality: dict | None

    # --- Resultado do quality check ---
    quality_verdict: Literal["ok", "partial", "incomplete", "unavailable"] | None
    quality_notes: str | None
    # Registro honesto do que faltou: category -> lista de problemas (nunca some)
    data_gaps: Annotated[dict[str, list[str]], operator.or_]
    # Próxima tool a tentar (quando incomplete), p/ investigar buscar dado faltante
    next_tool: str | None
    # Tools já tentadas (não repetir)
    tools_called: Annotated[list[str], operator.add]

    # --- Decisão do agente ---
    decision: Literal["orient", "act", "escalate"] | None
    decision_justification: str | None

    # --- Resposta final ---
    response: str | None

    # --- Trace da execução (para avaliação) ---
    trace: Annotated[list[dict], operator.add]
