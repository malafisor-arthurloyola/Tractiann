"""Tabela de evolução entre versões do agente.

Junta as duas fontes de verdade que o projeto já grava:

  - `execucoes` (schema public) — decisão e veredicto por execução, com
    `agent_version`. É o log do próprio agente.
  - `phoenix.span_annotations` — as notas do juiz LLM e as verificações
    determinísticas, anexadas ao span raiz de cada ticket. O nome do projeto
    (`tractian-agent-vN`) é o que amarra a anotação à versão.

Uso:
    python -m eval.evolucao            # tabela no terminal
    python -m eval.evolucao --md       # markdown, para colar na apresentação
    python -m eval.evolucao --modelos  # desempenho por modelo que de fato respondeu
"""
import argparse
import json
import sys
from pathlib import Path

from agent.logging.postgres import check_health, query

# Eixos do juiz, na ordem em que aparecem na tabela.
EIXOS = ("nota_geral", "honestidade", "clareza", "fundamentacao", "seguranca")

_SQL_DECISOES = """
SELECT agent_version AS versao,
       COUNT(*)                                            AS execucoes,
       COUNT(*) FILTER (WHERE decision = 'orient')          AS orient,
       COUNT(*) FILTER (WHERE decision = 'act')             AS act,
       COUNT(*) FILTER (WHERE decision = 'escalate')        AS escalate
FROM execucoes
GROUP BY agent_version
ORDER BY agent_version
"""

# As anotações vivem no schema do Phoenix; o nome do projeto carrega a versão.
# O padrão do LIKE vai como parâmetro: um `%` literal no SQL seria interpretado
# pelo psycopg2 como placeholder e quebra com "tuple index out of range".
_SQL_ANOTACOES = """
SELECT REPLACE(p.name, 'tractian-agent-', '') AS versao,
       a.name                                 AS metrica,
       ROUND(AVG(a.score)::numeric, 2)        AS media,
       COUNT(*)                               AS n
FROM phoenix.span_annotations a
JOIN phoenix.spans    s ON s.id = a.span_rowid
JOIN phoenix.traces   t ON t.id = s.trace_rowid
JOIN phoenix.projects p ON p.id = t.project_rowid
WHERE p.name LIKE %s
GROUP BY 1, 2
"""


def coletar() -> tuple[list[dict], dict]:
    """Devolve (linhas de decisão por versão, {versao: {metrica: media}})."""
    decisoes = query(_SQL_DECISOES) or []
    anotacoes: dict[str, dict[str, float]] = {}
    for linha in query(_SQL_ANOTACOES, ("tractian-agent-%",)) or []:
        anotacoes.setdefault(linha["versao"], {})[linha["metrica"]] = float(linha["media"])
    return decisoes, anotacoes


def _celula(valor) -> str:
    return f"{valor:.2f}" if isinstance(valor, float) else "—"


def render(markdown: bool = False) -> str:
    decisoes, anotacoes = coletar()
    if not decisoes:
        return "Nenhuma execução gravada. Rode `make run` com o Postgres no ar."

    cabecalho = ["versao", "exec", "orient", "act", "escal", "acuracia"] + list(EIXOS)
    linhas = []
    for d in decisoes:
        v = d["versao"]
        notas = anotacoes.get(v, {})
        acuracia = notas.get("decisao_correta")
        linhas.append([
            v, str(d["execucoes"]), str(d["orient"]), str(d["act"]), str(d["escalate"]),
            f"{acuracia:.0%}" if isinstance(acuracia, float) else "—",
            *[_celula(notas.get(e)) for e in EIXOS],
        ])

    if markdown:
        out = ["| " + " | ".join(cabecalho) + " |",
               "|" + "|".join([":---"] + ["---:"] * (len(cabecalho) - 1)) + "|"]
        out += ["| " + " | ".join(l) + " |" for l in linhas]
        out.append("")
        out.append("> `acuracia` vem da anotação determinística `decisao_correta`; "
                   "os demais eixos são do juiz LLM. Versões sem juiz aparecem como `—`.")
        return "\n".join(out)

    larguras = [max(len(c), *(len(l[i]) for l in linhas)) for i, c in enumerate(cabecalho)]
    sep = "  "
    out = [sep.join(c.ljust(w) for c, w in zip(cabecalho, larguras)),
           sep.join("-" * w for w in larguras)]
    out += [sep.join(c.ljust(w) for c, w in zip(l, larguras)) for l in linhas]
    return "\n".join(out)


def por_modelo(caminho: str = "eval/results-train.json") -> str:
    """Desempenho agrupado pelo modelo que REALMENTE respondeu cada ticket.

    Roteadores escolhem o modelo por requisição, então uma média sobre a rodada
    inteira mistura modelos com vieses diferentes — um mais cauteloso, outro
    mais afirmativo. Esta visão desfaz a mistura.
    """
    arquivo = Path(caminho)
    if not arquivo.exists():
        return f"{caminho} não existe. Rode `make run` primeiro."

    resultados = json.loads(arquivo.read_text(encoding="utf-8"))["results"]
    por: dict[str, dict] = {}
    for r in resultados:
        modelo = next(
            (p.get("modelo") for p in (r.get("trace") or [])
             if isinstance(p, dict) and p.get("node") == "decide" and p.get("modelo")),
            "(não registrado)",
        )
        d = por.setdefault(modelo, {"n": 0, "acertos": 0, "notas": {}})
        d["n"] += 1
        if r.get("expected_decision") and r["expected_decision"] == r.get("decision"):
            d["acertos"] += 1
        juiz = r.get("judge") or {}
        for eixo in EIXOS:
            if isinstance(juiz.get(eixo), (int, float)):
                d["notas"].setdefault(eixo, []).append(juiz[eixo])

    if not por:
        return "Nenhum resultado com modelo registrado."

    cab = ["modelo", "tickets", "acuracia"] + list(EIXOS)
    linhas = []
    for modelo, d in sorted(por.items(), key=lambda kv: -kv[1]["n"]):
        medias = [
            f"{sum(v) / len(v):.2f}" if (v := d["notas"].get(e)) else "—"
            for e in EIXOS
        ]
        linhas.append([modelo[:38], f"{d['n']}", f"{d['acertos']}/{d['n']}"] + medias)

    larg = [max(len(c), *(len(l[i]) for l in linhas)) for i, c in enumerate(cab)]
    out = ["  ".join(c.ljust(w) for c, w in zip(cab, larg)),
           "  ".join("-" * w for w in larg)]
    out += ["  ".join(c.ljust(w) for c, w in zip(l, larg)) for l in linhas]
    out.append("")
    out.append("Fonte: eval/results-train.json — o modelo vem do passo `decide` do trace.")
    return "\n".join(out)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Evolução entre versões do agente")
    parser.add_argument("--md", action="store_true", help="Saída em markdown")
    parser.add_argument("--modelos", action="store_true",
                        help="Agrupa por modelo que de fato respondeu (roteadores variam)")
    args = parser.parse_args()

    if args.modelos:
        print(por_modelo())
        return

    ok, motivo = check_health()
    if not ok:
        print(f"Postgres indisponível: {motivo}")
        print("Suba com `make up-obs`.")
        sys.exit(1)

    print(render(markdown=args.md))


if __name__ == "__main__":
    main()
