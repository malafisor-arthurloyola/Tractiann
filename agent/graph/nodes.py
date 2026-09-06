"""Nós do grafo do agente industrial.

Fluxo: investigate → quality_check → decide → (respond | act | escalate)

Duas ideias governam este módulo:

1. **O quality_check anota, não bloqueia.** A API industrial é probabilística de
   propósito. Um envelope degradado quase nunca significa "não dá para decidir":
   `conflict` devolve o payload inteiro mais um flag, e `partial` só remove
   campos secundários. Quem decide é o LLM, ciente das lacunas — o nó só
   classifica a força da evidência.

2. **Evidência compensatória, nunca retry.** `resolve_mode` na API é um hash
   determinístico de (seed, recurso, categoria): repetir o mesmo GET devolve
   exatamente o mesmo envelope, sempre. Quando um dado falha, o agente busca
   *outro* endpoint que responda à mesma pergunta.

Toda ida à API passa pela camada MCP (`agent/tools/mcp_client.call_tool`), como
manda o ADR-0001 — os nós não conhecem URLs, só nomes de tool.
"""
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from ..llm import build_llm, modelo_efetivo
from ..logging.phoenix import record_node
from ..tools.mcp_client import call_tool
from .state import AgentState

# Carrega .env do agent/ (sobe 2 níveis: graph/ → agent/)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _get_llm(structured_output=None, include_raw: bool = False):
    """LLM sob demanda (lazy), com fallback entre provedores.

    Ver `agent/llm.py`: se a cota do provedor principal acabar, a chamada cai
    automaticamente no próximo configurado.
    """
    return build_llm(temperature=0.3, structured_output=structured_output,
                     include_raw=include_raw)


# ---------------------------------------------------------------------------
# Camada de tools — categorias que o agente sabe buscar
# ---------------------------------------------------------------------------

# Buscadas sempre, na primeira passada.
# `asset_info` entra aqui porque quase todo raciocínio depende dela: traz
# sensor_status, machine_type, rotation_rpm e as frequências características
# (bpfo/bpfi/bsf/ftf, line_frequency) — sem elas é impossível ler um espectro.
CORE_TOOLS = ["asset_info", "baseline", "analyses", "rms", "spectrum", "data_quality"]

# Buscadas só como evidência compensatória, quando algo do núcleo falhou.
COMPENSATORY_TOOLS = ["model", "knowledge", "analysis_detail"]

# A API não expõe operação de listar modelos entre as 17; o dataset tem um
# único modelo. Configurável para não ficar cravado no código.
DEFAULT_MODEL_ID = os.getenv("TRACTIAN_DEFAULT_MODEL_ID", "mdl_vib_v3")

# `search_knowledge` faz `contains` da query inteira contra título/corpo, então
# só termo curto casa. Mapeia sinais do ticket para o termo que acha o documento.
_KNOWLEDGE_TERMS: list[tuple[tuple[str, ...], str]] = [
    (("rolamento", "bearing", "bpfo", "bpfi"), "rolamento"),
    (("eletric", "elétric", "fase", "tensao", "tensão"), "eletric"),
    (("lubrific", "graxa", "sintoma"), "sintom"),
    (("rms", "limiar", "alarme", "threshold", "tendencia", "tendência"), "rms"),
    (("desbalance", "desalinha", "1x", "2x", "espectro", "fft"), "rms"),
]


def _knowledge_query(message: str) -> str:
    """Escolhe um termo de busca a partir do texto do ticket.

    A versão anterior buscava `f"manutenção {asset_id}"` — procurar um id de
    ativo numa base de documentos nunca dava match.
    """
    text = (message or "").lower()
    for needles, term in _KNOWLEDGE_TERMS:
        if any(n in text for n in needles):
            return term
    return "baseline"


def _first_analysis_id(raw: dict) -> str | None:
    """Primeiro analysis_id disponível na lista de análises coletada."""
    for a in _extract_analyses_list(raw.get("analyses", {})):
        if isinstance(a, dict) and a.get("id"):
            return a["id"]
    return None


