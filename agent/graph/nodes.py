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
    """Nó de investigação: coleta dados da API via tools HTTP.

    - Na 1ª passada, busca as 5 tools principais.
    - Se voltar do quality_check com `next_tool`, busca APENAS essa tool.

    Retorna APENAS os tools chamados NESTA passada (não a lista inteira),
    pois `tools_called` usa Annotated[list, operator.add] que appenda.
    """
    asset_id = state["asset_id"]
    user_id = state["user_id"]
    raw = dict(state.get("raw") or {})

    if state.get("next_tool"):
        tool = state["next_tool"]
        try:
            key, envelope = _handle_request(tool, asset_id, user_id)
            raw[key] = envelope
        except Exception as e:
            raw[tool] = {"mode": "unavailable", "notes": f"erro ao buscar {tool}: {e}", "data": None}
        new_tools = [tool]
    else:
        new_tools = []
        for tool in CORE_TOOLS:
            try:
                key, envelope = _handle_request(tool, asset_id, user_id)
                raw[key] = envelope
            except Exception as e:
                raw[tool] = {"mode": "unavailable", "notes": f"erro ao buscar {tool}: {e}", "data": None}
            new_tools.append(tool)

    return {
        "raw": raw,
        "tools_called": new_tools,
        "next_tool": None,
        "trace": [{"node": "investigate", "tools_called": new_tools}],
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


def _extract_first_analysis_id(raw: dict) -> str | None:
    """Pega o primeiro analysis_id disponível nas análises coletadas."""
    analyses = _extract_analyses_list(raw.get("analyses", {}))
    for a in analyses:
        if isinstance(a, dict) and a.get("id"):
            return a["id"]
    return None


def _extract_action(decision_text: str, state: AgentState) -> tuple[str, str]:
    """Determina (action_type, action_target) a partir do texto do LLM + dados.

    O LLM decide "AGIR", mas precisamos saber QUAL ação e EM QUAL alvo. Mapeamos
    por palavras-chave no texto e pelo alvo disponível (primeira análise, modelo,
    ou o próprio ativo).
    """
    asset_id = state.get("asset_id") or ""
    text = (decision_text or "").lower()
    raw = state.get("raw") or {}

    # Prioridade de palavras-chave (regras do gabarito)
    if "retrein" in text or "retrain" in text:
        model_id = _find_model_id(raw)
        return "retrain", model_id or "mdl_vib_v3"
    if "config" in text or "criticidade" in text or "critical" in text:
        return "update_config", asset_id
    if "especialista" in text or "specialist" in text:
        aid = _extract_first_analysis_id(raw)
        return "specialist", aid or ""
    if "reprocess" in text or "reprocessar" in text:
        aid = _extract_first_analysis_id(raw)
        return "reprocess", aid or ""
    # Fallback
    return "reprocess", _extract_first_analysis_id(raw) or ""


def _find_model_id(raw: dict) -> str | None:
    """Procura um model_id real (field `id`) num envelope de models, se houver."""
    models_env = raw.get("models")
    if isinstance(models_env, dict):
        data = models_env.get("data") or {}
        if isinstance(data, dict) and data.get("id"):
            return data["id"]
    return None


def decide(state: AgentState) -> dict:
    """Nó de decisão: usa o LLM para decidir entre orientar, agir ou escalar.
    
    O LLM recebe o ticket + dados coletados + os GAPS honestos (o que NÃO tinha),
    para tomar uma decisão ciente das lacunas.
    """
    verdict = state.get("quality_verdict", "ok")

    # Sem dado crítico → escala direto com dossiê técnico estruturado
    if verdict == "unavailable":
        raw = state.get("raw") or {}
        base_mode = raw.get("baseline", {}).get("mode", "inconclusivo")
        an_mode = raw.get("analyses", {}).get("mode", "indisponível")
        gaps_list = list(state.get("data_gaps", {}).keys())
        gaps_str = ", ".join(gaps_list) if gaps_list else "baseline / análises"

        dossie = (
            f"📋 DOSSIÊ DE ESCALONAMENTO PARA SUPORTE TÉCNICO HUMANO\n\n"
            f"1. Motivo do Escalonamento: Dados críticos essenciais para diagnóstico seguro estão indisponíveis na API (Baseline={base_mode}, Análises={an_mode}).\n"
            f"2. Evidências Coletadas vs Lacunas: O sinal de RMS foi obtido, porém as lacunas em [{gaps_str}] impedem a validação técnica do limiar de alarme.\n"
            f"3. Por que a IA não concluiu: Na Tractian, o limiar de vibração deriva do Baseline aprendido do ativo específico. Sem histórico homologado, não é seguro certificar se o alarme é real ou descalibração.\n"
            f"4. Checklist de Ação para o Engenheiro de Suporte:\n"
            f"   - [ ] Esclarecer ao cliente que o alarme é dinâmico (calculado pelo histórico da máquina) e não uma norma fixa.\n"
            f"   - [ ] Inspecionar conectividade e qualidade do sensor no ativo '{state.get('asset_id')}'.\n"
            f"   - [ ] Verificar se o baseline deste ativo precisa ser restabelecido na plataforma."
        )

        return {
            "decision": "escalate",
            "decision_justification": dossie,
            "response": dossie,
            "trace": [{"node": "decide", "decision": "escalate", "reason": "critical_data_unavailable", "gaps": gaps_list}],
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
        decision = cached[0]
        if decision == "act":
            action_type, action_target = _extract_action(cached[1], state)
        else:
            action_type, action_target = None, None
        return {
            "decision": decision,
            "decision_justification": cached[1],
            "response": cached[1],
            "action_type": action_type,
            "action_target": action_target,
            "trace": [{"node": "decide", "decision": decision, "from_cache": True}],
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

    if decision == "act":
        action_type, action_target = _extract_action(response.content, state)
    else:
        action_type, action_target = None, None

    return {
        "decision": decision,
        "decision_justification": response.content,
        "response": response.content,
        "action_type": action_type,
        "action_target": action_target,
        "trace": [{"node": "decide", "decision": decision, "action": action_type}],
    }


# --- Cache em disco de decisões (economiza tokens em re-execuções) ---

_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".run" / "llm_cache"


def _cache_key(context_text: str) -> str:
    """Chave = hash(versão + contexto). Mudar AGENT_VERSION invalida o cache."""
    import hashlib
    from ..version import AGENT_VERSION
    payload = f"{AGENT_VERSION}:{context_text}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


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


def _build_action_url(action_type: str, target: str) -> tuple[str, str]:
    """Mapeia action_type + target para (method, path) da API."""
    if action_type == "reprocess":
        return "POST", f"/analyses/{target}/reprocess"
    if action_type == "specialist":
        return "POST", f"/analyses/{target}/request-specialist"
    if action_type == "retrain":
        return "POST", f"/models/{target}/request-retraining"
    if action_type == "update_config":
        return "PATCH", f"/assets/{target}"
    return "POST", f"/cases/{target}/escalate"


def act(state: AgentState) -> dict:
    """Nó de ação: pausa para HITL, depois executa POST/PATCH real na API."""
    decision = state.get("decision") or ""
    justification = state.get("decision_justification") or ""
    action_type = state.get("action_type")
    action_target = state.get("action_target")
    user_id = state.get("user_id") or ""
    case_id = state.get("case_id") or ""

    # 1. Pede confirmação humana antes de qualquer mutação
    confirmed = interrupt({
        "type": "action_confirmation",
        "decision": decision,
        "action_type": action_type,
        "action_target": action_target,
        "justification": justification[:500],
        "asset_id": state.get("asset_id"),
        "ticket_id": state.get("ticket_id"),
        "gaps": state.get("data_gaps") or {},
    })

    if not confirmed:
        return {
            "decision": "escalate",
            "decision_justification": (
                f"Ação '{action_type}' no '{action_target}' cancelada pelo humano. "
                f"Justificativa original: {justification[:200]}"
            ),
            "trace": [{"node": "act", "action": "cancelled_by_human",
                       "action_type": action_type, "action_target": action_target}],
        }

    # 2. Executa a ação real na API
    if not action_type or not action_target:
        return {
            "trace": [{"node": "act", "action": "skipped",
                       "reason": "action_type ou action_target ausente"}],
        }

    # Para escalate, usa case_id; para as demais, o action_target
    effective_target = case_id if action_type == "escalate" else action_target
    method, path = _build_action_url(action_type, effective_target)

    try:
        result = tractian_request(
            method=method,
            path=path,
            user_id=user_id,
            json_data={"justification": justification},
        )
        action_id = result.get("action_id", "?")
        message = result.get("message", "")
    except Exception as e:
        action_id = None
        message = f"ERRO {e}"

    return {
        "trace": [{"node": "act", "action": decision, "action_type": action_type,
                   "action_target": action_target, "api_result": message,
                   "action_id": action_id, "confirmed_by": "human"}],
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
