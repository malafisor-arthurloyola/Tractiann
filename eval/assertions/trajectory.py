"""Assertions determinísticas: compara trajetória do agente vs gabarito."""
from pathlib import Path
import json


def load_expected_paths() -> list:
    """Carrega o gabarito de trajetórias esperadas (lista de casos)."""
    path = Path(__file__).resolve().parent.parent / "expected-paths.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _expected_decision(expected: dict) -> str | None:
    """Deriva a decisão esperada do último step (POST) do gabarito."""
    path = expected.get("expected_path", [])
    if not path:
        return None
    last = path[-1].get("step", "")
    if "/escalate" in last:
        return "escalate"
    if "/reprocess" in last or "/retrain" in last or "/specialist" in last:
        return "act"
    return "orient"


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
        elif "/models" in step: cats.add("models")
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


def assert_trajectory(result: dict, expected: dict) -> dict:
    """Compara a trajetória real com a esperada.
    
    Args:
        result: estado final do grafo (com trace, decision, quality_verdict, data_gaps)
        expected: entrada do gabarito (com expected_path, mode)
    
    Returns:
        dict com passed (bool), score (0-1), details (lista de strings)
    """
    details = []
    total = 4.0
    score = 0.0

    # 1. Decisão esperada vs real
    exp_decision = _expected_decision(expected)
    real_decision = result.get("decision")
    if exp_decision and real_decision:
        if exp_decision == real_decision:
            score += 1.0
            details.append(f"decisao: OK ({real_decision})")
        else:
            details.append(f"decisao: FALHOU (esperado={exp_decision}, real={real_decision})")
    elif exp_decision:
        details.append("decisao: FALHOU (agente não retornou decisão)")
    else:
        details.append("decisao: sem gabarito")

    # 2. Chamadas à API (tools de investigação)
    exp_cats = _expected_api_categories(expected)
    real_tools = []
    for step in result.get("trace", []):
        if isinstance(step, dict) and step.get("node") == "investigate":
            real_tools = step.get("tools_called", [])
            break
    real_set = set(real_tools)
    if exp_cats:
        covered = exp_cats & real_set
        coverage = len(covered) / len(exp_cats) if exp_cats else 0
        score += coverage
        details.append(f"tools: {coverage:.0%} cobertura ({len(covered)}/{len(exp_cats)})")
    else:
        details.append("tools: sem gabarito de chamadas")

    # 3. Veredicto de qualidade (presente?)
    real_verdict = result.get("quality_verdict")
    if real_verdict:
        score += 1.0
        details.append(f"quality_verdict: {real_verdict}")
    else:
        details.append("quality_verdict: ausente")

    # 4. Gaps registrados (honestidade)
    gaps = result.get("data_gaps") or {}
    verdict = result.get("quality_verdict")
    if verdict and verdict != "ok" and not gaps:
        details.append("gaps: FALHOU — verdict não-ok mas nenhum gap registrado")
    elif gaps:
        score += 1.0
        details.append(f"gaps: {len(gaps)} categoria(s) registrada(s)")
    else:
        details.append("gaps: nenhum (verdict ok)")

    return {
        "passed": score >= (total * 0.5),
        "score": round(score / total, 3),
        "details": details,
    }
