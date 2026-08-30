"""
Tractian Industrial Agent · Diagnostic Console & Ticket Explorer
================================================================
Interface Streamlit para exploração interativa, diagnóstico e avaliação
do agente industrial de suporte da TRACTIAN.

Como rodar:
    api\\.venv\\Scripts\\python.exe -m streamlit run app.py
    ou via Makefile:
    make up-agent
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
import httpx

# ── Bootstrap: adiciona o projeto ao PYTHONPATH ──────────────────────────────
ROOT = Path(__file__).resolve().parent
API_ROOT = ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── Carrega variáveis de ambiente ────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(ROOT / "agent" / ".env")

# ── Imports do projeto ───────────────────────────────────────────────────────
from agent.graph.agent import agent_graph
from agent.graph.state import AgentState
from agent.logging.postgres import log_execution, count_by_version, compare_versions, _get_connection
from agent.version import AGENT_VERSION
from eval.runner import build_initial_state, load_expected_paths, run_single
from eval.assertions.trajectory import assert_trajectory
from langgraph.types import Command

# ── Constantes & Configuração ────────────────────────────────────────────────
CASES_PATH = ROOT / "agent-input" / "cases.json"
RESULTS_TRAIN_PATH = ROOT / "eval" / "results-train.json"
RESULTS_TEST_PATH = ROOT / "eval" / "results-test.json"

MODALITY_COLORS = {
    "CTX": "#3b82f6",   # blue
    "INV": "#f59e0b",   # amber
    "EXE": "#ef4444",   # red
    "UNK": "#6b7280",
}

QUALITY_COLORS = {
    "ok": "#22c55e",
    "partial": "#f59e0b",
    "incomplete": "#f97316",
    "unavailable": "#ef4444",
    None: "#6b7280",
}

DECISION_COLORS = {
    "orient": "#22c55e",
    "act": "#f59e0b",
    "escalate": "#ef4444",
    None: "#6b7280",
}

DECISION_ICONS = {
    "orient": "🟢",
    "act": "🟡",
    "escalate": "🔴",
    None: "⚪",
}

QUALITY_ICONS = {
    "ok": "✅",
    "partial": "⚠️",
    "incomplete": "🔶",
    "unavailable": "❌",
    None: "⚪",
}

# ── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Tractian Agent · Diagnostic Console",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS (Dark Industrial Theme) ───────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    :root {
        --bg-primary: #0f1117;
        --bg-card: #1a1d29;
        --border: #2d3142;
        --text-primary: #e2e8f0;
        --text-secondary: #8892a0;
        --accent: #ff6b35;
        --accent-hover: #ff8c5a;
        --green: #22c55e;
        --amber: #f59e0b;
        --red: #ef4444;
    }

    .stApp {
        background: var(--bg-primary);
        font-family: 'Inter', system-ui, sans-serif;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #141720;
        border-right: 1px solid var(--border);
    }
    [data-testid="stSidebar"] .stMarkdown {
        color: var(--text-primary);
    }

    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, var(--accent), var(--accent-hover)) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 10px 20px !important;
        font-weight: 600 !important;
        font-size: 13px !important;
        transition: all 0.2s ease;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(255, 107, 53, 0.35);
    }
    .stButton > button[kind="secondary"] {
        background: #1e2337 !important;
        color: var(--text-secondary) !important;
        border: 1px solid var(--border) !important;
    }
    .stButton > button[kind="secondary"]:hover {
        background: #252a3d !important;
        color: #fff !important;
        box-shadow: none;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        background: transparent;
        border-bottom: 1px solid var(--border);
        gap: 6px;
    }
    .stTabs [data-baseweb="tab"] {
        color: var(--text-secondary);
        font-weight: 600;
        padding: 10px 20px;
        border-radius: 8px 8px 0 0;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: var(--accent);
        border-bottom: 2px solid var(--accent);
        background: rgba(255, 107, 53, 0.08);
    }

    /* Cards */
    .tractian-card {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 18px;
        margin-bottom: 14px;
    }

    /* Metric cards */
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
        gap: 12px;
        margin-bottom: 16px;
    }
    .metric-card {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 14px;
        text-align: center;
    }
    .metric-label {
        font-size: 11px;
        color: var(--text-secondary);
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 6px;
    }
    .metric-value {
        font-size: 18px;
        font-weight: 700;
    }

    /* Timeline */
    .timeline-container {
        position: relative;
        padding-left: 28px;
        margin: 16px 0;
    }
    .timeline-line {
        position: absolute;
        left: 7px;
        top: 4px;
        bottom: 4px;
        width: 2px;
        background: var(--border);
    }
    .timeline-item {
        position: relative;
        margin-bottom: 18px;
    }
    .timeline-dot {
        position: absolute;
        left: -24px;
        top: 2px;
        width: 14px;
        height: 14px;
        border-radius: 50%;
        border: 3px solid var(--bg-primary);
    }
    .timeline-title {
        font-weight: 700;
        font-size: 14px;
    }
    .timeline-desc {
        font-size: 12px;
        color: var(--text-secondary);
        margin-top: 3px;
        line-height: 1.5;
    }

    /* HITL Banner */
    .hitl-banner {
        background: linear-gradient(135deg, #3d1f1f, #281414);
        border: 1px solid #991b1b;
        border-radius: 10px;
        padding: 18px;
        margin: 16px 0;
    }

    /* Tag pills */
    .tag {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 16px;
        font-size: 11px;
        font-weight: 600;
        margin-right: 6px;
    }
    .tag-ctx { background: #1e3a5f; color: #60a5fa; }
    .tag-inv { background: #3d2e1a; color: #f59e0b; }
    .tag-exe { background: #3d1f1f; color: #ef4444; }
    .tag-asset { background: #1e2337; color: #93c5fd; }
    .tag-user { background: #1e2337; color: #c084fc; }

    /* Code & JSON */
    pre {
        background: #0b0d13 !important;
        border: 1px solid var(--border) !important;
        border-radius: 8px !important;
    }

    h1, h2, h3, h4 {
        color: var(--text-primary) !important;
    }
</style>
""", unsafe_allow_html=True)