def _handle_request(category: str, state: AgentState, raw: dict) -> tuple[str, dict]:
    """Chama a tool MCP de uma categoria e devolve (chave, envelope).

    Mapeia a categoria interna (o que o agente quer saber) para o operationId da
    tool MCP (como a API expõe). Recebe `raw` porque as tools compensatórias
    dependem do que já foi coletado — o id da análise a detalhar, por exemplo.
    """
    asset_id = state["asset_id"]

    if category == "asset_info":
        return "asset_info", call_tool("getAsset", assetId=asset_id)
    if category == "baseline":
        return "baseline", call_tool("getBaseline", assetId=asset_id)
    if category == "analyses":
        return "analyses", call_tool("listAnalyses", assetId=asset_id)
    if category == "rms":
        return "rms", call_tool("getRmsSeries", assetId=asset_id)
    if category == "spectrum":
        return "spectrum", call_tool("getSpectrum", assetId=asset_id)
    if category == "data_quality":
        return "data_quality", call_tool("getDataQuality", assetId=asset_id)
    if category == "model":
        # Traz processing_state (o modelo está atrasado?) e
        # coverage[].can_learn_baseline (este tipo de máquina aprende baseline?).
        return "model", call_tool("getModel", modelId=DEFAULT_MODEL_ID)
    if category == "knowledge":
        return "knowledge", call_tool("searchKnowledge", q=_knowledge_query(state.get("message", "")))
    if category == "analysis_detail":
        analysis_id = _first_analysis_id(raw)
        if not analysis_id:
            return "analysis_detail", {
                "mode": "unavailable",
                "notes": "nenhum analysis_id conhecido para detalhar",
                "data": None,
            }
        return "analysis_detail", call_tool("getAnalysis", analysisId=analysis_id)
    raise ValueError(f"Categoria de tool desconhecida: {category}")


# ---------------------------------------------------------------------------
# Classificação de evidência
# ---------------------------------------------------------------------------

# `conflict` devolve o payload íntegro + flag; `partial` só omite campos
# secundários (ver _PARTIAL_DROP na API). Ambos continuam decidíveis.
USABLE_MODES = {"complete", "conflict", "partial"}
# Estes sim esvaziam o payload: `inconclusive` reduz a {inconclusive, asset_id}
# e `unavailable` devolve {}.
EMPTY_MODES = {"inconclusive", "unavailable"}

# Que evidência buscar quando uma categoria vem vazia ou degradada.
COMPENSATION: dict[str, list[str]] = {
    "baseline": ["model", "asset_info", "knowledge"],
    "analyses": ["analysis_detail", "model", "knowledge"],
    "rms": ["analyses", "data_quality", "knowledge"],
    "spectrum": ["asset_info", "analysis_detail"],
    "data_quality": ["asset_info", "knowledge"],
    "asset_info": ["knowledge"],
}


def _mode_of(envelope) -> str:
    if not isinstance(envelope, dict):
        return "invalid"
    return envelope.get("mode", "unknown")


def _extract_analyses_list(envelope: dict) -> list:
    if not isinstance(envelope, dict):
        return []
    data = envelope.get("data") or {}
    if isinstance(data, dict):
        return data.get("analyses", [])
    return []


def _next_compensation(raw: dict, tools_called: list[str]) -> str | None:
    """Próxima tool compensatória útil, ou None se não houver.

    Percorre as categorias com problema, na ordem de criticidade, e devolve a
    primeira compensação ainda não tentada.
    """
    tried = set(tools_called or [])
    problematic = [
        cat for cat in ("baseline", "analyses", "spectrum", "rms", "data_quality", "asset_info")
        if cat in raw and _mode_of(raw[cat]) != "complete"
    ]
    for cat in problematic:
        for candidate in COMPENSATION.get(cat, []):
            if candidate not in tried:
                return candidate
    return None


# ---------------------------------------------------------------------------
# Nós
# ---------------------------------------------------------------------------


def investigate(state: AgentState) -> dict:
    """Coleta dados da API via tools HTTP.

    - Na 1ª passada busca as tools do núcleo (`CORE_TOOLS`).
    - Voltando do quality_check com `next_tool`, busca APENAS essa tool.

    Retorna só as tools chamadas NESTA passada — `tools_called` é
    Annotated[list, operator.add] e faz o append sozinho.
    """
    raw = dict(state.get("raw") or {})
    modes: dict[str, str] = {}

    targets = [state["next_tool"]] if state.get("next_tool") else list(CORE_TOOLS)

    for tool in targets:
        try:
            key, envelope = _handle_request(tool, state, raw)
            raw[key] = envelope
            modes[key] = _mode_of(envelope)
        except Exception as e:
            raw[tool] = {"mode": "unavailable", "notes": f"erro ao buscar {tool}: {e}", "data": None}
            modes[tool] = "unavailable"

    record_node(
        "investigate.envelopes",
        **{"investigate.tools": targets},
        **{f"envelope.mode.{k}": v for k, v in modes.items()},
    )

    return {
        "raw": raw,
        "tools_called": targets,
        "next_tool": None,
        "trace": [{"node": "investigate", "tools_called": targets, "modes": modes}],
    }


