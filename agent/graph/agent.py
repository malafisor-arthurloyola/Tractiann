from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from .state import AgentState
from .nodes import investigate, quality_check, decide, respond, act, escalate

MAX_RETRIES = 3


def _core_count() -> int:
    """Quantidade de tools da investigação inicial (para calcular o limite de retry)."""
    from .nodes import CORE_TOOLS
    return len(CORE_TOOLS)


def route_after_quality(state: AgentState) -> str:
    """Roteamento após quality check.

    - ok / partial → decide (pode prosseguir, com os gaps registrados)
    - incomplete + ainda há next_tool → investigate (busca a tool específica que falta)
    - incomplete sem next_tool (já tentou backups) → decide (ciente das lacunas)
    - unavailable → escala (não tem como prosseguir com segurança)
    """
    verdict = state.get("quality_verdict", "ok")

    if verdict == "unavailable":
        return "escalate"

    if verdict == "incomplete" and state.get("next_tool"):
        # Limita o número de idas ao investigate
        calls = state.get("tools_called") or []
        if len(calls) - _core_count() < MAX_RETRIES:
            return "investigate"

    # ok, partial, incomplete-sem-backup → decide ciente das lacunas
    return "decide"


def route_after_decide(state: AgentState) -> str:
    """Roteamento após decisão do agente."""
    decision = state.get("decision", "orient")
    if decision == "act":
        return "act"
    if decision == "escalate":
        return "escalate"
    return "respond"


def build_graph() -> StateGraph:
    """Monta o grafo do agente industrial.

    Fluxo:
    investigate → quality_check → decide → (respond | act | escalate)
                         ↓
              incomplete + próxima tool → investigate (busca só a tool que falta)
              incomplete sem back-ups    → decide (ciente das lacunas)
              unavailable                → escalate
    """
    graph = StateGraph(AgentState)

    graph.add_node("investigate", investigate)
    graph.add_node("quality_check", quality_check)
    graph.add_node("decide", decide)
    graph.add_node("respond", respond)
    graph.add_node("act", act)
    graph.add_node("escalate", escalate)

    graph.set_entry_point("investigate")

    graph.add_edge("investigate", "quality_check")
    graph.add_conditional_edges(
        "quality_check",
        route_after_quality,
        {
            "decide": "decide",
            "investigate": "investigate",
            "escalate": "escalate",
        },
    )
    graph.add_conditional_edges(
        "decide",
        route_after_decide,
        {
            "respond": "respond",
            "act": "act",
            "escalate": "escalate",
        },
    )

    graph.add_edge("respond", END)
    graph.add_edge("act", END)
    graph.add_edge("escalate", END)

    # MemorySaver persiste o estado do grafo, permitindo o interrupt() (HITL)
    # pausar e depois retomar a execução de onde parou.
    return graph.compile(checkpointer=MemorySaver())


# Instância compilada do grafo
agent_graph = build_graph()
