from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import interrupt
import os
from pathlib import Path
from dotenv import load_dotenv
from .state import AgentState
from ..tools.client import tractian_request

# Carrega .env do agent/ (sobe 2 níveis: graph/ → agent/)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _get_llm():
    """Cria o LLM sob demanda (lazy). Só falha se não tiver API key no momento do uso."""
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "openai/gpt-oss-20b"),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1"),
        api_key=os.getenv("OPENAI_API_KEY", ""),
        temperature=0.3,
    )


def _handle_request(category: str, asset_id: str, user_id: str) -> tuple[str, dict]:
    """Chama a tool certa pra uma categoria e devolve (a_chave, envelope).
    
    Usado tanto pela investigação inicial quanto pelo retry (próxima tool).
    """
    if category == "baseline":
        return "baseline", tractian_request("GET", f"/assets/{asset_id}/baseline", user_id=user_id)
    if category == "analyses":
        return "analyses", tractian_request("GET", f"/assets/{asset_id}/analyses", user_id=user_id)
    if category == "rms":
        return "rms", tractian_request("GET", f"/assets/{asset_id}/rms", user_id=user_id)
    if category == "spectrum":
        return "spectrum", tractian_request("GET", f"/assets/{asset_id}/spectrum", user_id=user_id)
    if category == "data_quality":
        return "data_quality", tractian_request("GET", f"/assets/{asset_id}/data-quality", user_id=user_id)
    if category == "knowledge":
        # Outra tool complementar: busca procedimento/palavra sobre o ativo
        return "knowledge", tractian_request(
            "GET", "/knowledge/search",
            params={"q": f"manutenção {asset_id}"},
        )
    raise ValueError(f"Categoria de tool desconhecida: {category}")


# Tools que devem SEMPRE ser tentadas na investigação inicial
CORE_TOOLS = ["baseline", "analyses", "rms", "spectrum", "data_quality"]
# Tools complementares, usadas quando um dado crítico ficou incompleto
BACKUP_TOOLS = ["knowledge"]


def investigate(state: AgentState) -> dict:
    """Nó de investigação: coleta dados da API via tools MCP.

    - Na 1ª passada, busca as 5 tools principais.
    - Se voltar do quality_check com `next_tool` (dado faltante), busca APENAS
      essa tool específica — em vez de repetir as mesmas 5.
    """
    asset_id = state["asset_id"]
    user_id = state["user_id"]
    raw = dict(state.get("raw") or {})
    tools_called = list(state.get("tools_called") or [])

    if state.get("next_tool"):
        # Retry: buscar só a tool que falta (ex: knowledge)
        tool = state["next_tool"]
        if tool not in tools_called:
            try:
                key, envelope = _handle_request(tool, asset_id, user_id)
                raw[key] = envelope
                tools_called.append(tool)
            except Exception as e:
                raw[tool] = {"mode": "unavailable", "notes": f"erro ao buscar {tool}: {e}", "data": None}
                tools_called.append(tool)
    else:
        # Primeira passada: 5 tools principais
        for tool in CORE_TOOLS:
            try:
                key, envelope = _handle_request(tool, asset_id, user_id)
                raw[key] = envelope
            except Exception as e:
                raw[tool] = {"mode": "unavailable", "notes": f"erro ao buscar {tool}: {e}", "data": None}
            tools_called.append(tool)

    return {
        "raw": raw,
        "tools_called": tools_called,
        "next_tool": None,
        "trace": [{"node": "investigate", "tools_called": tools_called}],
    }


def _extract_analyses_list(envelope: dict) -> list:
    if not isinstance(envelope, dict):
        return []
    data = envelope.get("data") or {}
    if isinstance(data, dict):
        return data.get("analyses", [])
    return []