def quality_check(state: AgentState) -> dict:
    """Classifica a força da evidência coletada. Anota, não bloqueia.

    É o dono único da política sobre respostas não-completas. Para cada
    categoria registra honestamente o gap em `data_gaps` (que nunca some) e
    decide se vale buscar evidência compensatória.

    Veredicto:
      ok          — tudo completo
      partial     — há degradado, mas tudo continua utilizável
      incomplete  — alguma categoria veio vazia, com compensação disponível
      unavailable — NADA utilizável (único caso de bloqueio real)
    """
    raw = state.get("raw") or {}
    gaps: dict[str, list[str]] = {}
    usable: list[str] = []
    empty: list[str] = []
    notes: list[str] = []

    for cat, envelope in raw.items():
        mode = _mode_of(envelope)

        if mode == "complete":
            usable.append(cat)
            continue

        if mode in USABLE_MODES:
            usable.append(cat)
            detail = (envelope.get("notes") or "").strip()
            if mode == "conflict":
                gaps[cat] = [f"mode=conflict: fontes divergem, dados presentes — {detail}"]
                notes.append(f"{cat} com conflito entre fontes (dados presentes)")
            else:
                gaps[cat] = [f"mode=partial: campos secundários omitidos — {detail}"]
                notes.append(f"{cat} parcial")
        else:
            empty.append(cat)
            detail = (envelope.get("notes") or "").strip() if isinstance(envelope, dict) else ""
            gaps[cat] = [f"mode={mode}: sem dado — {detail}"]
            notes.append(f"{cat} sem dado ({mode})")

    # Análises que voltaram completas mas vazias não são "dado", são ausência.
    analyses_env = raw.get("analyses")
    if isinstance(analyses_env, dict) and not _extract_analyses_list(analyses_env):
        gaps.setdefault("analyses", []).append("nenhuma análise encontrada para o ativo")
        if "analyses" in usable:
            usable.remove("analyses")
            empty.append("analyses")
        notes.append("nenhuma análise registrada")

    if not usable:
        verdict = "unavailable"
    elif empty:
        verdict = "incomplete"
    elif gaps:
        verdict = "partial"
    else:
        verdict = "ok"

    # Só busca compensação quando há de fato algo a compensar.
    next_tool = None
    if verdict in ("incomplete", "unavailable", "partial"):
        next_tool = _next_compensation(raw, state.get("tools_called") or [])

    record_node("quality_check.evidence", **{
        "quality.verdict": verdict,
        "evidence.usable": usable,
        "evidence.empty": empty,
        "quality.next_tool": next_tool,
    })

    return {
        "quality_verdict": verdict,
        "quality_notes": "; ".join(notes) if notes else None,
        "data_gaps": gaps,
        "next_tool": next_tool,
        "trace": [{
            "node": "quality_check", "verdict": verdict, "gaps": gaps,
            "usable": usable, "empty": empty, "next_tool": next_tool,
        }],
    }


# ---------------------------------------------------------------------------
# Decisão
# ---------------------------------------------------------------------------