# ── Helpers de Sistema & Health Check ────────────────────────────────────────
@st.cache_data(ttl=5)
def check_api_health() -> Dict[str, Any]:
    """Verifica se a API industrial (:8000) está ativa."""
    api_url = os.getenv("TRACTIAN_API_URL", "http://localhost:8000")
    try:
        resp = httpx.get(f"{api_url}/companies/comp_mineracao_andes", timeout=1.2)
        if resp.status_code == 200:
            return {"online": True, "url": api_url, "msg": "API :8000 Online"}
        return {"online": False, "url": api_url, "msg": f"API :8000 (Status {resp.status_code})"}
    except Exception:
        return {"online": False, "url": api_url, "msg": "API :8000 Offline"}


@st.cache_data(ttl=5)
def check_postgres_health() -> Dict[str, Any]:
    """Verifica conectividade com PostgreSQL."""
    conn = _get_connection()
    if conn:
        conn.close()
        return {"online": True, "msg": "Postgres :5432 Conectado"}
    return {"online": False, "msg": "Postgres :5432 Offline"}


@st.cache_data(ttl=5)
def check_phoenix_health() -> Dict[str, Any]:
    """Verifica se o Phoenix Tracing (:6006) está acessível."""
    try:
        resp = httpx.get("http://localhost:6006", timeout=1.0)
        if resp.status_code in (200, 302, 307):
            return {"online": True, "msg": "Phoenix :6006 Ativo"}
        return {"online": False, "msg": "Phoenix :6006 Inativo"}
    except Exception:
        return {"online": False, "msg": "Phoenix :6006 Inativo"}


def check_llm_config() -> Dict[str, Any]:
    """Verifica credenciais e modelo do LLM."""
    key = os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("OPENAI_MODEL", "llama-3.3-70b-versatile")
    base_url = os.getenv("OPENAI_BASE_URL", "")
    has_key = bool(key and key != "coloque_sua_chave_gratuita_aqui")
    provider = "Groq" if "groq" in base_url.lower() else ("OpenRouter" if "openrouter" in base_url.lower() else "OpenAI")
    return {"configured": has_key, "model": model, "provider": provider}


# ── Carregamento de Dados ────────────────────────────────────────────────────
def load_cases() -> List[Dict[str, Any]]:
    """Carrega os casos do agent-input/cases.json."""
    if not CASES_PATH.exists():
        st.error(f"Arquivo não encontrado: {CASES_PATH}")
        return []
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def get_modality(ticket_id: str) -> str:
    """Extrai a modalidade do ticket_id (CTX, INV, EXE)."""
    if "-CTX-" in ticket_id:
        return "CTX"
    if "-INV-" in ticket_id or "-INV" in ticket_id:
        return "INV"
    if "-EXE-" in ticket_id or "-EXE" in ticket_id:
        return "EXE"
    return "UNK"


def format_case_option(case: Dict[str, Any]) -> str:
    """Formata a opção do dropdown."""
    mod = get_modality(case["ticket_id"])
    emoji = {"CTX": "📘", "INV": "📙", "EXE": "📕"}.get(mod, "📄")
    preview = case["message"][:48] + "..." if len(case["message"]) > 48 else case["message"]
    return f"{emoji} {case['ticket_id']} — {preview}"


# ── Execução do Grafo com HITL Interativo ───────────────────────────────────
def execute_agent_stepwise(case: Dict[str, Any]) -> Tuple[Dict[str, Any], float, bool]:
    """
    Executa o grafo do agente mantendo checkpoint no LangGraph MemorySaver.
    Retorna (result_or_interrupted_state, elapsed_time, is_interrupted).
    """
    start = time.time()
    state = build_initial_state(case)
    thread_id = case["ticket_id"]
    config = {"configurable": {"thread_id": thread_id}}

    result = agent_graph.invoke(state, config=config)
    elapsed = time.time() - start

    # Verifica se o grafo pausou em um interrupt() do HITL
    if "__interrupt__" in result:
        return result, elapsed, True

    # Gravação no Postgres se a execução terminou
    try:
        log_execution(result, agent_version=AGENT_VERSION)
    except Exception:
        pass

    return result, elapsed, False


def resume_agent_action(ticket_id: str, confirm: bool) -> Dict[str, Any]:
    """Retoma a execução do grafo após confirmação ou cancelamento humano."""
    config = {"configurable": {"thread_id": ticket_id}}
    resumed = agent_graph.invoke(Command(resume=confirm), config=config)
    try:
        log_execution(resumed, agent_version=AGENT_VERSION)
    except Exception:
        pass
    return resumed