def quality_check(state: AgentState) -> dict:
    """Nó de quality check: verifica o envelope de TODAS as tools.

    É o DONO ÚNICO da política de respostas não-completas.
    Para cada tool, registra honestamente os gaps em `data_gaps` (nunca some).
    Decide: ok / partial / incomplete / unavailable, e se precisa de outra tool.
    """
    raw = state.get("raw") or {}
    gaps: dict[str, list[str]] = {}
    verdict = "ok"
    notes = []

    # Verifica TODAS as tools que foram buscadas
    for cat, envelope in raw.items():
        if not isinstance(envelope, dict):
            gaps[cat] = ["resposta inválida"]
            continue
        mode = envelope.get("mode", "unknown")

        if mode in ("unavailable", "conflict", "inconclusive"):
            gaps[cat] = [f"mode={mode}: {envelope.get('notes','') or 'sem dado'}"]

            if cat in ("baseline", "analyses"):
                # Dado crítico indisponível → não dá pra decidir com segurança
                verdict = "unavailable"
                notes.append(f"{cat} indisponível ({mode})")
            else:
                # Dado secundário faltando → parcial, mas não impede decisão
                if verdict != "unavailable":
                    verdict = "partial"
                    notes.append(f"{cat} indisponível ({mode})")

        elif mode == "partial":
            gaps[cat] = ["dados parciais (campos omitidos)"]
            if verdict != "unavailable":
                verdict = "partial"
                notes.append(f"{cat} parcial")

    # Verifica se análises vieram vazias (dado crítico)
    analyses_env = raw.get("analyses")
    if isinstance(analyses_env, dict) and not _extract_analyses_list(analyses_env):
        if "analyses" not in gaps:
            gaps["analyses"] = ["nenhuma análise encontrada"]
        if verdict == "ok":
            verdict = "incomplete"
            notes.append("sem análises — tentando tool complementar")

    # Decide se precisa tentar outra tool (só quando há dado crítico faltando)
    next_tool = None
    if verdict in ("incomplete", "unavailable"):
        tried = set(state.get("tools_called") or [])
        for backup in BACKUP_TOOLS:
            if backup not in tried:
                next_tool = backup
                break

    return {
        "quality_verdict": verdict,
        "quality_notes": "; ".join(notes) if notes else None,
        "data_gaps": gaps,
        "next_tool": next_tool,
        "trace": [{"node": "quality_check", "verdict": verdict, "gaps": gaps, "next_tool": next_tool}],
    }


def decide(state: AgentState) -> dict:
    """Nó de decisão: usa o LLM para decidir entre orientar, agir ou escalar.
    
    O LLM recebe o ticket + dados coletados + os GAPS honestos (o que NÃO tinha),
    para tomar uma decisão ciente das lacunas.
    """
    verdict = state.get("quality_verdict", "ok")

    # Sem dado crítico → escala direto (não arrisca decidir sem informação)
    if verdict == "unavailable":
        return {
            "decision": "escalate",
            "decision_justification": (
                "Dados críticos indisponíveis (baseline/análises). Não é possível "
                "diagnosticar com segurança — necessário intervenção humana."
            ),
            "trace": [{"node": "decide", "decision": "escalate", "reason": "data_unavailable"}],
        }

    # Monta contexto com dados coletados E gaps registrados
    raw = state.get("raw") or {}
    parts = [
        f"Ticket: {state['message']}",
        f"Ativo: {state['asset_id']}",
        f"Qualidade da resposta: {verdict} ({state.get('quality_notes') or 'ok'})",
    ]

    for cat in ["baseline", "rms", "spectrum", "data_quality"]:
        env = raw.get(cat)
        if isinstance(env, dict) and env.get("mode") == "complete":
            parts.append(f"{cat}: {env.get('data')}")
        elif isinstance(env, dict):
            parts.append(f"{cat}: {env.get('mode')} (dado parcial/ausente)")

    analyses_list = _extract_analyses_list(raw.get("analyses", {}))
    if analyses_list:
        parts.append(f"Analyses ({len(analyses_list)}): {analyses_list[:3]}")

    # GAPS honestos — o que o agente NÃO teve
    gaps = state.get("data_gaps") or {}
    if gaps:
        parts.append(f"Lacunas de dados (importante considerar): {gaps}")

    context_text = "\n".join(parts)

    # Cache em disco: se este contexto já foi decidido antes, reusa (economiza token
    # em re-execuções de dev/avaliação). Chave = hash do prompt.
    cached = _cached_decision(context_text)
    if cached is not None:
        return {
            "decision": cached[0],
            "decision_justification": cached[1],
            "response": cached[1],
            "trace": [{"node": "decide", "decision": cached[0], "from_cache": True}],
        }

    llm = _get_llm()
    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=context_text),
    ])

    text = response.content.lower()
    if "agir" in text or "reprocessar" in text or "solicitar" in text or "retreinar" in text:
        decision = "act"
    elif "escalar" in text or "humano" in text or "intervenção" in text:
        decision = "escalate"
    else:
        decision = "orient"

    _write_decision_cache(context_text, decision, response.content)

    return {
        "decision": decision,
        "decision_justification": response.content,
        "response": response.content,
        "trace": [{"node": "decide", "decision": decision}],
    }