class AgentDecision(BaseModel):
    """Saída estruturada do nó decide.

    Substitui o parsing por substring da versão anterior (`"solicitar" in text`
    → agir), que confundia prosa comum com intenção de ação.
    """

    decision: Literal["orient", "act", "escalate"] = Field(
        description="orient=explicar sem alterar nada; act=executar ação na plataforma; escalate=encaminhar a humano"
    )
    action_type: Literal["reprocess", "specialist", "retrain", "update_config"] | None = Field(
        default=None, description="Obrigatório quando decision=act; caso contrário null"
    )
    action_target: str | None = Field(
        default=None,
        description="id do alvo: analysis_id (reprocess/specialist), model_id (retrain) ou asset_id (update_config)",
    )
    # Estes dois campos são um andaime de raciocínio: obrigam o modelo a
    # enumerar o que de fato observou e o que faltou ANTES de redigir a
    # resposta. Sem eles o juiz apontava respostas fluentes mas mal
    # fundamentadas — e, pior, afirmando coisas que a evidência não sustentava.
    evidencias: list[str] = Field(
        default_factory=list,
        description=(
            "Evidências CONCRETAS observadas que sustentam a decisão, uma por item. "
            "Cite o dado e seu valor (ex.: 'baseline.state = invalidated', "
            "'model.processing_state = delayed'). NUNCA liste algo que não apareça "
            "nas evidências fornecidas."
        ),
    )
    limitacoes: list[str] = Field(
        default_factory=list,
        description=(
            "O que faltou e COMO isso limita a conclusão, uma por item "
            "(ex.: 'rms indisponível: não dá para confirmar a tendência de vibração'). "
            "Lista vazia só se realmente não houve lacuna alguma."
        ),
    )
    justification: str = Field(
        description="Justificativa técnica interna, EM PORTUGUÊS, citando as evidências que sustentam a decisão"
    )
    customer_message: str = Field(
        description=(
            "Resposta ao cliente EM PORTUGUÊS. Estrutura obrigatória, em prosa corrida "
            "(sem títulos nem listas): (1) responda DIRETAMENTE o que ele perguntou; "
            "(2) explique com base nas `evidencias`, traduzindo o jargão; "
            "(3) reconheça as `limitacoes` explicitamente, se houver; "
            "(4) diga qual é o próximo passo. Nunca afirme como certo algo que as "
            "evidências não mostram."
        )
    )


SYSTEM_PROMPT = """Você é um engenheiro de suporte da TRACTIAN. Recebe tickets de clientes sobre
dados de sensores em ativos industriais e precisa ORIENTAR, AGIR ou ESCALAR.

## Domínio (use estes conceitos com precisão)
- BASELINE: o "normal" aprendido DAQUELE ativo específico, a partir do histórico sadio dele.
  Estados: `learning` (histórico insuficiente) → `established` (confiável) → `invalidated`
  (mudança física invalidou o histórico; precisa reaprender).
  O limiar de alarme de RMS DERIVA do baseline do ativo — não é norma ISO nem número fixo.
- DETECTION MODE: `baseline` = desvio do aprendido (desbalanceamento, desalinhamento,
  rolamento, elétrica) e EXIGE baseline `established`. `symptom` = o sintoma já indica a
  falha sozinho (ex.: lubrificação) e INDEPENDE do estado do baseline.
- ESPECTRO (FFT): 1× indica desbalanceamento, 2× desalinhamento, BPFO/BPFI/BSF/FTF
  rolamentos, 2× a frequência de linha indica falha elétrica. Interpretar exige as
  frequências características do ativo.
- MODELO: `processing_state` diz se o processamento está em dia ou atrasado;
  `coverage[].can_learn_baseline` diz se aquele tipo de máquina sequer aprende baseline.

## Qualidade da evidência
Os dados chegam num envelope com um modo. Interprete assim:
- `complete`: dado íntegro.
- `conflict`: dado ÍNTEGRO, com fontes divergindo. NÃO é ausência de dado — é a evidência
  mais rica que existe. Analise a divergência e explique-a; não escale só por haver conflito.
- `partial`: só campos secundários foram omitidos. O essencial está presente.
- `inconclusive` / `unavailable`: aí sim não veio dado.

## Regras
1. Fundamente a resposta APENAS nas evidências fornecidas abaixo.
2. Nunca invente dado. Se houver lacuna, reconheça-a explicitamente na resposta ao cliente.
3. Ao AGIR, escolha o alvo entre os ids listados nas evidências — nunca invente um id.

## Como escolher a decisão
Comece por O QUE O CLIENTE PEDIU; depois confirme se a evidência sustenta.

1) O cliente PEDIU uma ação na plataforma — ou relatou que já corrigiu o problema
   físico e o diagnóstico continua desatualizado?
   Exemplos: "reprocessa a análise", "treina o modelo de novo", "quero que um
   especialista veja", "troquei o rolamento mas o insight continua acusando falha".
   → ACT, se a evidência sustentar e houver um id de alvo válido:
     - intervenção física já feita, análise ficou obsoleta ....... reprocess
     - cliente quer parecer humano especializado sobre o caso .... specialist
     - o modelo erra de forma sistemática naquele tipo de ativo .. retrain
     - configuração cadastral do ativo está incorreta ............ update_config
   Se a evidência NÃO sustentar o pedido, ORIENTE explicando por quê — nunca aja no escuro.

2) O cliente PEDIU intervenção humana ou de campo, ou houve falha física já
   consumada (quebra, parada) que atendimento remoto não resolve?
   Exemplos: "isso ultrapassa o suporte remoto", "preciso de alguém em campo",
   "o equipamento quebrou e ninguém me avisou".
   → ESCALATE, dizendo o motivo técnico e exatamente o que faltou de evidência.

3) O cliente fez uma PERGUNTA — quer entender algo?
   Exemplos: "por que...", "isso é falso positivo?", "é elétrico ou mecânico?",
   "a partir de que valor vocês consideram alarme?".
   → ORIENT. Explique usando a evidência. Uma pergunta pede explicação, não ação.
   NÃO dispare reprocess/retrain só porque você notou algo estranho de passagem:
   agir sem o cliente ter pedido é erro.

Na dúvida entre ORIENT e ACT, prefira ORIENT.
Na dúvida entre ORIENT e ESCALATE, só escale se a evidência realmente não permitir
uma explicação honesta, ou se o caso exigir presença física.

## Padrão de qualidade da resposta
A resposta é avaliada em quatro eixos. O que separa uma resposta boa de uma medíocre:

- HONESTIDADE: dizer explicitamente o que faltou e como isso limita a conclusão.
  Silenciar sobre a lacuna já é falha; afirmar como fato algo que os dados não
  mostram é a falha grave.
- FUNDAMENTAÇÃO: citar a evidência ESPECÍFICA que leva àquela conclusão — o estado
  do baseline, o detection_mode, o pico do espectro, o processing_state do modelo.
  "Analisamos os dados e está tudo bem" não fundamenta nada.
- CLAREZA: linguagem de conversa, sem jargão não explicado. O cliente precisa
  terminar de ler sabendo qual é o próximo passo.
- SEGURANÇA: o nível de intervenção tem que corresponder ao que a evidência
  sustenta — nem agir no escuro, nem escalar tendo a resposta em mãos."""