# ── Componentes de UI: Header ────────────────────────────────────────────────
def render_header():
    """Renderiza o cabeçalho com badges dinâmicas de status do sistema."""
    col1, col2 = st.columns([1.2, 2.8])
    with col1:
        st.markdown("""
        <div style="display:flex; align-items:center; gap:12px;">
            <div style="width:42px; height:42px; background:linear-gradient(135deg,#ff6b35,#ff8c5a); 
                        border-radius:10px; display:flex; align-items:center; justify-content:center; 
                        font-size:22px; box-shadow:0 4px 12px rgba(255,107,53,0.3);">
                ⚡
            </div>
            <div>
                <div style="font-size:20px; font-weight:700; color:#fff; line-height:1.2;">TRACTIAN AGENT</div>
                <div style="font-size:11px; color:#8892a0; letter-spacing:1.2px;">DIAGNOSTIC & EVALUATION CONSOLE</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        api_h = check_api_health()
        pg_h = check_postgres_health()
        px_h = check_phoenix_health()
        llm_c = check_llm_config()

        api_badge = f'<span style="background:#1a2332; color:#4ade80; padding:4px 10px; border-radius:16px; font-size:11px; border:1px solid #1e3a2f;">● {api_h["msg"]}</span>' if api_h["online"] else f'<span style="background:#2a1a1a; color:#f87171; padding:4px 10px; border-radius:16px; font-size:11px; border:1px solid #4a1e1e;">● {api_h["msg"]}</span>'
        pg_badge = f'<span style="background:#1a2332; color:#60a5fa; padding:4px 10px; border-radius:16px; font-size:11px; border:1px solid #1e293b;">● {pg_h["msg"]}</span>' if pg_h["online"] else f'<span style="background:#1e1e24; color:#6b7280; padding:4px 10px; border-radius:16px; font-size:11px; border:1px solid #2d3142;">○ {pg_h["msg"]}</span>'
        px_badge = f'<span style="background:#1a2332; color:#c084fc; padding:4px 10px; border-radius:16px; font-size:11px; border:1px solid #3b1e4a;">● {px_h["msg"]}</span>' if px_h["online"] else f'<span style="background:#1e1e24; color:#6b7280; padding:4px 10px; border-radius:16px; font-size:11px; border:1px solid #2d3142;">○ {px_h["msg"]}</span>'
        llm_badge = f'<span style="background:#1a2332; color:#f59e0b; padding:4px 10px; border-radius:16px; font-size:11px; border:1px solid #3d2e1a;">⚡ LLM: {llm_c["provider"]} ({AGENT_VERSION})</span>'

        st.markdown(f"""
        <div style="display:flex; gap:6px; justify-content:flex-end; align-items:center; flex-wrap:wrap; margin-top:6px;">
            {api_badge}
            {pg_badge}
            {px_badge}
            {llm_badge}
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<hr style='border-color:#2d3142; margin:14px 0 18px 0;'>", unsafe_allow_html=True)


# ── Componentes de UI: Sidebar ───────────────────────────────────────────────
def render_sidebar(cases: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], str]:
    """Renderiza sidebar com filtros reativos e controles."""
    with st.sidebar:
        st.markdown("""
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:16px;">
            <div style="width:32px; height:32px; background:linear-gradient(135deg,#ff6b35,#ff8c5a); 
                        border-radius:8px; display:flex; align-items:center; justify-content:center; font-size:16px;">⚡</div>
            <div style="font-weight:700; color:#fff; font-size:15px;">Console de Operações</div>
        </div>
        """, unsafe_allow_html=True)

        # 1. Filtro de Modalidade (colocado ANTES do dropdown para reatividade correta)
        st.markdown("<div style='font-size:11px; color:#8892a0; text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;'>1. Filtrar Modalidade</div>", unsafe_allow_html=True)
        filter_mod = st.segmented_control(
            "Modalidade",
            options=["Todos", "CTX", "INV", "EXE"],
            default="Todos",
            key="sidebar_filter_modality",
            label_visibility="collapsed",
        )

        # Filtra os casos disponíveis
        filtered_cases = cases
        if filter_mod and filter_mod != "Todos":
            filtered_cases = [c for c in cases if get_modality(c["ticket_id"]) == filter_mod]
        if not filtered_cases:
            filtered_cases = cases

        # 2. Seletor de Ticket
        st.markdown("<div style='font-size:11px; color:#8892a0; text-transform:uppercase; letter-spacing:1px; margin:12px 0 4px 0;'>2. Selecionar Ticket</div>", unsafe_allow_html=True)
        case_map = {format_case_option(c): c for c in filtered_cases}
        selected_label = st.selectbox(
            "Ticket",
            options=list(case_map.keys()),
            label_visibility="collapsed",
            key="selected_ticket_label",
        )
        selected_case = case_map[selected_label]

        # 3. Card com Contexto do Caso
        mod = get_modality(selected_case["ticket_id"])
        mod_class = f"tag-{mod.lower()}"
        mod_label = {"CTX": "Contextualizar", "INV": "Investigar", "EXE": "Executar"}.get(mod, "—")

        st.markdown(f"""
        <div style="background:#0d0f16; border:1px solid #2d3142; border-radius:8px; padding:12px; margin:12px 0;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <span class="tag {mod_class}">{mod_label}</span>
                <span style="font-size:11px; color:#8892a0;">ID: {selected_case.get('id', '')}</span>
            </div>
            <div style="font-size:12px; color:#e2e8f0; line-height:1.4; margin-bottom:8px;">
                "{selected_case['message'][:85]}{'...' if len(selected_case['message']) > 85 else ''}"
            </div>
            <div>
                <span class="tag tag-asset">🏢 {selected_case.get('company_id','').replace('comp_','').replace('_',' ').title()}</span>
                <span class="tag tag-asset">⚙️ {selected_case.get('asset_id','')}</span>
                <span class="tag tag-user">👤 {selected_case.get('user_id','')}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 4. Botões de Execução
        st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)

        if st.button("▶ Executar Agente", key="btn_run", use_container_width=True):
            st.session_state.run_triggered = selected_case["ticket_id"]

        if st.button("🔄 Limpar Cache e Re-executar", key="btn_rerun", use_container_width=True):
            st.session_state.rerun_triggered = selected_case["ticket_id"]

        # 5. Estatísticas de Casos
        st.markdown("<hr style='border-color:#2d3142; margin:18px 0;'>", unsafe_allow_html=True)
        total_ctx = sum(1 for c in cases if get_modality(c['ticket_id']) == 'CTX')
        total_inv = sum(1 for c in cases if get_modality(c['ticket_id']) == 'INV')
        total_exe = sum(1 for c in cases if get_modality(c['ticket_id']) == 'EXE')

        st.markdown(f"""
        <div style="font-size:11px; color:#8892a0;">
            <div style="margin-bottom:4px;"><span style="color:#60a5fa;">●</span> <b>{total_ctx}</b> Contextualizar (CTX)</div>
            <div style="margin-bottom:4px;"><span style="color:#f59e0b;">●</span> <b>{total_inv}</b> Investigar (INV)</div>
            <div style="margin-bottom:4px;"><span style="color:#ef4444;">●</span> <b>{total_exe}</b> Executar Ações (EXE)</div>
            <div style="margin-top:8px; padding-top:8px; border-top:1px solid #2d3142;">
                <strong style="color:#e2e8f0;">Total: {len(cases)} chamados disponíveis</strong>
            </div>
        </div>
        """, unsafe_allow_html=True)

        return selected_case, filter_mod


# ── Componentes de UI: Aba Diagnóstico & HITL ────────────────────────────────
def render_ticket_card(case: Dict[str, Any]):
    """Exibe o card principal com o texto do chamado e tags contextuais."""
    mod = get_modality(case["ticket_id"])
    mod_class = f"tag-{mod.lower()}"
    mod_label = {"CTX": "Contextualizar", "INV": "Investigar", "EXE": "Executar"}.get(mod, "—")

    st.markdown(f"""
    <div class="tractian-card">
        <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px;">
            <div>
                <span class="tag {mod_class}">{mod_label.upper()}</span>
                <span style="color:#8892a0; font-size:12px;">
                    {case.get('company_id', '').replace('comp_', '').replace('_', ' ').title()} · 
                    {case.get('user_id', '')} · {case.get('asset_id', '')}
                </span>
            </div>
            <span style="color:#8892a0; font-size:12px; font-family:monospace;">{case.get('ticket_id', '')}</span>
        </div>
        <p style="margin:0; font-size:15px; line-height:1.6; color:#e2e8f0; font-style:italic;">
            "{case['message']}"
        </p>
    </div>
    """, unsafe_allow_html=True)


def render_result_cards(result: Dict[str, Any], elapsed: Optional[float] = None):
    """Renderiza os cards com métricas da decisão e telemetria da IA."""
    verdict = result.get("quality_verdict")
    decision = result.get("decision")
    gaps = result.get("data_gaps") or result.get("gaps") or {}
    tools_called = result.get("tools_called", [])
    raw_keys = list(result.get("raw", {}).keys())

    gap_text = ", ".join(gaps.keys()) if isinstance(gaps, dict) and gaps else "Nenhuma"
    if isinstance(gaps, list):
        gap_text = ", ".join(gaps) if gaps else "Nenhuma"

    cols = st.columns(5)
    metrics = [
        ("Qualidade dos Dados", f"{QUALITY_ICONS.get(verdict, '⚪')} {verdict or '—'}", QUALITY_COLORS.get(verdict, "#6b7280")),
        ("Decisão do Agente", f"{DECISION_ICONS.get(decision, '⚪')} {decision or '—'}", DECISION_COLORS.get(decision, "#6b7280")),
        ("Lacunas Detectadas", gap_text, "#e2e8f0"),
        ("Req. / Tools API", f"{len(raw_keys)} chamadas", "#60a5fa"),
        ("Latência Total", f"~{elapsed:.2f}s" if elapsed else "—", "#22c55e"),
    ]

    for col, (label, value, color) in zip(cols, metrics):
        with col:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{label}</div>
                <div class="metric-value" style="color:{color}; font-size:16px;">{value}</div>
            </div>
            """, unsafe_allow_html=True)


