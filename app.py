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
from agent.logging.postgres import log_execution, count_by_version, compare_versions
from agent.logging.postgres import check_health as postgres_health
from agent.logging.postgres import (
    registrar_ticket,
    enfileirar_aprovacao,
    listar_pendencias,
    resolver_pendencia,
    historico_aprovacoes,
    estatisticas_autonomia,
    listar_tickets,
    carregar_ticket,
    pendencia_de,
)
from agent.graph.checkpointer import status as checkpointer_status
from agent.logging.phoenix import setup_phoenix_tracing, run_in_phoenix_trace
from agent.version import AGENT_VERSION
from eval.runner import build_initial_state
from eval.assertions.trajectory import classificar_erro
from langgraph.types import Command

# ── Observabilidade ──────────────────────────────────────────────────────────
# Precisa ser explícito: sem isto a demo final não gera trace nenhum, porque
# as invocações da UI não passam pelo eval/runner.
@st.cache_resource
def _init_tracing() -> bool:
    return setup_phoenix_tracing()


# ── Constantes & Configuração ────────────────────────────────────────────────
CASES_PATH = ROOT / "agent-input" / "cases.json"
RESULTS_TRAIN_PATH = ROOT / "eval" / "results-train.json"
RESULTS_TEST_PATH = ROOT / "eval" / "results-test.json"


def _caminho_resultados(split: str):
    """Arquivo de resultados de cada split. `all` é o único que foge do padrão."""
    return ROOT / "eval" / ("results.json" if split == "all" else f"results-{split}.json")

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
    """Verifica conectividade com PostgreSQL, reportando a causa da falha."""
    ok, motivo = postgres_health()
    if ok:
        return {"online": True, "msg": "Postgres :5432 Conectado"}
    return {"online": False, "msg": "Postgres :5432 Offline", "detail": motivo}


@st.cache_data(ttl=5)
def check_phoenix_health() -> Dict[str, Any]:
    """Verifica se o Phoenix Tracing está acessível (respeita PHOENIX_ENDPOINT)."""
    endpoint = os.getenv("PHOENIX_ENDPOINT", "http://localhost:6006")
    try:
        resp = httpx.get(endpoint, timeout=1.0)
        if resp.status_code in (200, 302, 307):
            return {"online": True, "msg": "Phoenix :6006 Ativo"}
        return {"online": False, "msg": "Phoenix :6006 Inativo"}
    except Exception:
        return {"online": False, "msg": "Phoenix :6006 Inativo"}


def check_llm_config() -> Dict[str, Any]:
    """Descreve a cadeia de provedores, não só o primeiro.

    Ler as variáveis de ambiente direto mostrava apenas o provedor principal — a
    interface diria "Groq" mesmo depois de a chamada ter caído no fallback.
    """
    from agent.llm import descrever_provedores, juiz_independente
    try:
        cadeia = descrever_provedores("agente")
        juiz = descrever_provedores("juiz")
    except Exception:
        cadeia, juiz = [], []

    principal = cadeia[0] if cadeia else ""
    provedor, _, modelo = principal.partition(":")
    return {
        "configured": bool(cadeia),
        "model": modelo or "—",
        "provider": provedor or "—",
        "cadeia": cadeia,
        "fallbacks": max(len(cadeia) - 1, 0),
        "juiz": juiz[0] if juiz else "—",
        "juiz_independente": juiz_independente(),
    }


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


# Rótulos das abas. Ficam em constantes porque a navegação programática (abrir um
# ticket a partir de uma notificação) escreve o rótulo em `st.session_state`, e um
# rótulo escrito à mão em dois lugares diverge no primeiro ajuste de texto.
# O valor guardado e um id estavel, nao o rotulo: o rotulo das notificacoes
# carrega o contador de pendencias, e se ele fosse a identidade da secao,
# aprovar um item mudaria o rotulo e a navegacao perderia a posicao — o operador
# seria jogado para fora da fila exatamente ao trabalhar nela.
ABA_KEY = "aba_ativa"
ABA_DIAGNOSTICO = "diagnostico"
ABA_NOTIFICACOES = "notificacoes"
ABA_TRACE = "trace"
ABA_METRICAS = "metricas"
ABA_PLAYGROUND = "playground"
ABAS = [ABA_DIAGNOSTICO, ABA_NOTIFICACOES, ABA_TRACE, ABA_METRICAS, ABA_PLAYGROUND]


# ── Execução do Grafo com HITL Interativo ───────────────────────────────────
def execute_agent_stepwise(case: Dict[str, Any]) -> Tuple[Dict[str, Any], float, bool]:
    """Executa o grafo de um ticket, parando no `interrupt()` se houver.

    Retorna (estado, tempo, pausado). Quando pausa, a ação vai para a fila de
    aprovações no Postgres — a mesma fila que a ingestão alimenta. Assim um
    ticket disparado aqui aparece na aba Notificações como qualquer outro, e
    continua lá se o navegador fechar.
    """
    _init_tracing()
    start = time.time()
    state = build_initial_state(case)
    ticket_id = case["ticket_id"]

    # thread_id novo a cada execução: o checkpointer guarda o estado por thread,
    # então reusar o ticket_id cairia num checkpoint antigo (já pausado ou
    # finalizado). O id é a chave para retomar exatamente esta execução, e vai
    # junto para a fila — é assim que outro processo consegue continuá-la.
    thread_id = f"{ticket_id}-{int(time.time() * 1000)}"
    st.session_state[f"thread_{ticket_id}"] = thread_id
    config = {"configurable": {"thread_id": thread_id}}

    with run_in_phoenix_trace(thread_id, ticket_id, asset_id=case.get("asset_id")):
        result = agent_graph.invoke(state, config=config)
    elapsed = time.time() - start

    pausado = "__interrupt__" in result
    try:
        # A mesma classificação que a ingestão aplica. Sem ela, rodar um ticket
        # aqui gravava `split='avulso'` e sem gabarito, sobrescrevendo a linha da
        # ingestão — cada execução manual apagava um ticket das métricas.
        from agent.ingest import classificar
        split, esperada, nota = classificar(case, result)
        # Registra também na pausa: um ticket abandonado no interrupt (o operador
        # nunca confirma nem cancela) sumia do histórico, porque só o caminho
        # completo e o resume gravavam.
        registrar_ticket(
            result, agent_version=AGENT_VERSION, thread_id=thread_id,
            status="aguardando_humano" if pausado else "concluido",
            split=split, decisao_esperada=esperada, trajectory_score=nota,
        )
    except Exception:
        pass

    if pausado:
        try:
            enfileirar_aprovacao(
                ticket_id=ticket_id, thread_id=thread_id,
                agent_version=AGENT_VERSION, asset_id=case.get("asset_id"),
                payload=result["__interrupt__"][0].value,
            )
        except Exception:
            pass
        return result, elapsed, True

    return result, elapsed, False


