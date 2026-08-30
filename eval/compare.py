"""CLI de comparação de versões do agente no Postgres.

Uso:
    python -m eval.compare v1 v2          # compara decisões entre duas versões
    python -m eval.compare --versions     # lista versões e contagens
"""
import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "agent" / ".env")

from agent.logging.postgres import count_by_version, compare_versions, query


def print_table(rows, cols=None):
    if not rows:
        print("  (sem dados)")
        return
    cols = cols or list(rows[0].keys())
    headers = "  " + " | ".join(f"{c:>15}" for c in cols)
    print(headers)
    print("  " + "-" * len(headers))
    for r in rows:
        print("  " + " | ".join(f"{r.get(c, ''):>15}" for c in cols))


def main():
    parser = argparse.ArgumentParser(description="Compara versões do agente no Postgres")
    parser.add_argument("va", nargs="?", help="Versão A")
    parser.add_argument("vb", nargs="?", help="Versão B")
    parser.add_argument("--versions", action="store_true", help="Lista versões/contagens")
    args = parser.parse_args()

    if args.versions:
        print("Versões (contagens de execução):")
        for v, n in count_by_version().items():
            print(f"  {v}: {n}")
        return

    if not (args.va and args.vb):
        print("Uso: python -m eval.compare v1 v2  |  --versions")
        sys.exit(1)

    print(f"Comparando decisões: {args.va}  vs  {args.vb}")
    print()
    rows = compare_versions(args.va, args.vb)
    print("  (decisão | quality_verdict | vA | vB)")
    print_table(rows)
    print()
    print("Nota: vA/vB são contagens de execuções por (decisão, verdict).")
    print("Para comparar os TRACES (o 'porquê'), use o dashboard Phoenix "
          "com PHOENIX_ENABLED=1.")


if __name__ == "__main__":
    main()