def render_hitl_section(ticket_id: str, result: Dict[str, Any], is_interrupted: bool):
    """Renderiza a seção de Human-in-the-Loop com botões reais de confirmação/rejeição."""
    hitl_confirmed = st.session_state.get(f"hitl_confirmed_{ticket_id}")
    hitl_cancelled = st.session_state.get(f"hitl_cancelled_{ticket_id}")

    # 1. Se acabou de pausar no nó act aguardando confirmação humana
    if is_interrupted:
        interrupt_info = {}
        if "__interrupt__" in result and result["__interrupt__"]:
            interrupt_info = result["__interrupt__"][0].value

        action_type = interrupt_info.get("action_type") or result.get("action_type") or "Ação de Plataforma"
        action_target = interrupt_info.get("action_target") or result.get("action_target") or "Alvo não especificado"
        justification = interrupt_info.get("justification") or result.get("decision_justification") or ""

        st.markdown(f"""
        <div class="hitl-banner">
            <div style="display:flex; align-items:center; gap:12px; margin-bottom:10px;">
                <span style="font-size:26px;">⚠️</span>
                <div>
                    <div style="font-weight:700; color:#fca5a5; font-size:16px;">Ação de Impacto Detectada — Human-in-the-Loop</div>
                    <div style="font-size:12px; color:#f87171;">O agente solicitou autorização para executar mutação na API Tractian.</div>
                </div>
            </div>
            <div style="background:#1a1010; border:1px solid #7f1d1d; border-radius:8px; padding:12px; margin:10px 0;">
                <div style="font-size:13px; color:#fca5a5; margin-bottom:4px;">
                    <b>Tipo de Ação:</b> <code>{action_type}</code> | <b>Alvo:</b> <code>{action_target}</code>
                </div>
                <div style="font-size:13px; color:#fca5a5; line-height:1.5;">
                    <b>Justificativa do Agente:</b> "{justification}"
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        c1, c2, _ = st.columns([1.2, 1.2, 2.6])
        with c1:
            if st.button("✓ Confirmar e Executar na API (POST/PATCH)", key=f"hitl_confirm_{ticket_id}", type="primary"):
                with st.spinner("Executando mutação POST/PATCH na API Tractian..."):
                    resumed = resume_agent_action(ticket_id, confirm=True)
                    st.session_state[f"result_{ticket_id}"] = resumed
                    st.session_state[f"is_interrupted_{ticket_id}"] = False
                    st.session_state[f"hitl_confirmed_{ticket_id}"] = True
                    st.success("✅ Ação POST aprovada e executada com sucesso na API!")
                    st.rerun()

        with c2:
            if st.button("✗ Cancelar (Escalar)", key=f"hitl_cancel_{ticket_id}", type="secondary"):
                with st.spinner("Cancelando ação e escalando para suporte humano..."):
                    resumed = resume_agent_action(ticket_id, confirm=False)
                    st.session_state[f"result_{ticket_id}"] = resumed
                    st.session_state[f"is_interrupted_{ticket_id}"] = False
                    st.session_state[f"hitl_cancelled_{ticket_id}"] = True
                    st.info("🚫 Ação cancelada pelo operador. O caso foi escalado para humano.")
                    st.rerun()

    elif hitl_confirmed:
        st.markdown("""
        <div style="background:#14291e; border:1px solid #166534; border-radius:8px; padding:12px; margin:12px 0;">
            <div style="color:#4ade80; font-weight:600; font-size:13px;">
                ✅ Ação POST executada na API Tractian e confirmada pelo operador humano.
            </div>
        </div>
        """, unsafe_allow_html=True)

    elif hitl_cancelled:
        st.markdown("""
        <div style="background:#2d1a1a; border:1px solid #991b1b; border-radius:8px; padding:12px; margin:12px 0;">
            <div style="color:#f87171; font-weight:600; font-size:13px;">
                🚫 Ação cancelada pelo operador. Grafo redirecionado para escalonamento humano.
            </div>
        </div>
        """, unsafe_allow_html=True)


def render_response(result: Dict[str, Any], case: Dict[str, Any]):
    """Exibe a resposta formatada do agente ou o dossiê de escalonamento para engenharia."""
    decision = result.get("decision")
    response = result.get("response") or result.get("decision_justification") or ""
    if not response:
        return

    if decision == "escalate":
        st.markdown(f"""
        <div class="tractian-card" style="border-left:4px solid #ef4444; background: linear-gradient(180deg, #1f1414, #181922);">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <div style="font-size:12px; color:#f87171; font-weight:700; text-transform:uppercase; letter-spacing:1px;">
                    📋 Dossiê de Escalonamento para Engenharia de Suporte Humano
                </div>
                <span class="tag tag-exe">INTERVENÇÃO HUMANA</span>
            </div>
            <div style="font-size:14px; line-height:1.7; color:#e2e8f0; white-space:pre-wrap;">{response}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="tractian-card" style="border-left:4px solid #ff6b35;">
            <div style="font-size:11px; color:#8892a0; text-transform:uppercase; letter-spacing:1px; margin-bottom:8px;">
                Orientação / Resposta ao Cliente
            </div>
            <div style="font-size:14px; line-height:1.7; color:#e2e8f0; white-space:pre-wrap;">{response}</div>
        </div>
        """, unsafe_allow_html=True)

    # ⚖️ Botão para avaliar a resposta deste ticket com o Juiz LLM sob demanda
    st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)
    with st.expander("⚖️ Avaliar esta Resposta com o Juiz LLM (Critérios Industriais)"):
        judge_key = f"judge_result_{case['ticket_id']}"
        if st.button("Executar Juiz LLM neste Ticket", key=f"btn_judge_single_{case['ticket_id']}"):
            from eval.judge.llm_judge import judge_response
            with st.spinner("Juiz LLM avaliando honestidade, clareza, fundamentação e segurança..."):
                try:
                    judge_eval = judge_response(
                        ticket=case["message"],
                        gaps=result.get("data_gaps") or {},
                        response=response,
                        decision=decision or "orient",
                    )
                    st.session_state[judge_key] = judge_eval
                    st.success("✅ Avaliação do Juiz concluída!")
                except Exception as e:
                    st.error(f"❌ Erro na avaliação do juiz: {e}")

        if judge_key in st.session_state:
            je = st.session_state[judge_key]
            jc1, jc2, jc3, jc4, jc5 = st.columns(5)
            jc1.metric("Honestidade", f"{je.get('honestidade', 0)}/10")
            jc2.metric("Clareza", f"{je.get('clareza', 0)}/10")
            jc3.metric("Fundamentação", f"{je.get('fundamentacao', 0)}/10")
            jc4.metric("Segurança", f"{je.get('seguranca', 0)}/10")
            jc5.metric("Nota Geral", f"{je.get('nota_geral', 0)}/10")
            st.info(f"<b>Parecer do Juiz:</b> {je.get('razao', '—')}", icon="⚖️")


def tab_diagnostico(case: Dict[str, Any], result: Optional[Dict[str, Any]], elapsed: Optional[float], is_interrupted: bool):
    """Aba principal: ticket, métricas de resultado, HITL interativo e resposta."""
    render_ticket_card(case)

    if result:
        render_result_cards(result, elapsed)
        render_hitl_section(case["ticket_id"], result, is_interrupted)
        render_response(result, case)
    else:
        st.info("👈 Selecione um ticket na barra lateral e clique em **▶ Executar Agente** para ver o diagnóstico completo.")


# ── Componentes de UI: Aba Trace & Sinais Técnicos (Pipeline Interativo) ─────
def render_graph_pipeline_explorer(result: Dict[str, Any]):
    """Explorador interativo de nós do LangGraph."""
    trace = result.get("trace", [])
    raw = result.get("raw", {})
    if not trace:
        st.info("Nenhum trace de execução disponível.")
        return

    st.markdown("#### 🧭 Pipeline de Execução do LangGraph (Clique para Inspecionar)")

    # Monta lista de passos para navegação em abas/pills
    node_names = [f"{i+1}. {step.get('node', 'unknown').upper()}" for i, step in enumerate(trace)]
    selected_node_idx = st.segmented_control("Nó Ativo", options=list(range(len(node_names))), format_func=lambda i: node_names[i], default=0)

    if selected_node_idx is None:
        selected_node_idx = 0

    curr_step = trace[selected_node_idx]
    curr_node = curr_step.get("node", "unknown")

    st.markdown(f"""
    <div class="tractian-card" style="border-left:3px solid #60a5fa; margin-top:12px;">
        <div style="font-size:16px; font-weight:700; color:#60a5fa; margin-bottom:8px;">
            Nó: {curr_node.upper()}
        </div>
        <div style="font-size:13px; color:#e2e8f0; line-height:1.6;">
    """, unsafe_allow_html=True)

    if curr_node == "investigate":
        tools = curr_step.get("tools_called", [])
        st.markdown(f"**Função:** Consulta a API industrial Tractian através de ferramentas HTTP/MCP para o ativo.")
        st.markdown(f"**Tools invocadas neste passo ({len(tools)}):** `{'`, `'.join(tools)}`")
        st.markdown("**Envelopes coletados:**")
        st.json({k: {"mode": v.get("mode"), "notes": v.get("notes")} for k, v in raw.items() if k in tools})

    elif curr_node == "quality_check":
        verdict = curr_step.get("verdict", "—")
        gaps = curr_step.get("gaps", {})
        next_t = curr_step.get("next_tool")
        st.markdown(f"**Função:** Avalia a integridade e frescor de todas as respostas da API, detectando falhas probabilísticas.")
        st.markdown(f"**Veredicto Definido:** `{verdict}` | **Próxima Tool Recomendada:** `{next_t or 'Nenhuma (Prosseguir para decisão)'}`")
        st.markdown(f"**Lacunas Honestas Registradas (`data_gaps`):**")
        st.json(gaps if gaps else {"status": "Nenhum gap detectado"})

    elif curr_node == "decide":
        decision = curr_step.get("decision", "—")
        reason = curr_step.get("reason", "análise de contexto")
        from_cache = curr_step.get("from_cache", False)
        st.markdown(f"**Função:** Avalia o contexto completo + lacunas registradas para deliberar entre Orientar, Agir ou Escalar.")
        st.markdown(f"**Decisão do Agente:** `{decision.upper()}` | **Origem:** {'⚡ Cache Local' if from_cache else '🧠 Inferência LLM'}")
        st.markdown(f"**Raciocínio:** `{reason}`")

    elif curr_node == "act":
        action = curr_step.get("action", "act")
        act_type = curr_step.get("action_type", "—")
        act_target = curr_step.get("action_target", "—")
        api_res = curr_step.get("api_result", "—")
        st.markdown(f"**Função:** Executa mutação real (POST/PATCH) na API Tractian após confirmação humana.")
        st.markdown(f"**Ação Solicitada:** `{act_type}` no alvo `{act_target}`")
        st.markdown(f"**Resultado da API:** `{api_res}`")

    elif curr_node in ("respond", "escalate"):
        st.markdown(f"**Função:** Entrega final da orientação ou dossiê de escalonamento para o cliente/humano.")
        st.markdown(f"**Saída Gerada:**")
        st.code(result.get("response", "—"))

    st.markdown("</div></div>", unsafe_allow_html=True)


def render_trace_timeline(result: Dict[str, Any]):
    """Renderiza a timeline vertical clássica de nós do LangGraph."""
    trace = result.get("trace", [])
    if not trace:
        st.info("Nenhum trace disponível.")
        return

    st.markdown("<h4 style='font-size:13px; color:#8892a0; text-transform:uppercase; letter-spacing:1px; margin-bottom:14px;'>Linha do Tempo de Nós Executados</h4>", unsafe_allow_html=True)

    node_colors = {
        "investigate": "#3b82f6",
        "quality_check": "#f59e0b",
        "decide": "#8b5cf6",
        "respond": "#22c55e",
        "act": "#ef4444",
        "escalate": "#dc2626",
    }

    st.markdown('<div class="timeline-container"><div class="timeline-line"></div>', unsafe_allow_html=True)

    for i, step in enumerate(trace, 1):
        node = step.get("node", "unknown")
        color = node_colors.get(node, "#6b7280")

        desc_parts = []
        if "tools_called" in step:
            desc_parts.append(f"Tools consultadas: <code>{', '.join(step['tools_called'])}</code>")
        if "verdict" in step:
            desc_parts.append(f"Veredicto de qualidade: <b>{step['verdict']}</b>")
        if "gaps" in step and step["gaps"]:
            gaps = step["gaps"]
            if isinstance(gaps, dict):
                desc_parts.append(f"Gaps: <i>{', '.join(gaps.keys())}</i>")
        if "decision" in step:
            desc_parts.append(f"Decisão: <b>{step['decision'].upper()}</b>")
        if "action" in step:
            desc_parts.append(f"Ação: {step['action']}")
        if "reason" in step:
            desc_parts.append(f"Motivo: {step['reason']}")
        if "from_cache" in step and step["from_cache"]:
            desc_parts.append("⚡ <i>(Decisão recuperada de cache)</i>")

        desc = " · ".join(desc_parts) or "—"

        st.markdown(f"""
        <div class="timeline-item">
            <div class="timeline-dot" style="background:{color};"></div>
            <div class="timeline-title" style="color:{color};">{i}. Nó: {node.upper()}</div>
            <div class="timeline-desc">{desc}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)