def _resumir_rms(data: dict) -> dict:
    """Condensa a série de RMS no que decide, em vez de 30 amostras cruas.

    Duas razões. A primeira é custo: as amostras eram o maior bloco do prompt.
    A segunda importa mais — pedir ao LLM que compare 30 números com um limiar é
    pedir aritmética, justamente onde ele erra. O juiz flagrou o agente afirmando
    "valores de vibração acima dos limites" num ticket em que isso não era
    verdade. Aqui a comparação é feita em Python e entregue pronta.
    """
    amostras = [a for a in (data.get("samples") or []) if isinstance(a, dict)]
    valores = [a["value"] for a in amostras if isinstance(a.get("value"), (int, float))]
    limiar = data.get("alarm_threshold")

    resumo = {
        "unit": data.get("unit"),
        "baseline_reference": data.get("baseline_reference"),
        "baseline_state": data.get("baseline_state"),
        "alarm_threshold": limiar,
        "n_amostras": len(valores),
    }
    if not valores:
        resumo["observacao"] = "sem amostras na série"
        return resumo

    primeiro, ultimo = valores[0], valores[-1]
    resumo.update({
        "primeiro": round(primeiro, 3),
        "ultimo": round(ultimo, 3),
        "minimo": round(min(valores), 3),
        "maximo": round(max(valores), 3),
        "variacao_pct": round((ultimo - primeiro) / primeiro * 100, 1) if primeiro else None,
        "tendencia": "subindo" if ultimo > primeiro * 1.05
                     else "caindo" if ultimo < primeiro * 0.95
                     else "estavel",
    })
    if isinstance(limiar, (int, float)):
        acima = [v for v in valores if v > limiar]
        resumo["ultrapassou_limiar"] = bool(acima)
        resumo["n_amostras_acima_do_limiar"] = len(acima)
        resumo["ultimo_acima_do_limiar"] = ultimo > limiar
    return resumo


def _sem_nulos(data: dict) -> dict:
    """Remove campos nulos — ruído que o modelo pode confundir com dado ausente."""
    return {k: v for k, v in data.items() if v not in (None, [], {})}


