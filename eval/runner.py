"""Runner de avaliação: roda o agente sobre os cenários e coleta métricas.

Uso:
    python -m eval.runner                # roda todos os casos
    python -m eval.runner --case TKT-INV-04  # roda um caso específico
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "agent" / ".env")

from langgraph.types import Interrupt, Command

from agent.graph.agent import agent_graph
from agent.logging.phoenix import setup_phoenix_tracing, run_in_phoenix_trace
from eval.assertions.trajectory import assert_trajectory, load_expected_paths
from eval.judge.llm_judge import judge_response

# Instrumenta tracing (Phoenix) se ativado — opcional, não quebra sem o servidor
setup_phoenix_tracing()


def run_graph(state: dict) -> dict:
    """Roda o grafo, tratando o interrupt() do HITL.

    Na avaliação não há humano: a ação é aprovada automaticamente para que o
    grafo complete apenas o trace (decisão já foi tomada no nó decide).
    Com checkpointer, o langgraph retorna o estado pausado com a chave
    `__interrupt__` — capturamos e retomamos com aprovação.
    """
    # thread_id único por execução evita retomar checkpoints antigos no MemorySaver
    run_id = f"{state['ticket_id']}-run-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    config = {"configurable": {"thread_id": run_id}}
    try:
        result = agent_graph.invoke(state, config=config)
    except Interrupt:
        result = agent_graph.invoke(Command(resume=True), config=config)
    # Com MemorySaver o interrupt não levanta exceção: retorna com __interrupt__
    if "__interrupt__" in result:
        result = agent_graph.invoke(Command(resume=True), config=config)
    return result


def build_initial_state(case: dict) -> dict:
    """Monta o estado inicial do grafo a partir de um case."""
    return {
        "ticket_id": case["ticket_id"],
        "case_id": case["id"],
        "company_id": case["company_id"],
        "user_id": case["user_id"],
        "asset_id": case["asset_id"],
        "message": case["message"],
        "raw": {},
        "quality_verdict": None,
        "quality_notes": None,
        "data_gaps": {},
        "next_tool": None,
        "tools_called": [],
        "decision": None,
        "decision_justification": None,
        "action_type": None,
        "action_target": None,
        "response": None,
        "trace": [],
    }


def run_single(case: dict, expected: dict, run_judge: bool = True) -> dict:
    """Roda o agente em um caso e avalia.
    
    Returns:
        dict com case_id, trajectory (determinístico), judge (subjetivo), result
    """
    # 1. Executa o agente (aprova automaticamente qualquer interrupt — HITL)
    try:
        with run_in_phoenix_trace(case["id"], case["ticket_id"]):
            result = run_graph(build_initial_state(case))
    except Exception as e:
        return {
            "case_id": case["id"],
            "ticket_id": case["ticket_id"],
            "error": str(e),
            "trajectory": None,
            "judge": None,
        }

    # 2. Avaliação determinística (trajetória)
    trajectory = assert_trajectory(result, expected)

    # 3. Avaliação subjetiva (juiz LLM) — opcional
    judge = None
    if run_judge and result.get("response"):
        try:
            judge = judge_response(
                ticket=case["message"],
                gaps=result.get("data_gaps") or {},
                response=result.get("response") or "",
                decision=result.get("decision") or "",
            )
        except Exception as e:
            judge = {"error": str(e), "nota_geral": 0}

    return {
        "case_id": case["id"],
        "ticket_id": case["ticket_id"],
        "decision": result.get("decision"),
        "quality_verdict": result.get("quality_verdict"),
        "gaps": result.get("data_gaps") or {},
        "trajectory": trajectory,
        "judge": judge,
        "trace": result.get("trace") or [],
        "response": result.get("response"),
        "decision_justification": result.get("decision_justification"),
    }


def _log_result(case: dict, result: dict, agent_version: str | None = None) -> None:
    """Registra a execução no Postgres (silencioso se o DB não estiver no ar)."""
    if result.get("error"):
        return
    from agent.version import AGENT_VERSION
    payload = {
        "ticket_id": case.get("ticket_id"),
        "user_id": case.get("user_id"),
        "asset_id": case.get("asset_id"),
        "decision": result.get("decision"),
        "quality_verdict": result.get("quality_verdict"),
        "data_gaps": result.get("gaps") or {},
        "trace": result.get("trace") or [],          # trace REAL do agente
        "response": result.get("response"),
    }
    from agent.logging.postgres import log_execution
    log_execution(payload, agent_version=agent_version or AGENT_VERSION)


def load_split() -> dict:
    """Carrega o split treino/teste. Retorna {'train': [...], 'test': [...]}."""
    path = Path(__file__).resolve().parent / "split.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"train": data["train"], "test": data["test"]}


def filter_cases(cases: list, split: str) -> list:
    """Filtra cases por split ('train', 'test' ou 'all')."""
    if split == "all":
        return cases
    split_map = load_split()
    allowed = set(split_map[split])
    return [c for c in cases if c["id"] in allowed]


def run_all(split: str = "train", run_judge: bool = True) -> dict:
    """Roda avaliação sobre os casos do split escolhido.

    Args:
        split: 'train' (padrão, desenvolvimento) | 'test' (held-out, prova final) | 'all'
        run_judge: inclui avaliação subjetiva (LLM judge)
    
    Returns:
        dict com results (lista), summary (métricas agregadas)
    """
    cases_path = Path("agent-input/cases.json")
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    cases = filter_cases(cases, split)
    expected_list = load_expected_paths()
    expected_map = {e["id"]: e for e in expected_list}

    from agent.version import AGENT_VERSION

    results = []
    for case in cases:
        exp = expected_map.get(case["id"], {})
        result = run_single(case, exp, run_judge=run_judge)
        _log_result(case, result, AGENT_VERSION)
        results.append(result)

    # Métricas agregadas
    from collections import Counter
    decisions = Counter(r.get("decision") for r in results)
    verdicts = Counter(r.get("quality_verdict") for r in results)
    traj_scores = [r["trajectory"]["score"] for r in results if r.get("trajectory")]
    judge_scores = [r["judge"]["nota_geral"] for r in results if r.get("judge") and "nota_geral" in r["judge"]]

    summary = {
        "total": len(results),
        "decisions": dict(decisions),
        "verdicts": dict(verdicts),
        "trajectory_avg_score": sum(traj_scores) / len(traj_scores) if traj_scores else 0,
        "judge_avg_score": sum(judge_scores) / len(judge_scores) if judge_scores else 0,
    }

    return {"results": results, "summary": summary}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Runner de avaliação do agente Tractian")
    parser.add_argument("--case", type=str, help="Roda um caso específico (ticket_id)")
    parser.add_argument("--split", choices=["train", "test", "all"], default="train",
                        help="Split a rodar (padrão: train — o teste é held-out)")
    parser.add_argument("--no-judge", action="store_true", help="Pula avaliação subjetiva")
    parser.add_argument("--output", type=str, default="eval/results.json", help="Arquivo de saída")
    args = parser.parse_args()

    if args.case:
        cases = json.loads(Path("agent-input/cases.json").read_text(encoding="utf-8"))
        case = next((c for c in cases if c["ticket_id"] == args.case), None)
        if not case:
            print(f"Caso {args.case} não encontrado")
            sys.exit(1)
        expected_map = {e["id"]: e for e in load_expected_paths()}
        result = run_single(case, expected_map.get(case["id"], {}), run_judge=not args.no_judge)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        output = run_all(split=args.split, run_judge=not args.no_judge)
        out_path = args.output if args.split == "all" else f"eval/results-{args.split}.json"
        Path(out_path).write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Split: {args.split} | Resultados salvos em {out_path}")
        print(f"Resumo: {json.dumps(output['summary'], ensure_ascii=False)}")


if __name__ == "__main__":
    main()