def tab_trace(result: Optional[Dict[str, Any]]):
    """Aba de visualização técnica de traces, sinais industriais e envelopes brutos."""
    if not result:
        st.info("Nenhum resultado disponível. Execute um ticket na barra lateral primeiro.")
        return

    render_graph_pipeline_explorer(result)
    st.markdown("<hr style='border-color:#2d3142; margin:20px 0;'>", unsafe_allow_html=True)
    render_trace_timeline(result)
    raw = result.get("raw", {})
    if raw:
        render_technical_signals(raw)
        st.markdown("<h4 style='font-size:13px; color:#8892a0; text-transform:uppercase; letter-spacing:1px; margin:20px 0 10px 0;'>Envelopes Brutos da API</h4>", unsafe_allow_html=True)
        for cat, env in raw.items():
            mode = env.get("mode", "—") if isinstance(env, dict) else "—"
            with st.expander(f"📦 {cat.upper()} (mode={mode})"):
                st.json(env)


def render_technical_signals(raw: Dict[str, Any]):
    """Renderiza gráficos interativos para sinais de vibração RMS e Espectro FFT."""
    st.markdown("<h4 style='font-size:13px; color:#8892a0; text-transform:uppercase; letter-spacing:1px; margin:20px 0 12px 0;'>Sinais Técnicos & Diagnóstico Visual</h4>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)

    # 1. Gráfico de RMS
    with c1:
        rms_env = raw.get("rms", {})
        rms_data = rms_env.get("data") if isinstance(rms_env, dict) else {}
        if isinstance(rms_data, dict) and "samples" in rms_data and rms_data["samples"]:
            samples = rms_data["samples"]
            df_rms = pd.DataFrame(samples)
            if "ts" in df_rms.columns and "value" in df_rms.columns:
                df_rms["ts"] = pd.to_datetime(df_rms["ts"])
                df_rms = df_rms.sort_values("ts").set_index("ts")
                
                threshold = rms_data.get("alarm_threshold")
                if threshold is not None:
                    df_rms["Limiar de Alarme"] = float(threshold)

                st.markdown(f"<b>📈 Série Temporal RMS ({rms_data.get('unit', 'mm/s')})</b>", unsafe_allow_html=True)
                st.line_chart(df_rms, use_container_width=True)
        else:
            st.markdown("""
            <div class="tractian-card" style="text-align:center; padding:30px; color:#8892a0;">
                Sem série temporal de RMS disponível para este ativo.
            </div>
            """, unsafe_allow_html=True)

    # 2. Gráfico de Espectro FFT
    with c2:
        spec_env = raw.get("spectrum", {})
        spec_data = spec_env.get("data") if isinstance(spec_env, dict) else {}
        peaks_data = []
        if isinstance(spec_data, dict) and "peaks" in spec_data:
            raw_peaks = spec_data["peaks"]
            if isinstance(raw_peaks, str):
                try:
                    peaks_data = json.loads(raw_peaks)
                except Exception:
                    pass
            elif isinstance(raw_peaks, list):
                peaks_data = raw_peaks

        if peaks_data:
            df_peaks = pd.DataFrame(peaks_data)
            if "freq_hz" in df_peaks.columns and "amplitude_mm_s" in df_peaks.columns:
                df_peaks = df_peaks.sort_values("freq_hz")
                st.markdown("<b>📊 Espectro de Frequência FFT (Picos)</b>", unsafe_allow_html=True)
                st.bar_chart(df_peaks.set_index("freq_hz")["amplitude_mm_s"], use_container_width=True)
        else:
            st.markdown("""
            <div class="tractian-card" style="text-align:center; padding:30px; color:#8892a0;">
                Sem picos de espectro FFT disponíveis para este ativo.
            </div>
            """, unsafe_allow_html=True)

    # 3. Cards de Baseline & Qualidade dos Dados
    b1, b2 = st.columns(2)
    with b1:
        base_env = raw.get("baseline", {})
        base_data = base_env.get("data") if isinstance(base_env, dict) else {}
        if isinstance(base_data, dict) and base_data:
            state = base_data.get("state", "desconhecido")
            st.markdown(f"""
            <div class="tractian-card">
                <div style="font-size:11px; color:#8892a0; text-transform:uppercase;">Estado do Baseline</div>
                <div style="font-size:16px; font-weight:700; color:#60a5fa; margin:4px 0;">
                    {state.upper()}
                </div>
                <div style="font-size:12px; color:#8892a0;">
                    Modo: {base_env.get('mode', '—')} · Criado: {base_data.get('created_at', '—')}
                </div>
            </div>
            """, unsafe_allow_html=True)

    with b2:
        dq_env = raw.get("data_quality", {})
        dq_data = dq_env.get("data") if isinstance(dq_env, dict) else {}
        if isinstance(dq_data, dict) and dq_data:
            freshness = dq_data.get("freshness_minutes", "—")
            snr = dq_data.get("snr_db", "—")
            st.markdown(f"""
            <div class="tractian-card">
                <div style="font-size:11px; color:#8892a0; text-transform:uppercase;">Qualidade dos Sinais</div>
                <div style="font-size:14px; font-weight:600; color:#4ade80; margin:4px 0;">
                    Frescor: {freshness} min · SNR: {snr} dB
                </div>
                <div style="font-size:12px; color:#8892a0;">
                    Modo da Tool: {dq_env.get('mode', '—')}
                </div>
            </div>
            """, unsafe_allow_html=True)



# ── Componentes de UI: Aba Métricas & Avaliação ──────────────────────────────
def tab_metricas():
    """Aba de avaliação em batch, scores de trajetória, LLM judge e comparação de versões."""
    st.markdown("""
    <div class="tractian-card">
        <h3 style="margin:0 0 8px 0; font-size:16px;">📈 Avaliação do Agente & Comparador de Versões</h3>
        <p style="color:#8892a0; font-size:13px; margin:0;">
            Acompanhe a acurácia determinística de trajetória, notas do juiz LLM e histórico de versões persistidas no PostgreSQL.
        </p>
    </div>
    """, unsafe_allow_html=True)

    sub_t1, sub_t2 = st.tabs(["📊 Avaliação em Batch", "🗄️ Histórico & Comparação no Postgres"])

    with sub_t1:
        col_ctrl1, col_ctrl2, col_ctrl3 = st.columns([1.5, 1.5, 2])
        with col_ctrl1:
            split_choice = st.selectbox("Conjunto de Avaliação", options=["train", "test", "all"], index=0)
        with col_ctrl2:
            use_judge = st.checkbox("Executar Juiz LLM", value=False, help="Avalia qualidade e segurança da resposta com LLM.")
        with col_ctrl3:
            st.markdown("<div style='margin-top:24px;'></div>", unsafe_allow_html=True)
            if st.button("🚀 Executar Avaliação Batch", key="btn_run_eval_tab", use_container_width=True):
                from eval.runner import run_all
                with st.spinner(f"Executando avaliação no split '{split_choice}'..."):
                    try:
                        out = run_all(split=split_choice, run_judge=use_judge)
                        out_path = RESULTS_TRAIN_PATH if split_choice == "train" else (RESULTS_TEST_PATH if split_choice == "test" else ROOT / "eval" / "results.json")
                        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
                        st.success("✅ Avaliação finalizada e salva com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro ao rodar avaliação: {e}")

        # Carrega arquivo de resultados existente
        target_path = RESULTS_TRAIN_PATH if split_choice == "train" else (RESULTS_TEST_PATH if split_choice == "test" else ROOT / "eval" / "results.json")
        if target_path.exists():
            eval_data = json.loads(target_path.read_text(encoding="utf-8"))
            summary = eval_data.get("summary", {})
            results = eval_data.get("results", [])

            # Métricas agregadas
            cols = st.columns(4)
            traj_avg = summary.get("trajectory_avg_score", 0.0)
            judge_avg = summary.get("judge_avg_score", 0.0)
            decisions = summary.get("decisions", {})

            metrics = [
                ("Total Casos", summary.get("total", 0), "#e2e8f0"),
                ("Score Trajetória", f"{traj_avg:.2f}", "#3b82f6" if traj_avg >= 0.8 else "#f59e0b"),
                ("Nota Juiz LLM", f"{judge_avg:.1f}/10" if judge_avg else "—", "#22c55e" if judge_avg >= 7.0 else "#8892a0"),
                ("Distribuição", f"Orient: {decisions.get('orient',0)} | Act: {decisions.get('act',0)} | Esc: {decisions.get('escalate',0)}", "#f59e0b"),
            ]
            for col, (label, val, color) in zip(cols, metrics):
                with col:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-label">{label}</div>
                        <div class="metric-value" style="color:{color}; font-size:16px;">{val}</div>
                    </div>
                    """, unsafe_allow_html=True)

            # Tabela de resultados individuais
            table_rows = []
            for r in results:
                table_rows.append({
                    "Ticket": r.get("ticket_id", "—"),
                    "Decisão": f"{DECISION_ICONS.get(r.get('decision'), '⚪')} {r.get('decision', '—')}",
                    "Qualidade": f"{QUALITY_ICONS.get(r.get('quality_verdict'), '⚪')} {r.get('quality_verdict', '—')}",
                    "Trajetória Score": r.get("trajectory", {}).get("score", "—") if isinstance(r.get("trajectory"), dict) else "—",
                    "Nota Juiz": r.get("judge", {}).get("nota_geral", "—") if isinstance(r.get("judge"), dict) else "—",
                })

            st.dataframe(
                pd.DataFrame(table_rows),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info(f"Nenhum resultado de avaliação salvo para o split '{split_choice}'. Clique no botão acima para rodar.")

    with sub_t2:
        pg_status = check_postgres_health()
        if pg_status["online"]:
            counts = count_by_version()
            if counts:
                st.markdown("<b>Versões Registradas na Tabela <code>execucoes</code>:</b>", unsafe_allow_html=True)
                st.json(counts)

                v_list = list(counts.keys())
                if len(v_list) >= 2:
                    st.markdown("#### Comparar Distribuição entre Duas Versões")
                    c1, c2 = st.columns(2)
                    v_a = c1.selectbox("Versão A", options=v_list, index=0)
                    v_b = c2.selectbox("Versão B", options=v_list, index=1 if len(v_list) > 1 else 0)
                    comp_rows = compare_versions(v_a, v_b)
                    if comp_rows:
                        st.dataframe(pd.DataFrame(comp_rows), use_container_width=True)
            else:
                st.info("Tabela `execucoes` conectada, mas ainda sem registros gravados. Execute tickets para registrar.")
        else:
            st.warning("⚠️ PostgreSQL não está acessível no momento. Para iniciar o banco e habilitar comparação de versões:")
            st.code("make postgres-up\nmake postgres-init", language="bash")


# ── Componentes de UI: Aba Playground (Ticket Customizado) ───────────────────
def tab_playground(cases: List[Dict[str, Any]]):
    """Aba para testar qualquer chamado customizado livremente."""
    st.markdown("""
    <div class="tractian-card">
        <h3 style="margin:0 0 8px 0; font-size:16px;">🧪 Playground · Ticket Customizado</h3>
        <p style="color:#8892a0; font-size:13px; margin:0;">
            Escreva uma mensagem de cliente arbitrária e escolha um ativo para testar a resposta e o fluxo investigativo do agente.
        </p>
    </div>
    """, unsafe_allow_html=True)

    companies = sorted(list({c.get("company_id") for c in cases if c.get("company_id")}))
    assets = sorted(list({c.get("asset_id") for c in cases if c.get("asset_id")}))
    users = sorted(list({c.get("user_id") for c in cases if c.get("user_id")}))

    col1, col2, col3 = st.columns(3)
    with col1:
        comp_sel = st.selectbox("Empresa", options=companies, index=0)
    with col2:
        asset_sel = st.selectbox("Ativo", options=assets, index=0)
    with col3:
        user_sel = st.selectbox("Usuário", options=users, index=0)

    msg_input = st.text_area(
        "Mensagem do Cliente / Solicitação de Suporte",
        value="Identificamos vibração elevada no motor nas últimas 24 horas. Poderiam verificar se há desbalanceamento ou falha de rolamento?",
        height=100,
    )

    if st.button("▶ Executar Ticket Customizado", key="btn_run_custom", type="primary"):
        custom_case = {
            "ticket_id": f"TKT-CUST-{int(time.time())}",
            "id": f"cust_{int(time.time())}",
            "company_id": comp_sel,
            "asset_id": asset_sel,
            "user_id": user_sel,
            "message": msg_input,
        }
        with st.spinner("Investigando ticket customizado na API Tractian..."):
            try:
                res, elapsed, interrupted = execute_agent_stepwise(custom_case)
                st.session_state["custom_result"] = res
                st.session_state["custom_elapsed"] = elapsed
                st.session_state["custom_interrupted"] = interrupted
                st.session_state["custom_case"] = custom_case
                st.success(f"✅ Execução concluída em {elapsed:.2f}s!")
            except Exception as e:
                st.error(f"❌ Erro na execução: {e}")

    if "custom_result" in st.session_state and st.session_state["custom_result"]:
        res = st.session_state["custom_result"]
        el = st.session_state.get("custom_elapsed")
        inter = st.session_state.get("custom_interrupted", False)
        c_case = st.session_state.get("custom_case", {})

        st.markdown("<hr style='border-color:#2d3142; margin:20px 0;'>", unsafe_allow_html=True)
        render_result_cards(res, el)
        render_hitl_section(c_case.get("ticket_id", "custom"), res, inter)
        render_response(res)


# ── Função Principal ─────────────────────────────────────────────────────────
def main():
    render_header()

    cases = load_cases()
    if not cases:
        st.error("Não foi possível carregar os casos de teste em `agent-input/cases.json`.")
        st.stop()

    selected_case, filter_mod = render_sidebar(cases)

    # Identificadores de estado da sessão
    ticket_id = selected_case["ticket_id"]
    result_key = f"result_{ticket_id}"
    elapsed_key = f"elapsed_{ticket_id}"
    interrupted_key = f"is_interrupted_{ticket_id}"

    # Disparo de execução normal
    if st.session_state.get("run_triggered") == ticket_id:
        st.session_state.run_triggered = None
        with st.spinner("🔍 Investigando ticket na API e LangGraph..."):
            try:
                result, elapsed, is_interrupted = execute_agent_stepwise(selected_case)
                st.session_state[result_key] = result
                st.session_state[elapsed_key] = elapsed
                st.session_state[interrupted_key] = is_interrupted
                if is_interrupted:
                    st.warning("⚠️ O agente pausou solicitando confirmação humana (HITL).")
                else:
                    st.success(f"✅ Concluído em {elapsed:.2f}s")
            except Exception as e:
                st.error(f"❌ Erro na execução do agente: {e}")
                st.exception(e)

    # Disparo de re-execução (limpa cache local)
    if st.session_state.get("rerun_triggered") == ticket_id:
        st.session_state.rerun_triggered = None
        st.session_state.pop(result_key, None)
        st.session_state.pop(elapsed_key, None)
        st.session_state.pop(interrupted_key, None)
        st.session_state.pop(f"hitl_confirmed_{ticket_id}", None)
        st.session_state.pop(f"hitl_cancelled_{ticket_id}", None)
        with st.spinner("🔄 Re-executando agente..."):
            try:
                result, elapsed, is_interrupted = execute_agent_stepwise(selected_case)
                st.session_state[result_key] = result
                st.session_state[elapsed_key] = elapsed
                st.session_state[interrupted_key] = is_interrupted
                st.success(f"✅ Re-execução concluída em {elapsed:.2f}s")
            except Exception as e:
                st.error(f"❌ Erro: {e}")

    # Recupera estado do ticket selecionado
    result = st.session_state.get(result_key)
    elapsed = st.session_state.get(elapsed_key)
    is_interrupted = st.session_state.get(interrupted_key, False)

    # Abas da Aplicação
    tab_diag, tab_tr, tab_met, tab_play = st.tabs([
        "📋 Diagnóstico & HITL",
        "🔍 Trace & Sinais Técnicos",
        "📈 Métricas & Avaliação",
        "🧪 Playground",
    ])

    with tab_diag:
        tab_diagnostico(selected_case, result, elapsed, is_interrupted)

    with tab_tr:
        tab_trace(result)

    with tab_met:
        tab_metricas()

    with tab_play:
        tab_playground(cases)


if __name__ == "__main__":
    main()