def resume_agent_action(ticket_id: str, confirm: bool,
                        thread_id: Optional[str] = None) -> Dict[str, Any]:
    """Retoma um grafo congelado no HITL e fecha a pendência correspondente.

    `thread_id` explícito é o que permite retomar da aba Notificações uma
    execução que **outro processo** pausou — a ingestão, por exemplo. Sem ele,
    cai no id guardado na sessão (o caminho de quem rodou o ticket aqui mesmo).
    """
    thread_id = thread_id or st.session_state.get(f"thread_{ticket_id}", ticket_id)
    config = {"configurable": {"thread_id": thread_id}}
    with run_in_phoenix_trace(thread_id, ticket_id):
        resumed = agent_graph.invoke(Command(resume=confirm), config=config)
    try:
        # Retomar não é um ticket novo: é a continuação de um que já foi
        # classificado. Herdar conjunto e gabarito da linha anterior evita que
        # aprovar uma ação tire o ticket do conjunto a que ele pertence.
        anterior = carregar_ticket(ticket_id, AGENT_VERSION) or {}
        registrar_ticket(
            resumed, agent_version=AGENT_VERSION, thread_id=thread_id,
            status="concluido" if confirm else "cancelado",
            split=anterior.get("split"),
            decisao_esperada=anterior.get("decisao_esperada"),
            trajectory_score=anterior.get("trajectory_score"),
        )
        resolver_pendencia(thread_id, aprovado=confirm, por="operador")
    except Exception:
        pass
    return resumed


def _acao_no_trace(trace: list) -> tuple:
    """(action_type, action_target) registrados pelo nó `act`, se ele rodou."""
    passo = next((t for t in (trace or []) if t.get("node") == "act"), None)
    if not passo:
        return None, None
    return passo.get("action_type"), passo.get("action_target")


def estado_do_banco(ticket_id: str) -> Tuple[Optional[Dict[str, Any]], bool]:
    """Reconstrói o resultado de um ticket a partir do Postgres.

    A ingestão (`make demo`) processa cada ticket uma vez e grava tudo — trace,
    decisão, resposta, lacunas. Sem esta função, abrir a plataforma depois disso
    mostrava um ticket em branco pedindo "Executar Agente", porque as abas liam
    apenas `st.session_state`, que é vazio num navegador recém-aberto. O trabalho
    já estava feito; a interface é que não sabia procurá-lo.

    Devolve (estado, pausado) no mesmo formato que `execute_agent_stepwise`, de
    modo que os renderizadores não precisam saber de onde o dado veio.
    """
    try:
        linha = carregar_ticket(ticket_id, AGENT_VERSION)
    except Exception:
        return None, False
    if not linha:
        return None, False

    estado: Dict[str, Any] = {
        "ticket_id": linha["ticket_id"],
        "asset_id": linha.get("asset_id"),
        "user_id": linha.get("user_id"),
        "decision": linha.get("decision"),
        "quality_verdict": linha.get("quality_verdict"),
        "data_gaps": linha.get("data_gaps") or {},
        "trace": linha.get("trace") or [],
        "response": linha.get("response"),
        # Marca a procedência: a aba avisa que isto veio do último
        # processamento, não de uma execução desta sessão.
        "_processado_em": linha.get("created_at"),
    }
    estado["action_type"], estado["action_target"] = _acao_no_trace(estado["trace"])

    pausado = linha.get("status") == "aguardando_humano"
    if pausado:
        pend = pendencia_de(ticket_id, AGENT_VERSION)
        if pend:
            # O painel de HITL lê estes campos quando não há um objeto
            # `Interrupt` em mãos — e não há, porque quem pausou foi outro
            # processo. Os dados são os mesmos: o `interrupt()` gravou-os na fila.
            estado["action_type"] = pend.get("action_type")
            estado["action_target"] = pend.get("action_target")
            estado["decision_justification"] = pend.get("justification")
            estado["data_gaps"] = pend.get("gaps") or estado["data_gaps"]
        else:
            # A linha diz "aguardando" mas a fila não tem pendência aberta: ela
            # foi decidida ou substituída por uma reingestão. Tratar como pausado
            # ofereceria ao operador botões que retomariam um checkpoint morto.
            pausado = False

    # O `thread_id` do banco é a chave para retomar ESTA execução. Sem gravá-lo,
    # o botão de confirmar cairia no id da sessão e tentaria retomar outra coisa.
    if linha.get("thread_id"):
        st.session_state[f"thread_{ticket_id}"] = linha["thread_id"]

    return estado, pausado


PEDIDO_NAVEGACAO = "_navegar_para_ticket"


def abrir_ticket(ticket_id: str, cases: List[Dict[str, Any]]) -> bool:
    """Registra o pedido de abrir o diagnóstico de um ticket.

    Não escreve nas chaves dos widgets aqui: o Streamlit recusa modificar a
    chave de um widget depois que ele foi instanciado, e este botão vive dentro
    das abas — ou seja, depois da barra lateral e das próprias abas. Escrever
    direto levanta `StreamlitWidgetAlreadyInstantiatedError`.

    O pedido fica numa chave comum e é aplicado por `aplicar_navegacao()` no
    início do próximo ciclo, antes de qualquer widget existir.

    Devolve False quando o ticket não está entre os casos da barra lateral (é o
    caso dos cenários derivados, que não fazem parte dos 17 chamados oficiais).
    """
    if not any(c["ticket_id"] == ticket_id for c in cases):
        return False
    st.session_state[PEDIDO_NAVEGACAO] = ticket_id
    return True


