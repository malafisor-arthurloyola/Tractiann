"""Testes do agente industrial — grafo, rotas, quality_check, cache, ações.

Todos os testes rodam SEM chamar a LLM (mock) e SEM gastar token.
Foco na lógica pura: rotas do grafo, classificação de evidência, escolha de
evidência compensatória, validação de alvo de ação e cache de decisões.
"""
import pytest

from agent.graph.nodes import (
    AgentDecision,
    COMPENSATION,
    CORE_TOOLS,
    EMPTY_MODES,
    USABLE_MODES,
    _available_ids,
    ACTION_TOOLS,
    _build_action_call,
    _cache_key,
    _extract_analyses_list,
    _first_analysis_id,
    _knowledge_query,
    _next_compensation,
    _validate_action,
    quality_check,
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


def _complete_raw(**overrides):
    raw = {
        "asset_info": _envelope("complete", {"id": "asset_M101", "machine_type": "motor_induction"}),
        "baseline": _envelope("complete", {"state": "established"}),
        "analyses": _envelope("complete", {"analyses": [{"id": "an_1"}]}),
        "rms": _envelope("complete", {"samples": []}),
        "spectrum": _envelope("complete", {"fft": []}),
        "data_quality": _envelope("complete", {"freshness_minutes": 10}),
    }
    raw.update(overrides)
    return raw


# ---- Tests: route_after_quality ----

class TestRouteAfterQuality:
    """O quality_check não é mais porteiro: nenhum veredicto manda para escalate.

    O roteamento depende só de haver evidência compensatória pendente e
    orçamento de rodadas.
    """

    def test_sem_next_tool_vai_para_decide(self):
        assert route_after_quality(_make_state(quality_verdict="ok")) == "decide"

    def test_unavailable_ainda_vai_para_decide(self):
        # Antes o `unavailable` era curto-circuitado num escalate hardcoded.
        s = _make_state(quality_verdict="unavailable", next_tool=None)
        assert route_after_quality(s) == "decide"

    def test_next_tool_volta_para_investigate(self):
        s = _make_state(quality_verdict="incomplete", next_tool="model",
                        tools_called=list(CORE_TOOLS))
        assert route_after_quality(s) == "investigate"

    def test_partial_tambem_busca_compensacao(self):
        s = _make_state(quality_verdict="partial", next_tool="knowledge",
                        tools_called=list(CORE_TOOLS))
        assert route_after_quality(s) == "investigate"

    def test_orcamento_de_rodadas_esgotado_vai_para_decide(self):
        s = _make_state(
            quality_verdict="incomplete", next_tool="knowledge",
            tools_called=list(CORE_TOOLS) + ["model", "analysis_detail", "knowledge"],
        )
        assert route_after_quality(s) == "decide"

    def test_core_count_acompanha_core_tools(self):
        assert _core_count() == len(CORE_TOOLS)


# ---- Tests: route_after_decide ----

class TestRouteAfterDecide:

    def test_orient_routes_respond(self):
        assert route_after_decide(_make_state(decision="orient")) == "respond"

    def test_act_routes_act(self):
        assert route_after_decide(_make_state(decision="act")) == "act"

    def test_escalate_routes_escalate(self):
        assert route_after_decide(_make_state(decision="escalate")) == "escalate"


# ---- Tests: classificação de evidência ----

class TestClassificacaoDeModos:
    """`conflict` e `partial` preservam o payload; só os outros dois o esvaziam."""

    def test_conflict_e_partial_sao_utilizaveis(self):
        assert "conflict" in USABLE_MODES
        assert "partial" in USABLE_MODES
        assert "complete" in USABLE_MODES

    def test_inconclusive_e_unavailable_sao_vazios(self):
        assert EMPTY_MODES == {"inconclusive", "unavailable"}


class TestQualityCheck:

    def test_tudo_completo_da_ok(self):
        r = quality_check(_make_state(raw=_complete_raw()))
        assert r["quality_verdict"] == "ok"
        assert r["data_gaps"] == {}
        assert r["next_tool"] is None

    def test_conflict_em_analyses_nao_bloqueia(self):
        """O caso que mais custava: `conflict` traz o payload inteiro.

        A versão anterior declarava `unavailable` e escalava, jogando fora a
        evidência mais rica do case.
        """
        raw = _complete_raw(
            analyses=_envelope("conflict", {"analyses": [{"id": "an_1"}, {"id": "an_2"}]})
        )
        r = quality_check(_make_state(raw=raw))
        assert r["quality_verdict"] == "partial"
        assert "analyses" in r["data_gaps"]
        assert "conflict" in r["data_gaps"]["analyses"][0]

    def test_baseline_partial_nao_bloqueia(self):
        # `partial` no baseline só omite `features`; o `state` continua lá.
        raw = _complete_raw(baseline=_envelope("partial", {"state": "established"}))
        r = quality_check(_make_state(raw=raw))
        assert r["quality_verdict"] == "partial"

    def test_baseline_vazio_da_incomplete_nao_unavailable(self):
        raw = _complete_raw(baseline=_envelope("unavailable"))
        r = quality_check(_make_state(raw=raw))
        assert r["quality_verdict"] == "incomplete"
        assert "baseline" in r["data_gaps"]

    def test_unavailable_so_quando_nada_e_utilizavel(self):
        raw = {
            "baseline": _envelope("unavailable"),
            "analyses": _envelope("inconclusive"),
            "rms": _envelope("unavailable"),
        }
        r = quality_check(_make_state(raw=raw))
        assert r["quality_verdict"] == "unavailable"

    def test_analises_vazias_contam_como_ausencia(self):
        raw = _complete_raw(analyses=_envelope("complete", {"analyses": []}))
        r = quality_check(_make_state(raw=raw))
        assert r["quality_verdict"] == "incomplete"
        assert "analyses" in r["data_gaps"]

    def test_sugere_compensacao_quando_ha_lacuna(self):
        raw = _complete_raw(baseline=_envelope("unavailable"))
        s = _make_state(raw=raw, tools_called=list(CORE_TOOLS))
        r = quality_check(s)
        assert r["next_tool"] in COMPENSATION["baseline"]


# ---- Tests: evidência compensatória ----

class TestCompensacao:

    def test_baseline_vazio_busca_modelo(self):
        raw = _complete_raw(baseline=_envelope("unavailable"))
        assert _next_compensation(raw, list(CORE_TOOLS)) == "model"

    def test_nao_repete_tool_ja_chamada(self):
        raw = _complete_raw(baseline=_envelope("unavailable"))
        seguinte = _next_compensation(raw, list(CORE_TOOLS) + ["model"])
        assert seguinte != "model"
        assert seguinte in COMPENSATION["baseline"]

    def test_sem_lacuna_nao_ha_compensacao(self):
        assert _next_compensation(_complete_raw(), list(CORE_TOOLS)) is None

    def test_esgota_candidatos_e_devolve_none(self):
        raw = {"baseline": _envelope("unavailable")}
        tried = list(CORE_TOOLS) + COMPENSATION["baseline"]
        assert _next_compensation(raw, tried) is None


class TestKnowledgeQuery:
    """A busca é `contains` da query inteira: só termo curto casa."""

    def test_termo_de_rolamento(self):
        assert _knowledge_query("Troquei o rolamento da bomba") == "rolamento"

    def test_termo_de_limiar_rms(self):
        assert _knowledge_query("A partir de qual valor de RMS é alarme?") == "rms"

    def test_termo_eletrico(self):
        assert _knowledge_query("Pode ser problema elétrico?") == "eletric"

    def test_default_quando_nada_casa(self):
        assert _knowledge_query("mensagem sem termo de dominio") == "baseline"

    def test_nunca_devolve_asset_id(self):
        # A versão anterior buscava "manutenção {asset_id}", que nunca dava match.
        q = _knowledge_query("problema no asset_V301")
        assert "asset_" not in q


# ---- Tests: validação do alvo da ação ----

class TestValidateAction:
    """Structured output impede prosa no lugar da decisão, mas não impede o
    modelo de citar um id inexistente. Aqui o alvo é conferido."""

    def _state_com_analises(self):
        return _make_state(raw=_complete_raw(
            analyses=_envelope("complete", {"analyses": [{"id": "an_9903"}, {"id": "an_9904"}]}),
            model=_envelope("complete", {"id": "mdl_vib_v3"}),
        ))

    def _decisao(self, **kw):
        base = dict(decision="act", action_type="reprocess", action_target="an_9903",
                    justification="j" * 25, customer_message="msg")
        base.update(kw)
        return AgentDecision(**base)

    def test_alvo_valido_e_preservado(self):
        t, alvo = _validate_action(self._decisao(), self._state_com_analises())
        assert (t, alvo) == ("reprocess", "an_9903")

    def test_id_alucinado_cai_para_analise_real(self):
        d = self._decisao(action_target="an_INEXISTENTE")
        t, alvo = _validate_action(d, self._state_com_analises())
        assert (t, alvo) == ("reprocess", "an_9903")

    def test_sem_analise_a_acao_e_cancelada(self):
        d = self._decisao()
        s = _make_state(raw=_complete_raw(analyses=_envelope("unavailable")))
        assert _validate_action(d, s) == (None, None)

    def test_update_config_sempre_mira_o_ativo(self):
        d = self._decisao(action_type="update_config", action_target="qualquer_coisa")
        t, alvo = _validate_action(d, self._state_com_analises())
        assert (t, alvo) == ("update_config", "asset_M101")

    def test_retrain_mira_o_modelo_conhecido(self):
        d = self._decisao(action_type="retrain", action_target="mdl_errado")
        t, alvo = _validate_action(d, self._state_com_analises())
        assert (t, alvo) == ("retrain", "mdl_vib_v3")

    def test_orient_nao_produz_acao(self):
        d = self._decisao(decision="orient", action_type=None, action_target=None)
        assert _validate_action(d, self._state_com_analises()) == (None, None)


class TestAvailableIds:

    def test_lista_ids_de_analises(self):
        s = _make_state(raw=_complete_raw(
            analyses=_envelope("complete", {"analyses": [{"id": "an_1"}, {"id": "an_2"}]})
        ))
        assert _available_ids(s)["analysis_ids"] == ["an_1", "an_2"]

    def test_asset_id_vem_do_estado(self):
        assert _available_ids(_make_state())["asset_id"] == "asset_M101"


# ---- Tests: ações via tools MCP ----

class TestBuildActionCall:
    """Os nós não montam URL: escolhem a tool MCP e o parâmetro do alvo."""

    def test_reprocess(self):
        assert _build_action_call("reprocess", "an_1") == ("reprocessAnalysis", {"analysisId": "an_1"})

    def test_specialist(self):
        assert _build_action_call("specialist", "an_1") == ("requestSpecialistAnalysis", {"analysisId": "an_1"})

    def test_retrain(self):
        assert _build_action_call("retrain", "mdl_1") == ("requestRetraining", {"modelId": "mdl_1"})

    def test_update_config(self):
        assert _build_action_call("update_config", "asset_1") == ("updateAssetConfig", {"assetId": "asset_1"})

    def test_escalate(self):
        assert _build_action_call("escalate", "case_1") == ("escalateCase", {"caseId": "case_1"})

    def test_acao_desconhecida_cai_para_escalate(self):
        assert _build_action_call("inexistente", "case_1")[0] == "escalateCase"

    def test_toda_acao_do_modelo_tem_tool(self):
        """Cada action_type que o AgentDecision aceita precisa de uma tool MCP."""
        from typing import get_args
        aceitos = {a for a in get_args(AgentDecision.model_fields["action_type"].annotation) if isinstance(a, str)}
        assert aceitos <= set(ACTION_TOOLS), f"sem tool MCP: {aceitos - set(ACTION_TOOLS)}"


# ---- Tests: cache ----

class TestCacheKey:

    def test_same_version_same_key(self):
        assert _cache_key("contexto") == _cache_key("contexto")

    def test_different_context_different_key(self):
        assert _cache_key("contexto A") != _cache_key("contexto B")

    def test_version_change_invalidates_key(self):
        import agent.version as v
        original = v.AGENT_VERSION
        try:
            k1 = _cache_key("mesmo contexto")
            v.AGENT_VERSION = "v-outra"
            k2 = _cache_key("mesmo contexto")
            assert k1 != k2
        finally:
            v.AGENT_VERSION = original


# ---- Tests: helpers de extração ----

class TestExtractHelpers:

    def test_extract_analyses_list_empty(self):
        assert _extract_analyses_list({"data": {}}) == []

    def test_extract_analyses_list_with_data(self):
        env = {"data": {"analyses": [{"id": "a1"}]}}
        assert _extract_analyses_list(env) == [{"id": "a1"}]

    def test_extract_analyses_list_envelope_invalido(self):
        assert _extract_analyses_list(None) == []

    def test_first_analysis_id(self):
        raw = {"analyses": {"data": {"analyses": [{"id": "an_7"}, {"id": "an_8"}]}}}
        assert _first_analysis_id(raw) == "an_7"

    def test_first_analysis_id_empty(self):
        assert _first_analysis_id({"analyses": {"data": {"analyses": []}}}) is None


# ---- Tests: contrato do estado ----

class TestStateFields:

    def test_agent_state_has_action_fields(self):
        from agent.graph.state import AgentState
        for campo in ("action_type", "action_target", "decision_justification"):
            assert campo in AgentState.__annotations__

    def test_agent_state_has_tools_called(self):
        from agent.graph.state import AgentState
        assert "tools_called" in AgentState.__annotations__

    def test_asset_info_esta_no_nucleo(self):
        """Sem `GET /assets/{id}` não há frequências características e o
        espectro fica ininterpretável."""
        assert "asset_info" in CORE_TOOLS


# ---- Tests: camada MCP ----

class TestMCPEnvelope:
    """Conversão do retorno de uma tool MCP no envelope da API.

    Testa só a desserialização — não sobe o servidor nem exige a API no ar.
    """

    def _resultado(self, *, structured=None, textos=(), erro=False):
        class _Item:
            def __init__(self, text): self.text = text

        class _Resultado:
            structuredContent = structured
            content = [_Item(t) for t in textos]
            isError = erro

        return _Resultado()

    def test_structured_content_tem_prioridade(self):
        from agent.tools.mcp_client import _extrair_envelope
        r = self._resultado(structured={"mode": "complete", "data": {"state": "established"}})
        assert _extrair_envelope(r)["mode"] == "complete"

    def test_desembrulha_result_do_sdk(self):
        # O SDK embrulha retornos não-objeto em {"result": ...}
        from agent.tools.mcp_client import _extrair_envelope
        r = self._resultado(structured={"result": {"mode": "partial"}})
        assert _extrair_envelope(r)["mode"] == "partial"

    def test_cai_para_json_em_texto(self):
        from agent.tools.mcp_client import _extrair_envelope
        r = self._resultado(textos=['{"mode": "conflict", "data": {}}'])
        assert _extrair_envelope(r)["mode"] == "conflict"

    def test_texto_nao_json_vira_unavailable(self):
        from agent.tools.mcp_client import _extrair_envelope
        env = _extrair_envelope(self._resultado(textos=["explodiu"]))
        assert env["mode"] == "unavailable"
        assert "explodiu" in env["notes"]

    def test_sem_conteudo_vira_unavailable(self):
        from agent.tools.mcp_client import _extrair_envelope
        assert _extrair_envelope(self._resultado())["mode"] == "unavailable"


class TestMCPServerRegistro:
    """O servidor MCP precisa expor toda operação que o agente invoca."""

    def test_todas_as_tools_de_acao_existem_no_servidor(self):
        import agent.tools.mcp_server as servidor
        registradas = {
            nome for nome in dir(servidor)
            if not nome.startswith("_") and callable(getattr(servidor, nome, None))
        }
        for tool, _param in ACTION_TOOLS.values():
            assert tool in registradas, f"tool de ação ausente no servidor MCP: {tool}"

    def test_tem_bloco_main(self):
        """Sem `__main__`, `python -m agent.tools.mcp_server` encerra sem subir
        servidor — e o cliente stdio falha com erro de TaskGroup."""
        from pathlib import Path
        fonte = Path("agent/tools/mcp_server.py").read_text(encoding="utf-8")
        assert '__name__ == "__main__"' in fonte
        assert 'mcp.run(transport="stdio")' in fonte


# ---- Tests: curadoria do balanço de evidência ----

class TestResumoRms:
    """A comparação com o limiar é feita em Python, não pelo LLM.

    O juiz flagrou o agente afirmando "valores de vibração acima dos limites"
    num ticket onde isso era falso. Entregar 30 amostras cruas e esperar
    aritmética correta é convite à alucinação.
    """

    def _serie(self, valores, limiar=1.8):
        return {
            "unit": "mm/s", "baseline_reference": 1.2, "baseline_state": "established",
            "alarm_threshold": limiar,
            "samples": [{"ts": f"t{i}", "value": v} for i, v in enumerate(valores)],
        }

    def test_detecta_que_nao_ultrapassou(self):
        from agent.graph.nodes import _resumir_rms
        r = _resumir_rms(self._serie([1.1, 1.2, 1.09]))
        assert r["ultrapassou_limiar"] is False
        assert r["n_amostras_acima_do_limiar"] == 0

    def test_detecta_que_ultrapassou(self):
        from agent.graph.nodes import _resumir_rms
        r = _resumir_rms(self._serie([1.1, 2.4, 1.9]))
        assert r["ultrapassou_limiar"] is True
        assert r["n_amostras_acima_do_limiar"] == 2
        assert r["ultimo_acima_do_limiar"] is True

    def test_tendencia_subindo(self):
        from agent.graph.nodes import _resumir_rms
        assert _resumir_rms(self._serie([1.0, 1.2, 1.5]))["tendencia"] == "subindo"

    def test_tendencia_estavel(self):
        from agent.graph.nodes import _resumir_rms
        assert _resumir_rms(self._serie([1.0, 1.01, 1.02]))["tendencia"] == "estavel"

    def test_tendencia_caindo(self):
        from agent.graph.nodes import _resumir_rms
        assert _resumir_rms(self._serie([1.5, 1.2, 0.9]))["tendencia"] == "caindo"

    def test_serie_vazia_nao_quebra(self):
        from agent.graph.nodes import _resumir_rms
        r = _resumir_rms({"alarm_threshold": 1.8, "samples": []})
        assert r["n_amostras"] == 0
        assert "observacao" in r

    def test_sem_limiar_nao_inventa_comparacao(self):
        from agent.graph.nodes import _resumir_rms
        r = _resumir_rms({"samples": [{"value": 1.0}]})
        assert "ultrapassou_limiar" not in r

    def test_nao_carrega_as_amostras_cruas(self):
        """O ponto da curadoria: as 30 amostras não vão para o prompt."""
        from agent.graph.nodes import _resumir_rms
        assert "samples" not in _resumir_rms(self._serie([1.0] * 30))


class TestCuradoriaEvidencia:

    def test_baseline_mantem_o_que_decide(self):
        from agent.graph.nodes import _resumir_evidencia
        r = _resumir_evidencia("baseline", {
            "id": "bs_1", "state": "invalidated", "detection_mode": "baseline",
            "learnable": True, "invalidation_reason": "maintenance_intervention",
            "established_at": "2025-12-27", "features": [{"reference": 1.2}],
        })
        assert r["state"] == "invalidated"
        assert r["invalidation_reason"] == "maintenance_intervention"

    def test_spectrum_preserva_os_picos(self):
        from agent.graph.nodes import _resumir_evidencia
        picos = [{"freq_hz": 200, "amplitude_mm_s": 1.6, "note": "1x"}]
        r = _resumir_evidencia("spectrum", {"peaks": picos, "asset_id": "a1"})
        assert r["peaks"] == picos

    def test_asset_info_descarta_frequencias_nulas(self):
        from agent.graph.nodes import _resumir_evidencia
        r = _resumir_evidencia("asset_info", {
            "id": "asset_M102", "machine_type": "motor_dc", "rotation_rpm": 1200,
            "bpfo_hz": None, "bpfi_hz": None, "sensor_status": "online",
        })
        assert "bpfo_hz" not in r
        assert r["machine_type"] == "motor_dc"

    def test_model_mantem_processing_state(self):
        from agent.graph.nodes import _resumir_evidencia
        r = _resumir_evidencia("model", {"id": "mdl_vib_v3", "processing_state": "delayed",
                                         "coverage": [], "outro": None})
        assert r["processing_state"] == "delayed"
        assert "outro" not in r

    def test_payload_nao_dict_passa_intacto(self):
        from agent.graph.nodes import _resumir_evidencia
        assert _resumir_evidencia("rms", None) is None
