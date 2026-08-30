"""Roda o agente sobre os casos e salva resumo em utf-8."""
import json, sys, io
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path("agent/.env"))

from agent.graph.agent import agent_graph

cases = json.loads(Path("agent-input/cases.json").read_text(encoding="utf-8"))
lines = [f"Total de casos: {len(cases)}"]

from collections import Counter
decisions = Counter()

for i, case in enumerate(cases[:12], 1):
    st = {
        "ticket_id": case["ticket_id"], "case_id": case["id"],
        "company_id": case["company_id"], "user_id": case["user_id"],
        "asset_id": case["asset_id"], "message": case["message"],
        "raw": {}, "baseline": None, "analyses": [], "rms_data": None,
        "spectrum_data": None, "data_quality": None, "quality_verdict": None,
        "quality_notes": None, "data_gaps": {}, "next_tool": None,
        "tools_called": [], "decision": None, "decision_justification": None,
        "response": None, "trace": [],
    }
    try:
        r = agent_graph.invoke(st)
        q = r.get("quality_verdict") or "-"
        d = r.get("decision") or "-"
        gaps = list(r.get("data_gaps", {}).keys())
        decisions[(q, d)] += 1
        lines.append(f"{i:2}. {case['ticket_id']:<12} quality={q:<12} decision={d:<9} gaps={gaps}")
    except Exception as e:
        lines.append(f"{i:2}. {case['ticket_id']}: ERRO - {str(e)[:90]}")

lines.append("")
lines.append("=== RESUMO ===")
for (q, d), n in decisions.items():
    lines.append(f"  quality={q:<12} decision={d:<9} -> {n} casos")

out = Path("test_output.txt")
out.write_text("\n".join(lines), encoding="utf-8")
print("Salvo em test_output.txt")