def _resumir_evidencia(categoria: str, data) -> object:
    """Cura o payload de uma categoria para o balanço de evidência.

    Entregar JSON cru convida o modelo a citar campos que não leu direito. Cada
    categoria devolve só o que sustenta uma decisão.
    """
    if not isinstance(data, dict):
        return data
    if categoria == "rms":
        return _resumir_rms(data)
    if categoria == "spectrum":
        # `peaks` já vem compacto e é o sinal: freq, amplitude e a nota (1x, 2x...).
        return _sem_nulos({
            "collected_at": data.get("collected_at"),
            "peaks": data.get("peaks"),
            "bands_missing": data.get("bands_missing"),
        })
    if categoria == "baseline":
        return _sem_nulos({
            k: data.get(k) for k in
            ("state", "detection_mode", "learnable", "invalidation_reason", "features")
        })
    if categoria == "asset_info":
        return _sem_nulos({
            k: data.get(k) for k in
            ("id", "machine_type", "criticality", "rotation_rpm", "sensor_status",
             "bpfo_hz", "bpfi_hz", "bsf_hz", "ftf_hz", "line_frequency_hz", "points")
        })
    if categoria == "model":
        return _sem_nulos({
            k: data.get(k) for k in ("id", "version", "processing_state", "coverage")
        })
    return _sem_nulos(data)


def _evidence_ledger(state: AgentState) -> str:
    """Monta o balanço de evidência que vai ao LLM.

    Mostra explicitamente o que veio íntegro, o que veio degradado (e como) e o
    que não veio — para o modelo decidir ciente das lacunas em vez de receber um
    blob indiferenciado.
    """
    raw = state.get("raw") or {}
    parts = [
        f"TICKET: {state['message']}",
        f"ATIVO: {state['asset_id']}",
        f"FORÇA DA EVIDÊNCIA: {state.get('quality_verdict')} ({state.get('quality_notes') or 'sem ressalvas'})",
        "",
        "--- EVIDÊNCIAS COLETADAS ---",
    ]

    for cat in CORE_TOOLS + COMPENSATORY_TOOLS:
        env = raw.get(cat)
        if not isinstance(env, dict):
            continue
        mode = _mode_of(env)
        if cat == "analyses":
            items = _extract_analyses_list(env)
            if items:
                parts.append(f"[{cat}] mode={mode} — {len(items)} análise(s): {items[:3]}")
            else:
                parts.append(f"[{cat}] mode={mode} — nenhuma análise registrada")
        elif mode in USABLE_MODES:
            parts.append(f"[{cat}] mode={mode} — {_resumir_evidencia(cat, env.get('data'))}")
        else:
            parts.append(f"[{cat}] mode={mode} — SEM DADO ({env.get('notes') or ''})")

    gaps = state.get("data_gaps") or {}
    if gaps:
        parts += ["", "--- LACUNAS (considere na decisão e reconheça ao cliente) ---", str(gaps)]

    ids = _available_ids(state)
    if ids:
        parts += ["", f"--- IDS VÁLIDOS PARA AÇÃO --- {ids}"]

    return "\n".join(parts)


def _available_ids(state: AgentState) -> dict:
    """Ids reais que o LLM pode usar como alvo de ação."""
    raw = state.get("raw") or {}
    analyses = [a.get("id") for a in _extract_analyses_list(raw.get("analyses", {})) if isinstance(a, dict) and a.get("id")]
    model_env = raw.get("model")
    model_id = None
    if isinstance(model_env, dict) and isinstance(model_env.get("data"), dict):
        model_id = model_env["data"].get("id")
    return {
        "analysis_ids": analyses,
        "model_id": model_id or DEFAULT_MODEL_ID,
        "asset_id": state.get("asset_id"),
    }


def _validate_action(decision: AgentDecision, state: AgentState) -> tuple[str | None, str | None]:
    """Valida (ou corrige) o alvo da ação escolhida pelo LLM.

    Structured output impede o modelo de escrever prosa no lugar da decisão, mas
    não o impede de citar um id que não existe. Aqui o alvo é conferido contra os
    ids realmente presentes na evidência.
    """
    if decision.decision != "act" or not decision.action_type:
        return None, None

    ids = _available_ids(state)
    action_type = decision.action_type
    target = (decision.action_target or "").strip() or None

    if action_type == "update_config":
        return action_type, ids["asset_id"]
    if action_type == "retrain":
        return action_type, target if target == ids["model_id"] else ids["model_id"]
    # reprocess / specialist operam sobre uma análise
    valid = ids["analysis_ids"]
    if target in valid:
        return action_type, target
    if valid:
        return action_type, valid[0]
    # Sem análise alvo, a ação não tem onde acontecer.
    return None, None


