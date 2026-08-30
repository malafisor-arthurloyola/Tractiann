"""Testes do agente industrial — grafo, rotas, quality_check, cache, ações.

Todos os testes rodam SEM chamar a LLM (mock) e SEM gastar token.
Foco na lógica pura: rotas do grafo, quality_check, cache de decisões,
extração de ação, e chamadas HTTP (mockadas).
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from pathlib import Path

from agent.graph.nodes import (
    quality_check, _extract_action, _extract_first_analysis_id,
    _find_model_id, _build_action_url, _cache_key, _CACHE_DIR,
    _extract_analyses_list,
)
from agent.graph.agent import route_after_quality, route_after_decide, _core_count


# ---- Helpers de fixture ----

def _make_state(**overrides):
    base = {
        "ticket_id": "T1", "case_id": "c1", "company_id": "co1",
        "user_id": "usr_ana", "asset_id": "asset_M101", "message": "teste",
        "raw": {}, "quality_verdict": None, "quality_notes": None,
        "data_gaps": {}, "next_tool": None, "tools_called": [],
        "decision": None, "decision_justification": None,
        "action_type": None, "action_target": None,
        "response": None, "trace": [],
    }
    base.update(overrides)
    return base


def _envelope(mode, data=None, notes=None):
    return {"mode": mode, "notes": notes, "data": data or {}}


# ---- Tests: route_after_quality ----

class TestRouteAfterQuality:

    def test_ok_routes_to_decide(self):
        s = _make_state(quality_verdict="ok")
        assert route_after_quality(s) == "decide"

    def test_partial_routes_to_decide(self):
        s = _make_state(quality_verdict="partial")
        assert route_after_quality(s) == "decide"

    def test_unavailable_routes_to_decide(self):
        """unavailable AGORA vai para decide (fix do bug anterior)."""
        s = _make_state(quality_verdict="unavailable")
        assert route_after_quality(s) == "decide"

    def test_incomplete_with_next_tool_routes_investigate(self):
        s = _make_state(quality_verdict="incomplete", next_tool="knowledge",
                        tools_called=["baseline", "analyses", "rms", "spectrum", "data_quality"])
        assert route_after_quality(s) == "investigate"

    def test_incomplete_without_next_tool_routes_decide(self):
        s = _make_state(quality_verdict="incomplete", next_tool=None)
        assert route_after_quality(s) == "decide"

    def test_incomplete_exceeds_retry_budget_routes_decide(self):
        """Após MAX_RETRIES retries, deve ir para decide mesmo com next_tool."""
        s = _make_state(
            quality_verdict="incomplete", next_tool="knowledge",
            tools_called=["baseline", "analyses", "rms", "spectrum", "data_quality",
                          "knowledge", "knowledge", "knowledge"]  # 8 tools (5 core + 3)
        )
        assert route_after_quality(s) == "decide"


# ---- Tests: route_after_decide ----

class TestRouteAfterDecide:

    def test_orient_routes_respond(self):
        s = _make_state(decision="orient")
        assert route_after_decide(s) == "respond"

    def test_act_routes_act(self):
        s = _make_state(decision="act")
        assert route_after_decide(s) == "act"

    def test_escalate_routes_escalate(self):
        s = _make_state(decision="escalate")
        assert route_after_decide(s) == "escalate"


# ---- Tests: quality_check ----

class TestQualityCheck:

    def test_all_complete_gives_ok(self):
        raw = {
            "baseline": _envelope("complete", {"state": "established"}),
            "analyses": _envelope("complete", {"analyses": [{"id": "a1"}]}),
            "rms": _envelope("complete", {"samples": []}),
            "spectrum": _envelope("complete", {"fft": []}),
            "data_quality": _envelope("complete", {"freshness": 10}),
        }
        s = _make_state(raw=raw)
        r = quality_check(s)
        assert r["quality_verdict"] == "ok"
        assert r["data_gaps"] == {}

    def test_baseline_unavailable_gives_unavailable(self):
        raw = {
            "baseline": _envelope("unavailable"),
            "analyses": _envelope("complete", {"analyses": [{"id": "a1"}]}),
        }
        s = _make_state(raw=raw)
        r = quality_check(s)
        assert r["quality_verdict"] == "unavailable"
        assert "baseline" in r["data_gaps"]

    def test_analyses_empty_gives_incomplete(self):
        raw = {
            "baseline": _envelope("complete"),
            "analyses": _envelope("complete", {"analyses": []}),
        }
        s = _make_state(raw=raw)
        r = quality_check(s)
        assert r["quality_verdict"] == "incomplete"
        assert "analyses" in r["data_gaps"]

    def test_rms_partial_gives_partial(self):
        raw = {
            "baseline": _envelope("complete"),
            "analyses": _envelope("complete", {"analyses": [{"id": "a1"}]}),
            "rms": _envelope("partial"),
        }
        s = _make_state(raw=raw)
        r = quality_check(s)
        assert r["quality_verdict"] == "partial"
        assert "rms" in r["data_gaps"]

    def test_suggests_backup_tool_when_incomplete(self):
        raw = {
            "baseline": _envelope("complete"),
            "analyses": _envelope("complete", {"analyses": []}),
        }
        s = _make_state(raw=raw, tools_called=["baseline", "analyses", "rms", "spectrum", "data_quality"])
        r = quality_check(s)
        assert r["next_tool"] == "knowledge"


# ---- Tests: action extraction ----

class TestExtractAction:

    def test_reprocess_from_keywords(self):
        state = _make_state(raw={
            "analyses": _envelope("complete", {"analyses": [{"id": "an_9906"}]}),
        })
        t, target = _extract_action("Precisamos reprocessar a análise para atualizar.", state)
        assert t == "reprocess"
        assert target == "an_9906"

    def test_specialist_from_keywords(self):
        state = _make_state(raw={
            "analyses": _envelope("complete", {"analyses": [{"id": "an_9902"}]}),
        })
        t, target = _extract_action("Solicitar análise especialista.", state)
        assert t == "specialist"
        assert target == "an_9902"

    def test_retrain_from_keywords(self):
        state = _make_state(raw={})
        t, target = _extract_action("Solicitar retreinamento do modelo.", state)
        assert t == "retrain"
        assert target == "mdl_vib_v3"  # fallback

    def test_config_from_keywords(self):
        state = _make_state(asset_id="asset_V301")
        t, target = _extract_action("Alterar configuração criticidade.", state)
        assert t == "update_config"
        assert target == "asset_V301"


# ---- Tests: action URL building ----

class TestBuildActionUrl:

    def test_reprocess(self):
        assert _build_action_url("reprocess", "an_9906") == ("POST", "/analyses/an_9906/reprocess")

    def test_specialist(self):
        assert _build_action_url("specialist", "an_9902") == ("POST", "/analyses/an_9902/request-specialist")

    def test_retrain(self):
        assert _build_action_url("retrain", "mdl_vib_v3") == ("POST", "/models/mdl_vib_v3/request-retraining")

    def test_update_config(self):
        assert _build_action_url("update_config", "asset_V301") == ("PATCH", "/assets/asset_V301")

    def test_escalate(self):
        assert _build_action_url("escalate", "case_123") == ("POST", "/cases/case_123/escalate")


# ---- Tests: cache key invalidation ----

class TestCacheKey:

    def test_same_version_same_key(self):
        from agent.version import AGENT_VERSION
        k1 = _cache_key("context_a")
        k2 = _cache_key("context_a")
        assert k1 == k2

    def test_different_context_different_key(self):
        k1 = _cache_key("context_a")
        k2 = _cache_key("context_b")
        assert k1 != k2

    def test_version_change_invalidates_key(self):
        import agent.version as v
        old = v.AGENT_VERSION
        k1 = _cache_key("context_a")
        v.AGENT_VERSION = "v-test-invalid"
        k2 = _cache_key("context_a")
        v.AGENT_VERSION = old
        assert k1 != k2


# ---- Tests: extract helpers ----

class TestExtractHelpers:

    def test_extract_analyses_list_empty(self):
        assert _extract_analyses_list({}) == []
        assert _extract_analyses_list(None) == []

    def test_extract_analyses_list_with_data(self):
        env = {"data": {"analyses": [{"id": "a1"}, {"id": "a2"}]}}
        result = _extract_analyses_list(env)
        assert len(result) == 2
        assert result[0]["id"] == "a1"

    def test_extract_first_analysis_id(self):
        raw = {"analyses": {"data": {"analyses": [{"id": "an_9906"}, {"id": "an_9907"}]}}}
        assert _extract_first_analysis_id(raw) == "an_9906"

    def test_extract_first_analysis_id_empty(self):
        assert _extract_first_analysis_id({}) is None


# ---- Tests: state fields ----

class TestStateFields:

    def test_agent_state_has_action_fields(self):
        from agent.graph.state import AgentState
        hints = AgentState.__annotations__
        assert "action_type" in hints
        assert "action_target" in hints

    def test_agent_state_has_tools_called(self):
        from agent.graph.state import AgentState
        assert "tools_called" in AgentState.__annotations__