def aplicar_navegacao(cases: List[Dict[str, Any]]):
    """Consome um pedido de `abrir_ticket`, posicionando barra lateral e aba.

    Precisa rodar antes de `render_sidebar` e de `st.tabs`: é a janela em que as
    chaves desses widgets ainda podem ser escritas. O filtro de modalidade volta
    a "Todos" porque o ticket pedido pode não estar na modalidade filtrada — sem
    isso, a seleção apontaria para uma opção fora da lista.
    """
    ticket_id = st.session_state.pop(PEDIDO_NAVEGACAO, None)
    if not ticket_id:
        return
    caso = next((c for c in cases if c["ticket_id"] == ticket_id), None)
    if not caso:
        return
    st.session_state["sidebar_filter_modality"] = "Todos"
    st.session_state["selected_ticket_label"] = format_case_option(caso)
    st.session_state[ABA_KEY] = ABA_DIAGNOSTICO


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
        extra = f" +{llm_c['fallbacks']} fallback" if llm_c["fallbacks"] else ""
        llm_badge = f'<span style="background:#1a2332; color:#f59e0b; padding:4px 10px; border-radius:16px; font-size:11px; border:1px solid #3d2e1a;" title="{" → ".join(llm_c["cadeia"])}">⚡ {llm_c["provider"]}{extra} ({AGENT_VERSION})</span>'

        # Autoavaliação precisa estar visível na tela, não só na documentação:
        # quando juiz e agente são o mesmo modelo, a nota tende a ser inflada.
        if llm_c["juiz_independente"]:
            juiz_badge = f'<span style="background:#1a2332; color:#4ade80; padding:4px 10px; border-radius:16px; font-size:11px; border:1px solid #1e3a2f;" title="{llm_c["juiz"]}">⚖️ juiz independente</span>'
        else:
            juiz_badge = '<span style="background:#2a2418; color:#fbbf24; padding:4px 10px; border-radius:16px; font-size:11px; border:1px solid #4a3a1e;" title="Juiz e agente são o mesmo modelo — a nota tende a ser inflada">⚖️ autoavaliação</span>'

        st.markdown(f"""
        <div style="display:flex; gap:6px; justify-content:flex-end; align-items:center; flex-wrap:wrap; margin-top:6px;">
            {api_badge}
            {pg_badge}
            {px_badge}
            {llm_badge}
            {juiz_badge}
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

        if st.button("▶ Executar Agente", key="btn_run", width="stretch"):
            st.session_state.run_triggered = selected_case["ticket_id"]

        if st.button("🔄 Limpar Cache e Re-executar", key="btn_rerun", width="stretch"):
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


def render_handoff_support_ticket(case: Dict[str, Any], result: Dict[str, Any]):
    """Renderiza um Painel de Chamado de Suporte / Handoff usando componentes nativos Streamlit."""
    decision = result.get("decision")
    if decision != "escalate":
        return

    gaps = result.get("data_gaps") or result.get("gaps") or {}
    gaps_str = ", ".join(gaps.keys()) if isinstance(gaps, dict) and gaps else "Dados críticos não confirmados"
    ticket_id = case.get("ticket_id", "TKT-UNKNOWN")
    assigned_key = f"assigned_tech_{ticket_id}"

    # Container principal do chamado
    with st.container(border=True):
        # Cabeçalho do chamado
        col_header1, col_header2 = st.columns([3, 1])
        with col_header1:
            st.markdown("### 🎫 CHAMADO DE SUPORTE ESCALADO")
            st.caption(f"Ticket ID: `{ticket_id}`")
        with col_header2:
            st.markdown("<div style='text-align:right; margin-top:8px;'></div>", unsafe_allow_html=True)
            st.badge("🟡 Aguardando Atendimento Humano", color="orange")

        st.divider()

        # Grid de informações do chamado
        st.markdown("**📋 Contexto do Chamado**")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("🏢 Cliente", case.get('company_id', '').replace('comp_','').replace('_',' ').title())
        with c2:
            st.metric("⚙️ Ativo", case.get('asset_id', '—'))
        with c3:
            st.metric("👤 Solicitante", case.get('user_id', '—'))
        with c4:
            st.metric("⚠️ Bloqueio IA", gaps_str, help="Lacunas críticas detectadas nos sinais")

        # Por que o agente não finalizou
        with st.expander("🛑 **Por que o Agente não finalizou automaticamente?**", expanded=True):
            st.markdown("""
            O agente coletou sinais preliminares, mas o estado do **Baseline** ou das **Análises** veio com 
            inconsistência/indisponibilidade na API industrial. 
            
            Na metodologia Tractian, limiares de vibração derivam do comportamento aprendido da máquina (baseline próprio do ativo). 
            Para evitar passar falsos diagnósticos ao cliente, o atendimento foi repassado para a engenharia de suporte.
            """)

        # Ações recomendadas
        with st.expander("🛠️ **Ações Recomendadas para o Engenheiro Humano**", expanded=True):
            st.markdown(f"""
            1. **Orientar o Cliente:** Explicar que o alarme é dinâmico (baseado no histórico da máquina) e não uma norma fixa genérica.
            
            2. **Verificar Sensor:** Inspecionar se o sensor do ativo `{case.get('asset_id','')}` teve perda de sinal ou ruído.
            
            3. **Recalibrar Baseline:** Validar se o baseline precisa ser restabelecido na plataforma após intervenção mecânica.
            """)

        # Controles de Atribuição de Técnico
        st.markdown("---")
        st.markdown("**👨‍🔧 Atribuição de Responsável**")
        
        c1, c2, c3 = st.columns([2.5, 1.2, 1.3])
        with c1:
            tech_assigned = st.selectbox(
                "Técnico Responsável:",
                options=[
                    "Eng. Carlos Silva (Especialista em Vibração e Preditiva)",
                    "Eng. Ana Souza (Suporte N3 & Diagnóstico de Ativos)",
                    "Eng. Rodrigo Lima (Engenharia de Conectividade e Sensores)",
                    "Eng. Juliana Costa (Especialista em Modelos e Baselines)",
                ],
                key=f"select_{assigned_key}",
            )
        with c2:
            st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
            if st.button("📌 Assumir Chamado", key=f"btn_assign_{ticket_id}", type="primary", width="stretch"):
                st.session_state[assigned_key] = tech_assigned
                st.success(f"✅ Chamado atribuído a {tech_assigned.split('(')[0].strip()}!")
                st.rerun()

        if assigned_key in st.session_state:
            st.success(f"👨‍🔧 **Chamado sob responsabilidade de:** `{st.session_state[assigned_key]}`")


def render_result_cards(result: Dict[str, Any], elapsed: Optional[float] = None):
    """Renderiza os cards com métricas da decisão e telemetria da IA."""
    verdict = result.get("quality_verdict")
    decision = result.get("decision")
    gaps = result.get("data_gaps") or result.get("gaps") or {}
    # `raw` (os envelopes brutos) só existe numa execução desta sessão — não é
    # persistido, porque guardar o payload inteiro de cada ticket incharia o
    # banco. Para um diagnóstico carregado do Postgres, o número de chamadas sai
    # do trace, que registra `tools_called` a cada rodada de investigação.
    raw_keys = list(result.get("raw", {}).keys())
    if not raw_keys:
        raw_keys = [
            tool
            for passo in (result.get("trace") or [])
            if passo.get("node") == "investigate"
            for tool in (passo.get("tools_called") or [])
        ]

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

    if is_interrupted:
        interrupt_info = {}
        if "__interrupt__" in result and result["__interrupt__"]:
            interrupt_info = result["__interrupt__"][0].value

        action_type = interrupt_info.get("action_type") or result.get("action_type") or "Ação de Plataforma"
        action_target = interrupt_info.get("action_target") or result.get("action_target") or "Alvo não especificado"
        justification = interrupt_info.get("justification") or result.get("decision_justification") or ""
        # O `interrupt` já carrega as lacunas, e elas são o que mais deveria pesar
        # na decisão do operador: aprovar uma mutação sabendo que o baseline não
        # veio é diferente de aprovar com a evidência completa.
        gaps_hitl = interrupt_info.get("gaps") or result.get("data_gaps") or {}

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

        if gaps_hitl:
            with st.expander(f"⚠️ O agente decidiu com {len(gaps_hitl)} lacuna(s) de dado — revise antes de aprovar",
                             expanded=True):
                for categoria, problemas in gaps_hitl.items():
                    st.markdown(f"**{categoria}** — {'; '.join(problemas) if isinstance(problemas, list) else problemas}")
        else:
            st.success("Nenhuma lacuna registrada: o agente decidiu com evidência completa.", icon="✓")

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


def _render_ancoragem(result: Dict[str, Any]):
    """Mostra em que evidência a resposta se apoiou e o que faltou.

    O agente é obrigado a enumerar `evidencias` e `limitacoes` antes de redigir —
    foi esse andaime que levou a fundamentação de 5,75 para 8,38 no juiz. Sem
    exibir os dois campos, o operador não consegue conferir se a resposta está
    de fato ancorada no que a API devolveu.
    """
    passo = next((s for s in (result.get("trace") or [])
                  if isinstance(s, dict) and s.get("node") == "decide"), {})
    evidencias = result.get("evidencias") or passo.get("evidencias") or []
    limitacoes = result.get("limitacoes") or passo.get("limitacoes") or []
    modelo = passo.get("modelo")
    do_cache = passo.get("from_cache")

    if not (evidencias or limitacoes or modelo):
        return

    esq, dir_ = st.columns(2)
    with esq:
        with st.container(border=True):
            st.markdown("**Evidências citadas**")
            if evidencias:
                for e in evidencias:
                    st.markdown(f"- {e}")
            else:
                st.caption("O modelo não enumerou evidências nesta decisão.")
    with dir_:
        with st.container(border=True):
            st.markdown("**Limitações reconhecidas**")
            if limitacoes:
                for l in limitacoes:
                    st.markdown(f"- {l}")
            else:
                st.caption("Nenhuma lacuna declarada.")

    if modelo:
        origem = "cache de decisões" if do_cache else "chamada nova ao LLM"
        st.caption(f"Decidido por `{modelo}` · {origem}")


def render_response(result: Dict[str, Any], case: Dict[str, Any]):
    """Exibe a resposta formatada do agente para o cliente."""
    decision = result.get("decision")
    response = result.get("response") or result.get("decision_justification") or ""
    if not response:
        return

    st.markdown(f"""
    <div class="tractian-card" style="border-left:4px solid #ff6b35;">
        <div style="font-size:11px; color:#8892a0; text-transform:uppercase; letter-spacing:1px; margin-bottom:8px;">
            Orientação Técnica / Resposta ao Cliente
        </div>
        <div style="font-size:14px; line-height:1.7; color:#e2e8f0; white-space:pre-wrap;">{response}</div>
    </div>
    """, unsafe_allow_html=True)

    _render_ancoragem(result)

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
            st.info(f"**Parecer do Juiz:** {je.get('razao', '—')}", icon="⚖️")

            # Quem julgou importa: se for o mesmo modelo que respondeu, a nota
            # tende a ser inflada — sobretudo no eixo de honestidade.
            modelo_juiz = je.get("modelo_juiz") or "—"
            if je.get("juiz_independente"):
                st.caption(f"Julgado por `{modelo_juiz}` — provedor independente do agente.")
            else:
                st.warning(
                    f"Julgado por `{modelo_juiz}`, **o mesmo modelo que respondeu**. "
                    "Autoavaliação tende a inflar a nota, sobretudo em honestidade. "
                    "Configure `JUDGE_*` no `agent/.env` para separar.",
                    icon="⚠️",
                )


def tab_diagnostico(case: Dict[str, Any], result: Optional[Dict[str, Any]], elapsed: Optional[float], is_interrupted: bool):
    """Aba principal: ticket, Chamado de Suporte/Handoff, métricas de resultado, HITL e resposta."""
    render_ticket_card(case)

    if result:
        # Procedência: sem isto, um diagnóstico vindo da ingestão é
        # indistinguível de um que acabou de rodar, e o operador não tem como
        # saber se está olhando dado de agora ou da semana passada.
        processado_em = result.get("_processado_em")
        if processado_em:
            # O Postgres devolve em UTC. Mostrar o horário cru faria o operador
            # ler três horas a menos do que o relógio dele — uma leitura errada
            # que parece um sistema desatualizado.
            local = processado_em.astimezone() if processado_em.tzinfo else processado_em
            st.caption(
                f"Diagnóstico do processamento de "
                f"**{local.strftime('%d/%m às %H:%M')}**, carregado do banco. "
                "Use **▶ Executar Agente** para rodar de novo."
            )
        # Se escalou para humano, renderiza o Chamado de Suporte Handoff com prioridade máxima
        render_handoff_support_ticket(case, result)
        render_result_cards(result, elapsed)
        render_hitl_section(case["ticket_id"], result, is_interrupted)
        render_response(result, case)
    else:
        st.info(
            "Este ticket ainda não foi processado. Clique em **▶ Executar Agente** na "
            "barra lateral, ou rode `make ingest` para processar todos de uma vez.",
            icon="💡",
        )


# ── Componentes de UI: Aba Trace & Grafo Visual Conectado ────────────────────
def render_visual_connected_graph(result: Dict[str, Any]):
    """Renderiza um fluxograma conectado de nós estilizado com cores de status dinâmicas."""
    trace = result.get("trace", [])
    raw = result.get("raw", {})
    verdict = result.get("quality_verdict", "ok")
    decision = result.get("decision", "orient")

    # Mapeamento de cores de cada nó
    # 1. Investigate: Verde se consultou, Vermelho se falhou tudo
    inv_color = "#22c55e" if raw else "#ef4444"
    inv_label = f"1. INVESTIGATE<br/>({len(raw)} tools consultadas)"

    # 2. Quality Check: Verde se OK, Amarelo se Partial/Incomplete, Vermelho se Unavailable
    qc_map = {"ok": ("#22c55e", "OK"), "partial": ("#f59e0b", "PARCIAL"), "incomplete": ("#f97316", "INCOMPLETO"), "unavailable": ("#ef4444", "INDISPONÍVEL")}
    qc_color, qc_tag = qc_map.get(verdict, ("#6b7280", "—"))
    qc_label = f"2. QUALITY_CHECK<br/>({qc_tag})"

    # 3. Decide: Roxo normal ou Vermelho se forçado a escalar
    dec_color = "#ef4444" if verdict == "unavailable" else "#8b5cf6"
    dec_label = f"3. DECIDE<br/>(Decisão: {decision.upper()})"

    # 4. Nó terminal
    term_node = "respond" if decision == "orient" else ("act" if decision == "act" else "escalate")
    term_color = "#22c55e" if decision == "orient" else ("#f59e0b" if decision == "act" else "#ef4444")
    term_label = f"4. {term_node.upper()}<br/>({'Orientar' if decision=='orient' else ('Executar Ação' if decision=='act' else 'Handoff Humano')})"

    st.markdown("#### 🗺️ Fluxograma Visual Conectado do LangGraph")
    st.markdown(f"""
    <div style="background:#0d0f16; border:1px solid #2d3142; border-radius:10px; padding:20px; margin-bottom:16px;">
        <div style="display:flex; align-items:center; justify-content:center; gap:8px; flex-wrap:wrap;">
            <!-- Nó 1 -->
            <div style="background:#141d1a; border:2px solid {inv_color}; border-radius:8px; padding:12px 18px; text-align:center; min-width:140px; box-shadow:0 0 10px rgba(34,197,94,0.15);">
                <div style="font-weight:700; color:{inv_color}; font-size:13px;">1. INVESTIGATE</div>
                <div style="font-size:11px; color:#8892a0; margin-top:4px;">{len(raw)} tools consultadas</div>
            </div>
            <div style="color:#64748b; font-size:20px; font-weight:700;">➔</div>
            <!-- Nó 2 -->
            <div style="background:#1a1914; border:2px solid {qc_color}; border-radius:8px; padding:12px 18px; text-align:center; min-width:140px; box-shadow:0 0 10px rgba(245,158,11,0.15);">
                <div style="font-weight:700; color:{qc_color}; font-size:13px;">2. QUALITY_CHECK</div>
                <div style="font-size:11px; color:#8892a0; margin-top:4px;">Status: <b>{qc_tag}</b></div>
            </div>
            <div style="color:#64748b; font-size:20px; font-weight:700;">➔</div>
            <!-- Nó 3 -->
            <div style="background:#17141d; border:2px solid {dec_color}; border-radius:8px; padding:12px 18px; text-align:center; min-width:140px; box-shadow:0 0 10px rgba(139,92,246,0.15);">
                <div style="font-weight:700; color:{dec_color}; font-size:13px;">3. DECIDE</div>
                <div style="font-size:11px; color:#8892a0; margin-top:4px;">Deliberação: <b>{decision.upper()}</b></div>
            </div>
            <div style="color:#64748b; font-size:20px; font-weight:700;">➔</div>
            <!-- Nó 4 -->
            <div style="background:#1f1414; border:2px solid {term_color}; border-radius:8px; padding:12px 18px; text-align:center; min-width:140px; box-shadow:0 0 10px rgba(239,68,68,0.15);">
                <div style="font-weight:700; color:{term_color}; font-size:13px;">4. {term_node.upper()}</div>
                <div style="font-size:11px; color:#8892a0; margin-top:4px;">{'Orientação Final' if decision=='orient' else ('Confirmação HITL' if decision=='act' else 'Handoff para Humano')}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_node_gap_inspector(result: Dict[str, Any]):
    """Inspetor interativo de nós para analisar gaps, erros e causas de bloqueio."""
    trace = result.get("trace", [])
    raw = result.get("raw", {})
    if not trace:
        st.info("Nenhum dado de execução disponível.")
        return

    st.markdown("#### 🔍 Inspetor de Detalhes & Gaps por Nó")

    node_options = [f"{i+1}. {step.get('node', 'unknown').upper()}" for i, step in enumerate(trace)]
    selected_idx = st.segmented_control(
        "Selecione um Nó para Inspecionar",
        options=list(range(len(node_options))),
        format_func=lambda i: node_options[i],
        default=0,
    )

    if selected_idx is None:
        selected_idx = 0

    curr_step = trace[selected_idx]
    curr_node = curr_step.get("node", "unknown")

    if curr_node == "investigate":
        tools = curr_step.get("tools_called", [])
        st.markdown(f"**Ferramentas consultadas nesta etapa:** `{', '.join(tools)}`")
        
        cols = st.columns(min(len(tools), 5) or 1)
        for idx, tool_name in enumerate(tools):
            env = raw.get(tool_name, {})
            mode = env.get("mode", "unknown") if isinstance(env, dict) else "unknown"
            mode_color = "#22c55e" if mode == "complete" else ("#f59e0b" if mode == "partial" else "#ef4444")
            with cols[idx % len(cols)]:
                st.markdown(f"""
                <div style="background:#0f1117; border:1px solid #2d3142; border-radius:8px; padding:10px; text-align:center;">
                    <div style="font-weight:700; color:#e2e8f0; font-size:12px;">{tool_name.upper()}</div>
                    <div style="color:{mode_color}; font-size:11px; font-weight:600; margin-top:4px;">mode: {mode}</div>
                </div>
                """, unsafe_allow_html=True)

        with st.expander("📦 Ver Envelopes Brutos Coletados (JSON)"):
            st.json({k: v for k, v in raw.items() if k in tools})

    elif curr_node == "quality_check":
        verdict = curr_step.get("verdict", "—")
        gaps = curr_step.get("gaps", {})
        next_t = curr_step.get("next_tool")

        st.markdown(f"**Veredicto da Qualidade:** `{verdict.upper()}` | **Próxima Ferramenta:** `{next_t or 'Nenhuma'}`")

        if gaps:
            st.markdown("<b>⚠️ Lacunas e Erros Identificados nos Sinais:</b>", unsafe_allow_html=True)
            for cat, gap_list in gaps.items():
                gap_desc = "; ".join(gap_list) if isinstance(gap_list, list) else str(gap_list)
                st.markdown(f"""
                <div style="background:#261814; border:1px solid #f97316; border-radius:8px; padding:10px 14px; margin-bottom:8px;">
                    <div style="color:#fdba74; font-weight:700; font-size:12px;">❌ Lacuna na Categoria: {cat.upper()}</div>
                    <div style="color:#fed7aa; font-size:12px; margin-top:2px;">{gap_desc}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("✅ Nenhuma lacuna detectada. Todos os sinais técnicos vieram completos e consistentes.")

    elif curr_node == "decide":
        decision = curr_step.get("decision", "—")
        from_cache = curr_step.get("from_cache", False)
        reason = curr_step.get("reason", "Análise contextual de evidências")
        st.markdown(f"**Decisão Emitida:** `{decision.upper()}` | **Origem:** `{'⚡ Cache em Disco' if from_cache else '🧠 LLM Realtime'}`")
        st.markdown(f"**Justificativa Técnica Interna:**")
        st.code(result.get("decision_justification", "—"))

    elif curr_node == "act":
        act_type = curr_step.get("action_type", "—")
        act_target = curr_step.get("action_target", "—")
        api_res = curr_step.get("api_result", "—")
        st.markdown(f"**Ação de Impacto Disparada:** `{act_type}` no alvo `{act_target}`")
        st.markdown(f"**Resposta da API Tractian:** `{api_res}`")

    elif curr_node in ("respond", "escalate"):
        st.markdown(f"**Saída do Atendimento ao Cliente / Engenharia:**")
        st.code(result.get("response", "—"))


def render_trace_timeline(result: Dict[str, Any]):
    """Renderiza timeline visual nativa do Streamlit (st.status) dos passos do agente."""
    trace = result.get("trace", [])
    if not trace:
        st.info("Nenhum trace de execução disponível.")
        return
    
    st.markdown("#### ⏱️ Timeline de Execução do Agente")
    
    node_config = {
        "investigate": {"icon": "🔍", "label": "Investigação de Sinais", "color": "green"},
        "quality_check": {"icon": "📊", "label": "Verificação de Qualidade", "color": "orange"},
        "decide": {"icon": "🧠", "label": "Decisão do Agente", "color": "violet"},
        "act": {"icon": "⚡", "label": "Ação de Impacto (HITL)", "color": "red"},
        "respond": {"icon": "💬", "label": "Resposta ao Cliente", "color": "green"},
        "escalate": {"icon": "🎫", "label": "Escalonamento para Humano", "color": "red"},
    }
    
    for i, step in enumerate(trace, 1):
        node = step.get("node", "unknown")
        config = node_config.get(node, {"icon": "⚙️", "label": node.upper(), "color": "gray"})
        
        with st.status(f"{config['icon']} Passo {i}: {config['label']}", expanded=False, state="complete"):
            cols = st.columns([1, 3])
            with cols[0]:
                st.markdown(f"**Nó:** `{node}`")
                if "verdict" in step:
                    st.markdown(f"**Veredito:** `{step['verdict'].upper()}`")
                if "decision" in step:
                    st.markdown(f"**Decisão:** `{step['decision'].upper()}`")
                if "action" in step:
                    st.markdown(f"**Ação:** `{step['action']}`")
            with cols[1]:
                details = []
                if "tools_called" in step:
                    details.append(f"🔧 Tools: {', '.join(step['tools_called'])}")
                if "gaps" in step and step["gaps"]:
                    gaps = step["gaps"]
                    if isinstance(gaps, dict):
                        details.append(f"⚠️ Gaps: {', '.join(gaps.keys())}")
                if "reason" in step:
                    details.append(f"💭 Razão: {step['reason']}")
                if "from_cache" in step:
                    details.append(f"⚡ Cache: {'Sim' if step['from_cache'] else 'Não'}")
                if details:
                    for d in details:
                        st.markdown(f"- {d}")
                else:
                    st.caption("—")


def tab_trace(result: Optional[Dict[str, Any]]):
    """Aba de visualização técnica."""
    if not result:
        st.info("Nenhum resultado disponível. Execute um ticket na barra lateral primeiro.")
        return

    render_visual_connected_graph(result)
    render_node_gap_inspector(result)
    st.markdown("<hr style='border-color:#2d3142; margin:20px 0;'>", unsafe_allow_html=True)
    
    # Corrigido: chamando a função correta render_trace_timeline
    render_trace_timeline(result)
    
    raw = result.get("raw", {})
    if raw:
        render_technical_signals(raw)




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
                st.line_chart(df_rms, width="stretch")
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
                st.bar_chart(df_peaks.set_index("freq_hz")["amplitude_mm_s"], width="stretch")
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
            split_choice = st.selectbox(
                "Conjunto de Avaliação",
                options=["train", "test", "derivados", "all"],
                index=0,
                help="`derivados` são cenários construídos neste projeto, sobre ativos que o "
                     "case original não usa. Reporte SEMPRE separado — um gabarito escrito por "
                     "quem escreveu o agente pode favorecê-lo sem intenção.",
            )
        with col_ctrl2:
            use_judge = st.checkbox("Executar Juiz LLM", value=False, help="Avalia qualidade e segurança da resposta com LLM.")
        with col_ctrl3:
            st.markdown("<div style='margin-top:24px;'></div>", unsafe_allow_html=True)
            if st.button("🚀 Executar Avaliação Batch", key="btn_run_eval_tab", width="stretch"):
                from eval.runner import run_all
                with st.spinner(f"Executando avaliação no split '{split_choice}'..."):
                    try:
                        out = run_all(split=split_choice, run_judge=use_judge)
                        out_path = _caminho_resultados(split_choice)
                        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
                        st.success("✅ Avaliação finalizada e salva com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro ao rodar avaliação: {e}")

        # Carrega arquivo de resultados existente
        target_path = _caminho_resultados(split_choice)
        if target_path.exists():
            eval_data = json.loads(target_path.read_text(encoding="utf-8"))
            summary = eval_data.get("summary", {})
            results = eval_data.get("results", [])

            # Métricas agregadas
            cols = st.columns(5)
            traj_avg = summary.get("trajectory_avg_score", 0.0)
            judge_avg = summary.get("judge_avg_score", 0.0)
            decisions = summary.get("decisions", {})
            acc = summary.get("decision_accuracy")
            hits = summary.get("decision_hits", "—")
            conserv = summary.get("erros_conservadores")
            arrisc = summary.get("erros_arriscados")

            # A ACURÁCIA vem primeiro. O `trajectory_avg_score` era o destaque e
            # é justamente a métrica que engana: 2 dos 4 pontos eram grátis, e ela
            # marcava 0,74 enquanto a acurácia real era 31%.
            metrics = [
                ("Acurácia de Decisão",
                 f"{acc:.0%} ({hits})" if isinstance(acc, (int, float)) else "—",
                 "#22c55e" if isinstance(acc, (int, float)) and acc >= 0.75 else "#f59e0b"),
                ("Erros Arriscados",
                 arrisc if arrisc is not None else "—",
                 "#22c55e" if arrisc == 0 else "#f87171"),
                ("Erros Conservadores", conserv if conserv is not None else "—", "#60a5fa"),
                ("Nota Juiz LLM", f"{judge_avg:.1f}/10" if judge_avg else "—",
                 "#22c55e" if judge_avg >= 7.0 else "#8892a0"),
                ("Distribuição",
                 f"Orient {decisions.get('orient',0)} · Act {decisions.get('act',0)} · Esc {decisions.get('escalate',0)}",
                 "#f59e0b"),
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
                traj = r.get("trajectory") if isinstance(r.get("trajectory"), dict) else {}
                juiz = r.get("judge") if isinstance(r.get("judge"), dict) else {}
                esperado = r.get("expected_decision")
                tipo = classificar_erro(esperado, r.get("decision"))
                # Um erro conservador e um arriscado não custam igual num agente
                # industrial — a tabela precisa distinguir os dois.
                veredicto = "✅ acerto" if esperado and not tipo else (
                    {"conservador": "🟦 conservador", "arriscado": "🟥 arriscado"}.get(tipo, "—"))
                modelo = next(
                    (s.get("modelo") for s in (r.get("trace") or [])
                     if isinstance(s, dict) and s.get("node") == "decide" and s.get("modelo")), "—")

                table_rows.append({
                    "Ticket": r.get("ticket_id", "—"),
                    "Esperado": esperado or "—",
                    "Decisão": f"{DECISION_ICONS.get(r.get('decision'), '⚪')} {r.get('decision', '—')}",
                    "Veredicto": veredicto,
                    "Qualidade": f"{QUALITY_ICONS.get(r.get('quality_verdict'), '⚪')} {r.get('quality_verdict', '—')}",
                    "Trajetória": traj.get("score", "—"),
                    "Nota Juiz": juiz.get("nota_geral", "—"),
                    "Modelo": modelo,
                })

            st.dataframe(pd.DataFrame(table_rows), width="stretch", hide_index=True)
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
                        st.dataframe(pd.DataFrame(comp_rows), width="stretch")
            else:
                st.info("Tabela `execucoes` conectada, mas ainda sem registros gravados. Execute tickets para registrar.")
        else:
            st.warning("⚠️ PostgreSQL não está acessível no momento. Para iniciar o banco e habilitar comparação de versões:")
            st.code("make postgres-up\nmake postgres-init", language="bash")


# ── Componentes de UI: Aba Playground (Ticket Customizado) ───────────────────
def _tempo_de_espera(criado_em) -> str:
    """Há quanto tempo a ação está congelada esperando decisão.

    Numa fila de manutenção o tempo de espera é informação operacional, não
    enfeite: uma ação de reprocessamento parada há dias significa que o ativo
    seguiu sendo monitorado com um modelo que o próprio agente considerou
    suspeito.
    """
    if not criado_em:
        return "—"
    agora = datetime.now(timezone.utc)
    delta = agora - (criado_em if criado_em.tzinfo else criado_em.replace(tzinfo=timezone.utc))
    segundos = int(delta.total_seconds())
    if segundos < 60:
        return f"{segundos}s"
    if segundos < 3600:
        return f"{segundos // 60}min"
    if segundos < 86400:
        return f"{segundos // 3600}h"
    return f"{segundos // 86400}d"


def _render_pendencia(p: dict, indice: int, cases: List[Dict[str, Any]]):
    """Um item da caixa de entrada, com o contexto necessário para decidir.

    O operador precisa de três coisas antes de autorizar uma escrita: o que o
    agente quer fazer, por quê, e o que ele admite não saber. As lacunas vêm em
    destaque justamente porque são o argumento contra aprovar no automático.
    """
    espera = _tempo_de_espera(p.get("criado_em"))
    titulo = (f"{p['ticket_id']} · {p.get('action_type') or 'ação'} "
              f"em {p.get('action_target') or '—'} · aguardando há {espera}")

    with st.expander(titulo, expanded=(indice == 0)):
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**Ativo**  \n`{p.get('asset_id') or '—'}`")
        c2.markdown(f"**Ação solicitada**  \n`{p.get('action_type') or '—'}`")
        c3.markdown(f"**Alvo**  \n`{p.get('action_target') or '—'}`")

        if p.get("justification"):
            st.markdown("**Justificativa do agente**")
            st.info(p["justification"])

        lacunas = p.get("gaps") or {}
        if lacunas:
            st.markdown(f"**Lacunas de dado reconhecidas ({len(lacunas)})**")
            st.warning(
                # Os valores chegam como lista (uma categoria pode acumular mais de
                # um motivo). Interpolar direto imprimiria o `repr` do Python —
                # colchetes e aspas — no meio de um texto que um operador vai ler.
                "\n".join(
                    f"- `{k}`: " + ("; ".join(str(x) for x in v) if isinstance(v, list) else str(v))
                    for k, v in lacunas.items()
                ),
                icon="⚠️",
            )
            st.caption(
                "O agente sabe que decidiu sem esses dados. É por isso que a ação "
                "para aqui em vez de ser executada."
            )
        else:
            st.caption("O agente não reportou lacunas de dado para esta decisão.")

        st.caption(f"`thread_id` = `{p['thread_id']}` — a chave do checkpoint que "
                   "será retomado.")

        col_ok, col_no, col_abrir = st.columns([1, 1, 1.4])
        chave = p["thread_id"]
        # Abrir o ticket leva ao diagnóstico completo: trace, sinais e o dossiê.
        # A fila mostra o suficiente para decidir o caso simples; o caso duvidoso
        # exige ver a investigação inteira, e obrigar o operador a procurar o
        # ticket na barra lateral é atrito sem propósito.
        if col_abrir.button("Abrir ticket ↗", key=f"abrir_{chave}"):
            if abrir_ticket(p["ticket_id"], cases):
                st.rerun()
            else:
                st.info(
                    f"`{p['ticket_id']}` é um cenário derivado e não está entre os "
                    "17 chamados oficiais da barra lateral. Ele pode ser aprovado "
                    "aqui, mas não tem página de diagnóstico.",
                    icon="ℹ️",
                )
        if col_ok.button("Aprovar e executar", type="primary", key=f"ok_{chave}"):
            with st.spinner("Executando a ação na plataforma..."):
                try:
                    resumed = resume_agent_action(p["ticket_id"], True, thread_id=chave)
                    st.session_state[f"result_{p['ticket_id']}"] = resumed
                    st.session_state[f"is_interrupted_{p['ticket_id']}"] = False
                except Exception as e:
                    st.error(f"Falha ao executar: {e}")
                    return
            st.success(f"Ação executada em {p['ticket_id']}.", icon="✓")
            st.rerun()

        if col_no.button("Recusar", key=f"no_{chave}"):
            with st.spinner("Cancelando..."):
                try:
                    resumed = resume_agent_action(p["ticket_id"], False, thread_id=chave)
                    st.session_state[f"result_{p['ticket_id']}"] = resumed
                    st.session_state[f"is_interrupted_{p['ticket_id']}"] = False
                except Exception as e:
                    st.error(f"Falha ao cancelar: {e}")
                    return
            st.info(f"Ação recusada em {p['ticket_id']}.", icon="🚫")
            st.rerun()


def _tabela_autonomia() -> pd.DataFrame:
    """Autonomia por conjunto, contada nas linhas de `execucoes` do Postgres.

    Sai do banco, e não de `eval/results-*.json`, porque a pergunta é sobre o
    que a plataforma processou — inclusive tickets sem gabarito, que arquivo de
    avaliação nenhum contém.
    """
    linhas = []
    for split, rotulo in (("train", "treino"), ("test", "teste held-out"),
                          ("derivados", "derivados"), ("avulso", "avulsos")):
        d = estatisticas_autonomia(AGENT_VERSION, split=split)
        if not d["total"]:
            continue
        linhas.append({
            "Conjunto": rotulo,
            "Tickets": d["total"],
            "Sem intervenção": d["autonomos"],
            "Exigiram humano": d["com_humano"],
            "Autonomia": f"{d['autonomos'] / d['total']:.0%}",
        })
    return pd.DataFrame(linhas)


def tab_notificacoes(cases: List[Dict[str, Any]]):
    """Caixa de entrada do operador: o que o agente quer fazer e ainda não fez.

    Toda a aba lê do Postgres. É o que permite que um ticket ingerido por
    `make demo` — outro processo, minutos antes — apareça aqui esperando
    decisão, e continue esperando depois de reiniciar a interface.
    """
    tipo_cp, motivo_cp = checkpointer_status()
    if tipo_cp != "postgres":
        st.error(
            f"**Checkpointer em memória** ({motivo_cp}). Ações pausadas morrem "
            "com este processo e não são visíveis para outros — a fila abaixo "
            "ficará vazia mesmo com tickets congelados.",
            icon="⚠️",
        )
        st.code("make postgres-up\nmake postgres-init", language="bash")

    pendentes = listar_pendencias(AGENT_VERSION)

    st.markdown("### Caixa de entrada")
    st.caption(
        "Cada item é uma execução congelada: o agente decidiu escrever na "
        "plataforma da Tractian e o grafo parou no `interrupt()` antes de fazê-lo. "
        "Nada é executado sem uma decisão aqui."
    )

    if pendentes:
        st.warning(
            f"**{len(pendentes)}** ação(ões) aguardando decisão humana.",
            icon="🔔",
        )
        for i, p in enumerate(pendentes):
            _render_pendencia(p, i, cases)
    else:
        st.success("Nenhuma ação pendente.", icon="✓")
        stats = estatisticas_autonomia(AGENT_VERSION)
        if not stats["total"]:
            st.info(
                "Nenhum ticket foi processado ainda. Rode a ingestão para a "
                "plataforma receber os chamados:",
                icon="💡",
            )
            st.code("make demo        # sobe tudo e ingere os tickets\n"
                    "make ingest      # só a ingestão, com a plataforma já de pé",
                    language="bash")
        else:
            st.caption(f"{stats['total']} ticket(s) processado(s), todos resolvidos "
                       "sem intervenção ou já decididos.")

    st.markdown("---")
    st.markdown("### Autonomia")
    st.caption(
        "`agir` é a única decisão que passa por confirmação — é a única que "
        "escreve na plataforma. `orientar` e `escalar` não alteram estado e "
        "correm de ponta a ponta."
    )

    df = _tabela_autonomia()
    if df.empty:
        st.info("Sem tickets processados nesta versão do agente.")
    else:
        geral = estatisticas_autonomia(AGENT_VERSION)
        c1, c2, c3 = st.columns(3)
        c1.metric("Tickets processados", geral["total"])
        c2.metric("Sem intervenção humana", geral["autonomos"],
                  f"{geral['autonomos'] / geral['total']:.0%}")
        c3.metric("Exigiram confirmação", geral["com_humano"],
                  f"{geral['com_humano'] / geral['total']:.0%}")
        st.dataframe(df, width="stretch", hide_index=True)

    # Acurácia sobre o que a própria plataforma processou. Responde "quantos
    # tickets passaram" sem depender dos arquivos de avaliação: a ingestão grava
    # a decisão esperada junto com a tomada, quando existe gabarito.
    tickets = listar_tickets(AGENT_VERSION)
    avaliados = [t for t in tickets if t.get("decisao_esperada")]
    if avaliados:
        acertos = [t for t in avaliados if t["decision"] == t["decisao_esperada"]]
        st.markdown("### Acerto de decisão nos tickets processados")
        c1, c2 = st.columns(2)
        c1.metric("Decisão correta", f"{len(acertos)}/{len(avaliados)}",
                  f"{len(acertos) / len(avaliados):.0%}")
        sem_humano = [t for t in avaliados if t["status"] != "aguardando_humano"]
        c2.metric("Concluídos sem humano", f"{len(sem_humano)}/{len(avaliados)}")
        st.dataframe(
            pd.DataFrame([{
                "Ticket": t["ticket_id"],
                "Conjunto": t.get("split") or "—",
                "Decidiu": t["decision"],
                "Esperado": t["decisao_esperada"],
                "OK": "✓" if t["decision"] == t["decisao_esperada"] else "✗",
                "Nota": f"{t['trajectory_score']:.2f}" if t.get("trajectory_score") is not None else "—",
                "Estado": t["status"],
            } for t in avaliados]),
            width="stretch", hide_index=True,
        )

    historico = historico_aprovacoes(limite=20)
    if historico:
        st.markdown("---")
        st.markdown("### Histórico de decisões humanas")
        st.caption("Quem autorizou o quê — o registro que uma ação com impacto "
                   "físico precisa deixar.")
        st.dataframe(
            pd.DataFrame([{
                "Ticket": h["ticket_id"],
                "Ação": h.get("action_type") or "—",
                "Alvo": h.get("action_target") or "—",
                "Decisão": h["status"],
                "Por": h.get("resolvido_por") or "—",
                # `.astimezone()` sem argumento converte para o fuso local; o
                # Postgres guarda em UTC.
                "Quando": h["resolvido_em"].astimezone().strftime("%d/%m %H:%M") if h.get("resolvido_em") else "—",
            } for h in historico]),
            width="stretch", hide_index=True,
        )


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
        render_response(res, c_case)


# ── Função Principal ─────────────────────────────────────────────────────────
def main():
    render_header()

    cases = load_cases()
    if not cases:
        st.error("Não foi possível carregar os casos de teste em `agent-input/cases.json`.")
        st.stop()

    # Antes de qualquer widget: é a única janela em que as chaves da barra
    # lateral e das abas ainda podem ser escritas (ver `abrir_ticket`).
    aplicar_navegacao(cases)

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

    # Recupera estado do ticket selecionado. Se esta sessão não executou o
    # ticket, busca no Postgres o que a ingestão já processou — é o que faz a
    # plataforma abrir com os tickets prontos em vez de pedir "Executar Agente".
    result = st.session_state.get(result_key)
    elapsed = st.session_state.get(elapsed_key)
    is_interrupted = st.session_state.get(interrupted_key, False)
    if result is None:
        result, is_interrupted = estado_do_banco(ticket_id)

    # Navegação. O contador de pendências sai do Postgres, então marca também o
    # que foi congelado por outro processo — a ingestão do `make demo`.
    try:
        pendentes_n = len(listar_pendencias(AGENT_VERSION))
    except Exception:
        pendentes_n = 0

    def _rotulo(aba: str) -> str:
        return {
            ABA_DIAGNOSTICO: "📋 Diagnóstico & HITL",
            ABA_NOTIFICACOES: (f"🔔 Notificações ({pendentes_n})" if pendentes_n
                               else "🔔 Notificações"),
            ABA_TRACE: "🔍 Trace & Sinais Técnicos",
            ABA_METRICAS: "📈 Métricas & Avaliação",
            ABA_PLAYGROUND: "🧪 Playground",
        }[aba]

    # `st.segmented_control` no lugar de `st.tabs` porque as abas nao aceitam
    # selecao programatica: escrever no `session_state` de um `st.tabs` com
    # `key` faz o widget sumir da tela e o valor voltar `None` (testado no
    # Streamlit 1.63). Sem isso, clicar numa notificacao nao consegue levar o
    # operador ao ticket. De quebra, so a secao ativa e renderizada — as abas
    # executavam o conteudo das cinco a cada interacao.
    if st.session_state.get(ABA_KEY) not in ABAS:
        st.session_state[ABA_KEY] = ABA_DIAGNOSTICO
    aba = st.segmented_control(
        "Navegação", ABAS, key=ABA_KEY, format_func=_rotulo,
        label_visibility="collapsed",
    ) or ABA_DIAGNOSTICO
    st.markdown("<hr style='margin:4px 0 14px 0; border:none; "
                "border-top:1px solid #1e2530;'>", unsafe_allow_html=True)

    if aba == ABA_DIAGNOSTICO:
        tab_diagnostico(selected_case, result, elapsed, is_interrupted)
    elif aba == ABA_NOTIFICACOES:
        tab_notificacoes(cases)
    elif aba == ABA_TRACE:
        tab_trace(result)
    elif aba == ABA_METRICAS:
        tab_metricas()
    elif aba == ABA_PLAYGROUND:
        tab_playground(cases)


if __name__ == "__main__":
    main()