def decide(state: AgentState) -> dict:
    """Decide entre orientar, agir ou escalar — sempre via LLM.

    A versão anterior curto-circuitava aqui quando o veredicto era `unavailable`
    e devolvia um dossiê fixo, idêntico para todos os tickets e com afirmações
    não verificadas. Agora o LLM sempre recebe o balanço de evidência real.
    """
    context_text = _evidence_ledger(state)

    cached = _cached_decision(context_text)
    if cached is not None:
        cached, modelo_cache = cached
        record_node("decide.outcome", **{"cache.hit": True, "decision": cached.decision,
                                         "llm.model_efetivo": modelo_cache})
        action_type, action_target = _validate_action(cached, state)
        return {
            "decision": cached.decision,
            "decision_justification": cached.justification,
            "response": cached.customer_message,
            "action_type": action_type,
            "action_target": action_target,
            "trace": [{"node": "decide", "decision": cached.decision,
                       "action": action_type, "from_cache": True,
                       "modelo": modelo_cache,
                       "evidencias": cached.evidencias,
                       "limitacoes": cached.limitacoes}],
        }

    # include_raw devolve tambem a resposta bruta, de onde sai o modelo real.
    llm = _get_llm(structured_output=AgentDecision, include_raw=True)
    bruto = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=context_text),
    ])
    result: AgentDecision = bruto["parsed"]
    if result is None:
        raise RuntimeError(f"LLM não produziu decisão válida: {bruto.get('parsing_error')}")
    modelo = modelo_efetivo(bruto.get("raw"))

    _write_decision_cache(context_text, result, modelo)
    action_type, action_target = _validate_action(result, state)

    record_node("decide.outcome", **{
        "cache.hit": False,
        "decision": result.decision,
        "action.type": action_type,
        # O slug pedido pode ser um combo; `llm.model_efetivo` e quem respondeu.
        "llm.model_solicitado": os.getenv("OPENAI_MODEL", ""),
        "llm.model_efetivo": modelo,
        "response.evidencias": result.evidencias,
        "response.limitacoes": result.limitacoes,
    })

    return {
        "decision": result.decision,
        "decision_justification": result.justification,
        "response": result.customer_message,
        "action_type": action_type,
        "action_target": action_target,
        "trace": [{"node": "decide", "decision": result.decision,
                   "action": action_type, "from_cache": False,
                   "modelo": modelo,
                   # No trace, não só no span: é o que permite a interface mostrar
                   # em que o agente se apoiou e o que ele reconheceu que faltou.
                   "evidencias": result.evidencias,
                   "limitacoes": result.limitacoes}],
    }


# --- Cache em disco de decisões (economiza tokens em re-execuções) ---

_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".run" / "llm_cache"


def _cache_enabled() -> bool:
    """Cache ligado por padrão; `AGENT_LLM_CACHE=0` desliga.

    As rodadas que medem custo e latência precisam desligar — com cache não há
    chamada de LLM e portanto não há tokens nem latência para medir.
    """
    return os.getenv("AGENT_LLM_CACHE", "1") != "0"


def _cache_key(context_text: str) -> str:
    """Chave = hash(versão + contexto). Mudar AGENT_VERSION invalida o cache."""
    import hashlib
    from ..version import AGENT_VERSION
    return hashlib.sha1(f"{AGENT_VERSION}:{context_text}".encode("utf-8")).hexdigest()


def _cached_decision(context_text: str) -> tuple[AgentDecision, str | None] | None:
    """Devolve (decisão, modelo que a gerou), ou None se não houver cache."""
    if not _cache_enabled():
        return None
    try:
        path = _CACHE_DIR / f"{_cache_key(context_text)}.json"
        if not path.exists():
            return None
        import json
        dados = json.loads(path.read_text(encoding="utf-8"))
        modelo = dados.pop("_modelo", None)
        return AgentDecision(**dados), modelo
    except Exception:
        return None


def _write_decision_cache(context_text: str, decision: AgentDecision,
                          modelo: str | None = None) -> None:
    if not _cache_enabled():
        return
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        import json
        path = _CACHE_DIR / f"{_cache_key(context_text)}.json"
        # `_modelo` fora do schema: preserva de qual modelo veio a decisão
        # guardada, senão uma rodada com cache reportaria modelo desconhecido.
        payload = {**decision.model_dump(), "_modelo": modelo}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Ações
# ---------------------------------------------------------------------------


def respond(state: AgentState) -> dict:
    """Entrega a orientação ao cliente. Não altera nada na plataforma."""
    record_node("respond.final", **{"final.decision": "orient"})
    return {
        "trace": [{"node": "respond", "action": "orient",
                   "response": (state.get("response") or "")[:120]}],
    }


