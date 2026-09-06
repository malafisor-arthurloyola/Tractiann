"""Assertions determinísticas: compara a trajetória do agente com o gabarito.

Pesos (total 4.0):
    decisão correta ....... 2.0   dominante — é o que "resolver o ticket" significa
    cobertura de tools .... 1.0   proporcional às categorias de GET do gabarito
    honestidade dos gaps .. 1.0   guard-rail: só pontua se for coerente com o veredicto

A versão anterior dava 1.0 só por o agente ter produzido um `quality_verdict` e
1.0 por qualquer `data_gaps` não-vazio. Com 2 dos 4 pontos garantidos, um agente
que errasse TODAS as decisões ainda tirava 0.5 — e a média ficava presa em 0.74
enquanto a acurácia real era de 31%.
"""
from pathlib import Path
import json


def load_expected_paths() -> list:
    """Carrega o gabarito de trajetórias esperadas (lista de casos)."""
    path = Path(__file__).resolve().parent.parent / "expected-paths.json"
    return json.loads(path.read_text(encoding="utf-8"))


def expected_decision(expected: dict) -> str | None:
    """Deriva a decisão esperada do último passo do gabarito.

    Um `expected_path` que termina em POST /escalate espera `escalate`; que
    termina em reprocess/retrain/specialist espera `act`; qualquer outro
    (termina em GET) espera `orient`.
    """
    path = expected.get("expected_path", [])
    if not path:
        return None
    last = path[-1].get("step", "")
    if "escalate" in last:
        return "escalate"
    # Casa sem exigir a barra: os endpoints reais são `request-specialist` e
    # `request-retraining`, então procurar "/specialist" e "/retrain" não
    # encontrava nada e rotulava esses casos como `orient` por engano.
    if any(k in last for k in ("reprocess", "retrain", "specialist")):
        return "act"
    if last.startswith("PATCH"):
        return "act"
    return "orient"


# Escada de consequência da decisão, do mais seguro ao mais arriscado.
# `escalate` não afirma nem altera nada; `orient` faz uma afirmação técnica sobre
# uma máquina; `act` altera estado na plataforma.
CONSEQUENCIA = {"escalate": 0, "orient": 1, "act": 2}


def classificar_erro(esperado: str | None, real: str | None) -> str | None:
    """Classifica um erro de decisão como conservador ou arriscado.

    Num contexto industrial os dois erros não custam igual. Orientar errado sobre
    uma máquina em falha custa mais caro que ocupar um engenheiro com um caso que
    talvez desse para resolver remotamente. O gabarito trata todo desvio como
    erro de mesmo peso; esta função separa os dois lados.

    Returns:
        None se acertou, "conservador" se decidiu algo MENOS consequente que o
        esperado, "arriscado" se decidiu algo MAIS consequente.
    """
    if not esperado or not real or esperado == real:
        return None
    if esperado not in CONSEQUENCIA or real not in CONSEQUENCIA:
        return None
    return "arriscado" if CONSEQUENCIA[real] > CONSEQUENCIA[esperado] else "conservador"


def _expected_api_categories(expected: dict) -> set:
    """Extrai as categorias de GET esperadas do gabarito."""
    cats = set()
    for item in expected.get("expected_path", []):
        step = item.get("step", "")
        if not step.startswith("GET"):
            continue
        if "/baseline" in step: cats.add("baseline")
        elif "/analyses" in step: cats.add("analyses")
        elif "/rms" in step: cats.add("rms")
        elif "/spectrum" in step: cats.add("spectrum")
        elif "/data-quality" in step: cats.add("data_quality")
        elif "/knowledge" in step: cats.add("knowledge")
        elif "/models" in step: cats.add("model")
        elif "/assets" in step: cats.add("asset_info")
    return cats


