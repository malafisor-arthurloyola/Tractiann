from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from .state import AgentState
from .nodes import investigate, quality_check, decide, respond, act, escalate


def route_after_quality(state: AgentState) -> str:
    """Roteamento após quality check.
    
    - ok/partial → decide (pode prosseguir com dados parciais)
    - incomplete → investiga mais (tenta buscar dados faltantes)
    - unavailable → escala (não tem como prosseguir)
    """
    verdict = state.get("quality_verdict", "ok")
    if verdict == "unavailable":
        return "escalate"
    if verdict == "incomplete":
        return "investigate"  # Tenta buscar dados faltantes
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
                    incomplete → investigate (loop)
                    unavailable → escalate
    """
    graph = StateGraph(AgentState)
    
    # Adiciona nós
    graph.add_node("investigate", investigate)
    graph.add_node("quality_check", quality_check)
    graph.add_node("decide", decide)
    graph.add_node("respond", respond)
    graph.add_node("act", act)
    graph.add_node("escalate", escalate)
    
    # Ponto de entrada
    graph.set_entry_point("investigate")
    
    # Arestas
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
    
    # Nós finais
    graph.add_edge("respond", END)
    graph.add_edge("act", END)
    graph.add_edge("escalate", END)
    
    return graph.compile()


# Instância compilada do grafo
agent_graph = build_graph()
