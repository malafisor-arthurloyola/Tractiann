from typing import TypedDict, Literal, Annotated
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage


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
    company_info: dict | None
    asset_info: dict | None
    baseline: dict | None
    analyses: list[dict]
    rms_data: dict | None
    spectrum_data: dict | None
    data_quality: dict | None
    model_info: dict | None
    knowledge_docs: list[dict]

    # --- Resultado do quality check ---
    quality_verdict: Literal["ok", "partial", "incomplete", "unavailable"] | None
    quality_notes: str | None

    # --- Decisão do agente ---
    decision: Literal["orient", "act", "escalate"] | None
    decision_justification: str | None

    # --- Resposta final ---
    response: str | None

    # --- Trace da execução (para avaliação) ---
    trace: Annotated[list[dict], add_messages]
