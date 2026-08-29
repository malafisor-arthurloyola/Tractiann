from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
import os
from .state import AgentState
from ..tools.client import tractian_request


def _get_llm():
    """Cria o LLM sob demanda (lazy). Só falha se não tiver API key no momento do uso."""
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "llama-3.3-70b-versatile"),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1"),
        api_key=os.getenv("OPENAI_API_KEY", ""),
        temperature=0.3,
    )

# System prompt do agente
SYSTEM_PROMPT = """Você é um engenheiro de suporte da TRACTIAN. Você recebe tickets de clientes
e precisa investigar dados de ativos industriais para orientar, agir ou escalar.

## Regras
1. Sempre investigue ANTES de responder. Use as tools disponíveis para coletar evidências.
2. Nunca invente dados. Se a resposta da API vier incompleta, diga que não tem informação suficiente.
3. Ao orientar, fundamente sua resposta nas evidências coletadas.
4. Ao agir, justifique com pelo menos 20 caracteres.
5. Ao escalar, explique por que o caso extrapola o atendimento remoto.

## Fluxo
- Leia o ticket do cliente
- Identifique o ativo e a empresa
- Consulte baseline, análises, RMS, espectro, qualidade dos dados
- Interprete os dados e tome uma decisão
- Responda em linguagem simples ao cliente"""


async def investigate(state: AgentState) -> dict:
    """Nó de investigação: coleta dados da API via tools MCP.
    
    Lê o ticket e usa as tools para buscar contexto sobre
    o ativo, baseline, análises e dados técnicos.
    """
    asset_id = state["asset_id"]
    user_id = state["user_id"]
    
    # Coleta paralela de dados (simplificado: sequencial por agora)
    try:
        from ..tools.client import tractian_request
        baseline = tractian_request("GET", f"/assets/{asset_id}/baseline")
    except Exception:
        baseline = None
    
    try:
        analyses_raw = tractian_request("GET", f"/assets/{asset_id}/analyses")
        analyses = analyses_raw.get("data", []) if isinstance(analyses_raw, dict) else []
    except Exception:
        analyses = []
    
    try:
        rms_data = tractian_request("GET", f"/assets/{asset_id}/rms")
    except Exception:
        rms_data = None
    
    try:
        spectrum_data = tractian_request("GET", f"/assets/{asset_id}/spectrum")
    except Exception:
        spectrum_data = None
    
    try:
        data_quality = tractian_request("GET", f"/assets/{asset_id}/data-quality")
    except Exception:
        data_quality = None

    return {
        "baseline": baseline,
        "analyses": analyses,
        "rms_data": rms_data,
        "spectrum_data": spectrum_data,
        "data_quality": data_quality,
        "trace": [{"node": "investigate", "data_collected": bool(baseline or analyses)}],
    }


async def quality_check(state: AgentState) -> dict:
    """Nó de quality check: avalia se as respostas são suficientes.
    
    É o DONO ÚNICO da política de respostas incompletas.
    Decide: ok → segue, incomplete → tenta outro dado, unavailable → escala.
    """
    baseline = state.get("baseline")
    analyses = state.get("analyses", [])
    
    # Verifica envelope de resposta
    if baseline and isinstance(baseline, dict):
        mode = baseline.get("mode", "unknown")
        if mode in ("unavailable", "conflict"):
            return {
                "quality_verdict": "unavailable",
                "quality_notes": f"Baseline veio com modo: {mode}",
                "trace": [{"node": "quality_check", "verdict": "unavailable"}],
            }
        if mode == "partial":
            return {
                "quality_verdict": "partial",
                "quality_notes": "Baseline parcial — dados podem estar incompletos",
                "trace": [{"node": "quality_check", "verdict": "partial"}],
            }
    
    if not analyses:
        return {
            "quality_verdict": "incomplete",
            "quality_notes": "Nenhuma análise encontrada para o ativo",
            "trace": [{"node": "quality_check", "verdict": "incomplete"}],
        }
    
    return {
        "quality_verdict": "ok",
        "quality_notes": None,
        "trace": [{"node": "quality_check", "verdict": "ok"}],
    }


async def decide(state: AgentState) -> dict:
    """Nó de decisão: usa o LLM para decidir entre orientar, agir ou escalar.
    
    Alimenta o LLM com o ticket + dados coletados + resultado do quality check.
    """
    quality = state.get("quality_verdict", "ok")
    
    # Se quality check diz que dados estão indisponíveis, escala
    if quality == "unavailable":
        return {
            "decision": "escalate",
            "decision_justification": "Dados da API indisponíveis ou conflitantes — necessário intervenção humana.",
            "trace": [{"node": "decide", "decision": "escalate", "reason": "data_unavailable"}],
        }
    
    # Monta contexto para o LLM
    context_parts = [
        f"Ticket: {state['message']}",
        f"Ativo: {state['asset_id']}",
    ]
    
    baseline = state.get("baseline")
    if baseline and isinstance(baseline, dict):
        data = baseline.get("data", baseline)
        context_parts.append(f"Baseline: {data}")
    
    analyses = state.get("analyses", [])
    if analyses:
        context_parts.append(f"Análises: {analyses[:3]}")  # Limita a 3
    
    data_quality = state.get("data_quality")
    if data_quality:
        context_parts.append(f"Qualidade dos dados: {data_quality}")
    
    context_parts.append(f"Qualidade da resposta: {quality} - {state.get('quality_notes', 'ok')}")
    
    user_message = "\n".join(context_parts)
    
    llm = _get_llm()
    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_message),
    ])
    
    # Parse simplificado da decisão
    text = response.content.lower()
    if "agir" in text or "reprocessar" in text or "solicitar" in text:
        decision = "act"
    elif "escalar" in text or "humano" in text or "suporte" in text:
        decision = "escalate"
    else:
        decision = "orient"
    
    return {
        "decision": decision,
        "decision_justification": response.content,
        "response": response.content,
        "trace": [{"node": "decide", "decision": decision, "llm_response": response.content[:200]}],
    }


async def respond(state: AgentState) -> dict:
    """Nó de resposta: entrega a orientação ao cliente."""
    return {
        "trace": [{"node": "respond", "action": "orient", "response": state.get("response", "")[:100]}],
    }


async def act(state: AgentState) -> dict:
    """Nó de ação: executa ação na plataforma (placeholder — será integrado com interrupt)."""
    return {
        "trace": [{"node": "act", "action": state.get("decision"), "justification": state.get("decision_justification", "")[:100]}],
    }


async def escalate(state: AgentState) -> dict:
    """Nó de escalonamento: encaminha para humano."""
    return {
        "trace": [{"node": "escalate", "reason": state.get("decision_justification", "")[:100]}],
    }
