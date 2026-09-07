from langgraph.graph import StateGraph, END
from .checkpointer import build_checkpointer
from .state import AgentState
from .nodes import investigate, quality_check, decide, respond, act, escalate

MAX_RETRIES = 3


def _core_count() -> int:
    """Quantidade de tools da investigação inicial (para calcular o limite de retry)."""
    from .nodes import CORE_TOOLS
    return len(CORE_TOOLS)


def route_after_quality(state: AgentState) -> str:
    """Roteamento após quality check.

    Enquanto houver evidência compensatória a buscar e orçamento de rodadas,
    volta para `investigate`. Caso contrário segue para `decide` — que decide
    sempre, ciente das lacunas.

    O quality_check não bloqueia mais: nenhum veredicto manda direto para
    `escalate`. Quem decide escalar é o LLM, olhando a evidência real.
    """
    if state.get("next_tool"):
        calls = state.get("tools_called") or []
        if len(calls) - _core_count() < MAX_RETRIES:
            return "investigate"
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
              há evidência compensatória e orçamento → investigate
              caso contrário                          → decide (ciente das lacunas)
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

    # O checkpointer guarda o estado do grafo, permitindo que o interrupt() (HITL)
    # pause a execução e alguém a retome depois. Ele é persistente (Postgres)
    # sempre que o banco responde: é o que permite que a ingestão pause um ticket
    # num processo e a interface o retome em outro, horas depois.
    return graph.compile(checkpointer=build_checkpointer())


# Instância compilada do grafo
agent_graph = build_graph()