# Ação do agente → tool MCP que a executa, com o nome do parâmetro do alvo.
# Os nós não montam URL: quem conhece endpoint é o servidor MCP (ADR-0001).
ACTION_TOOLS: dict[str, tuple[str, str]] = {
    "reprocess": ("reprocessAnalysis", "analysisId"),
    "specialist": ("requestSpecialistAnalysis", "analysisId"),
    "retrain": ("requestRetraining", "modelId"),
    "update_config": ("updateAssetConfig", "assetId"),
    "escalate": ("escalateCase", "caseId"),
}


def _build_action_call(action_type: str, target: str) -> tuple[str, dict]:
    """Mapeia action_type + alvo para (nome da tool MCP, argumentos)."""
    tool, param = ACTION_TOOLS.get(action_type, ACTION_TOOLS["escalate"])
    return tool, {param: target}


def act(state: AgentState) -> dict:
    """Pausa para confirmação humana (HITL) e, se aprovado, executa a mutação."""
    decision = state.get("decision") or ""
    justification = state.get("decision_justification") or ""
    action_type = state.get("action_type")
    action_target = state.get("action_target")
    user_id = state.get("user_id") or ""

    # 1. Confirmação humana antes de qualquer mutação de impacto.
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
        record_node("act.execution", **{"action.confirmed": False, "final.decision": "escalate"})
        return {
            "decision": "escalate",
            "decision_justification": (
                f"Ação '{action_type}' em '{action_target}' cancelada pelo humano. "
                f"Justificativa original: {justification[:200]}"
            ),
            "trace": [{"node": "act", "action": "cancelled_by_human",
                       "action_type": action_type, "action_target": action_target}],
        }

    if not action_type or not action_target:
        record_node("act.execution", **{"action.confirmed": True, "action.executed": False})
        return {
            "trace": [{"node": "act", "action": "skipped",
                       "reason": "action_type ou action_target ausente"}],
        }

    # 2. Executa a ação real, via tool MCP.
    tool, args = _build_action_call(action_type, action_target)
    if action_type == "update_config":
        # A única mutação que exige um corpo de mudanças além da justificativa.
        args["changes"] = {}
    try:
        result = call_tool(tool, user_id=user_id, justification=justification, **args)
        # A API pode recusar legitimamente (ex.: 403 quando o usuário não tem a
        # permissão exigida). Isso volta como envelope, não como exceção.
        status = result.get("http_status")
        ok = status is None
        action_id = result.get("action_id") if ok else None
        message = result.get("message", "") if ok else str(result.get("notes", ""))
    except Exception as e:
        action_id, message, ok = None, f"falha na tool MCP: {e}", False

    record_node("act.execution", **{
        "action.confirmed": True, "action.executed": ok,
        "action.type": action_type, "action.target": action_target,
        "final.decision": "act",
    })

    return {
        "trace": [{"node": "act", "action": decision, "action_type": action_type,
                   "action_target": action_target, "api_result": message,
                   "action_id": action_id, "confirmed_by": "human"}],
    }


def escalate(state: AgentState) -> dict:
    """Encaminha para humano — e registra o escalonamento na plataforma.

    Antes este nó só escrevia no trace: `POST /cases/{id}/escalate` nunca era
    chamado, embora o gabarito o espere. Escalar é a ação segura, por isso não
    passa por HITL (o `interrupt()` fica para as mutações de impacto).
    """
    case_id = state.get("case_id") or ""
    justification = state.get("decision_justification") or "Escalonamento automático do agente."

    action_id, message, ok = None, "", False
    if case_id:
        try:
            result = call_tool(
                "escalateCase",
                caseId=case_id,
                user_id=state.get("user_id") or "",
                justification=justification,
            )
            status = result.get("http_status")
            ok = status is None
            action_id = result.get("action_id") if ok else None
            message = result.get("message", "") if ok else str(result.get("notes", ""))
        except Exception as e:
            message = f"falha na tool MCP: {e}"

    record_node("escalate.registro", **{"final.decision": "escalate", "escalate.registered": ok})

    return {
        "trace": [{"node": "escalate", "reason": justification[:120],
                   "api_result": message, "action_id": action_id, "registered": ok,
                   # Um escalonamento recusado por permissão continua sendo a
                   # decisão certa do agente: o que falta é um humano com o
                   # perfil adequado assumir o caso.
                   "needs_authorized_user": (not ok) and "403" in str(message)}],
    }