def _expected_actions(expected: dict) -> set:
    """Extrai ações POST/PATCH esperadas do gabarito."""
    actions = set()
    for item in expected.get("expected_path", []):
        step = item.get("step", "")
        if step.startswith("POST") or step.startswith("PATCH"):
            if "/escalate" in step: actions.add("escalate")
            elif "/reprocess" in step: actions.add("reprocess")
            elif "/retrain" in step: actions.add("retrain")
            elif "/specialist" in step: actions.add("specialist")
            elif "/config" in step: actions.add("update_config")
            else: actions.add("unknown_action")
    return actions


def _tools_actually_called(result: dict) -> set:
    """Todas as tools chamadas, somando TODAS as passadas de investigação.

    A versão anterior lia só o primeiro passo `investigate` e dava `break`,
    ignorando as rodadas de evidência compensatória.
    """
    called = set()
    for step in result.get("trace", []):
        if isinstance(step, dict) and step.get("node") == "investigate":
            called.update(step.get("tools_called") or [])
    # `analysis_detail` é um GET /analyses/{id}: conta como cobertura de análises.
    if "analysis_detail" in called:
        called.add("analyses")
    return called


def assert_trajectory(result: dict, expected: dict) -> dict:
    """Compara a trajetória real com a esperada.

    Args:
        result: estado final do grafo (trace, decision, quality_verdict, data_gaps)
        expected: entrada do gabarito (expected_path, mode)

    Returns:
        dict com passed (bool), score (0-1), decision_ok (bool), details (list[str])
    """
    details = []
    total = 4.0
    score = 0.0

    # 1. Decisão esperada vs real — peso 2.0
    exp_decision = expected_decision(expected)
    real_decision = result.get("decision")
    decision_ok = bool(exp_decision) and exp_decision == real_decision
    if exp_decision and real_decision:
        if decision_ok:
            score += 2.0
            details.append(f"decisao: OK ({real_decision})")
        else:
            details.append(f"decisao: FALHOU (esperado={exp_decision}, real={real_decision})")
    elif exp_decision:
        details.append("decisao: FALHOU (agente não retornou decisão)")
    else:
        details.append("decisao: sem gabarito")

    # 2. Cobertura das chamadas à API — peso 1.0
    exp_cats = _expected_api_categories(expected)
    real_set = _tools_actually_called(result)
    if exp_cats:
        covered = exp_cats & real_set
        coverage = len(covered) / len(exp_cats)
        score += coverage
        faltando = sorted(exp_cats - real_set)
        details.append(
            f"tools: {coverage:.0%} cobertura ({len(covered)}/{len(exp_cats)})"
            + (f" — faltou {faltando}" if faltando else "")
        )
    else:
        details.append("tools: sem gabarito de chamadas")

    # 3. Honestidade dos gaps — peso 1.0, como guard-rail.
    #    Pontua por COERÊNCIA entre veredicto e gaps, não por existirem gaps.
    verdict = result.get("quality_verdict")
    gaps = result.get("data_gaps") or {}
    if not verdict:
        details.append("gaps: FALHOU — sem quality_verdict, impossível avaliar honestidade")
    elif verdict == "ok" and not gaps:
        score += 1.0
        details.append("gaps: OK (veredicto ok, nenhuma lacuna — coerente)")
    elif verdict != "ok" and gaps:
        score += 1.0
        details.append(f"gaps: OK ({len(gaps)} categoria(s) registrada(s) para veredicto '{verdict}')")
    elif verdict != "ok" and not gaps:
        details.append(f"gaps: FALHOU — veredicto '{verdict}' mas nenhuma lacuna registrada")
    else:
        details.append("gaps: FALHOU — veredicto 'ok' mas há lacunas registradas")

    return {
        "passed": decision_ok,
        "score": round(score / total, 3),
        "decision_ok": decision_ok,
        "erro_tipo": classificar_erro(exp_decision, real_decision),
        "details": details,
    }


# Alias mantido para compatibilidade com código que importava o nome privado.
_expected_decision = expected_decision