# --- Cache em disco de decisões (economiza tokens em re-execuções) ---

_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".run" / "llm_cache"


def _cache_key(context_text: str) -> str:
    import hashlib
    return hashlib.sha1(context_text.encode("utf-8")).hexdigest()


def _cached_decision(context_text: str):
    """Retorna (decision, response) em cache, ou None se não houver."""
    try:
        path = _CACHE_DIR / f"{_cache_key(context_text)}.json"
        if not path.exists():
            return None
        import json
        data = json.loads(path.read_text(encoding="utf-8"))
        return data["decision"], data["response"]
    except Exception:
        return None


def _write_decision_cache(context_text: str, decision: str, response: str) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        import json
        path = _CACHE_DIR / f"{_cache_key(context_text)}.json"
        path.write_text(
            json.dumps({"decision": decision, "response": response}),
            encoding="utf-8",
        )
    except Exception:
        pass


def respond(state: AgentState) -> dict:
    """Nó de resposta: entrega a orientação ao cliente."""
    return {
        "trace": [{"node": "respond", "action": "orient",
                   "response": (state.get("response") or "")[:120]}],
    }


def act(state: AgentState) -> dict:
    """Nó de ação: pausa para confirmação humana antes de executar."""
    decision = state.get("decision") or ""
    justification = state.get("decision_justification") or ""
    
    # Antes de executar qualquer ação de impacto, pede confirmação humana
    confirmed = interrupt({
        "type": "action_confirmation",
        "decision": decision,
        "justification": justification[:500],
        "asset_id": state.get("asset_id"),
        "ticket_id": state.get("ticket_id"),
        "gaps": state.get("data_gaps") or {},
    })
    
    if not confirmed:
        # Humano cancelou → escala em vez de agir
        return {
            "decision": "escalate",
            "decision_justification": (
                f"Ação '{decision}' cancelada pelo humano. "
                f"Justificativa original: {justification[:200]}"
            ),
            "trace": [{"node": "act", "action": "cancelled_by_human",
                       "original_decision": decision}],
        }
    
    # Humano confirmou → registra que a ação foi executada
    return {
        "trace": [{"node": "act", "action": decision,
                   "justification": justification[:120],
                   "confirmed_by": "human"}],
    }


def escalate(state: AgentState) -> dict:
    """Nó de escalonamento: encaminha para humano."""
    return {
        "trace": [{"node": "escalate",
                   "reason": (state.get("decision_justification") or "")[:120]}],
    }


# System prompt do agente
SYSTEM_PROMPT = """Você é um engenheiro de suporte da TRACTIAN. Você recebe tickets de clientes
e precisa investigar dados de ativos industriais para orientar, agir ou escalar.

## Regras
1. Sempre fundamente sua resposta nas evidências coletadas. Use A PENA os dados fornecidos.
2. Nunca invente dados. Se houver lacunas de dados, considere-as na sua decisão.
3. Ao escalar, explique por que o caso extrapola o atendimento remoto.

## Decisão
- ORIENTAR: explicar ao cliente, sem alterar nada.
- AGIR: executar ação (reprocessar análise, solicitar especialista, retreinar modelo). Justifique com >= 20 caracteres.
- ESCALAR: encaminhar a humano. Use quando dados críticos faltarem ou o caso for grave.

Responda iniciando com a palavra da decisão (ORIENTAR/AGIR/ESCALAR) seguida do texto."""
