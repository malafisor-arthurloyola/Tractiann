"""Ingestão de tickets — a plataforma recebendo chamados.

O que isto é, e por que não é o `eval.runner`
---------------------------------------------
Os dois rodam o mesmo grafo sobre os mesmos tickets, mas respondem a perguntas
diferentes e por isso tratam o HITL de formas opostas:

- `eval.runner` mede o agente. Não há operador olhando, então ele **aprova
  automaticamente** todo `interrupt()` para conseguir pontuar a trajetória
  inteira dos tickets sem intervenção. Por construção, nada fica pendente.
- `agent.ingest` **é** a plataforma. Quando o agente quer escrever na plataforma
  da Tractian, a execução congela no checkpointer e a ação vai para a fila de
  aprovações. Nada é executado sem um humano.

Como o checkpointer é o Postgres, o estado congelado aqui é o mesmo estado que a
interface Streamlit enxerga — processos diferentes, uma fila só. É isso que faz
a aba de notificações ter conteúdo real, em vez de reconstituir a fila na sessão
do navegador.

A ingestão também avalia: quando existe gabarito para o ticket, a nota de
trajetória e a decisão esperada são gravadas junto. Assim "executar na
plataforma" e "avaliar" deixam de ser dois mundos — as métricas da interface
saem das mesmas linhas que a operação produziu.

Uso:
    python -m agent.ingest                 # todos os tickets (cases.json)
    python -m agent.ingest --derivados     # inclui os cenários derivados
    python -m agent.ingest --tickets TKT-INV-09 TKT-EXE-12
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from agent.graph.agent import agent_graph
from agent.graph.checkpointer import status as checkpointer_status
from agent.logging.phoenix import setup_phoenix_tracing, run_in_phoenix_trace, flush
from agent.logging.postgres import (
    init_db,
    registrar_ticket,
    enfileirar_aprovacao,
    substituir_pendencias,
)
from agent.version import AGENT_VERSION

RAIZ = Path(__file__).resolve().parent.parent


def _estado_inicial(case: dict) -> dict:
    """Estado inicial do grafo para um ticket."""
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


def _carregar_casos(incluir_derivados: bool) -> list:
    casos = json.loads((RAIZ / "agent-input/cases.json").read_text(encoding="utf-8"))
    if incluir_derivados:
        casos += json.loads(
            (RAIZ / "agent-input/cases-derivados.json").read_text(encoding="utf-8")
        )
    return casos


def _carregar_gabaritos() -> dict:
    """Gabaritos indexados por ticket_id, dos dois conjuntos."""
    gab = {}
    for nome in ("eval/expected-paths.json", "eval/expected-paths-derivados.json"):
        caminho = RAIZ / nome
        if caminho.exists():
            for e in json.loads(caminho.read_text(encoding="utf-8")):
                gab[e["ticket_id"]] = e
    return gab


def _split_de(case: dict) -> str:
    """A que conjunto o ticket pertence — para a interface separar treino de
    held-out sem reler os arquivos de resultado.

    Duas armadilhas do `split.json`, ambas encontradas na prática:

    - ele é indexado por **`case_id`** (`case_tkt_inv_09`), não por `ticket_id`
      (`TKT-INV-09`), então procurar pelo ticket nunca casa;
    - as chaves iniciadas por `_` são comentários, não listas. Sem filtrá-las,
      `x in ids` roda contra uma string e vira busca de substring.
    """
    case_id = case.get("id", "")
    caminho = RAIZ / "eval/split.json"
    if caminho.exists():
        mapa = json.loads(caminho.read_text(encoding="utf-8"))
        for nome, ids in mapa.items():
            if nome.startswith("_") or not isinstance(ids, list):
                continue
            if case_id in ids:
                return nome
    # Fora do split treino/teste: os cenários derivados vivem em outro arquivo.
    derivados = RAIZ / "agent-input/cases-derivados.json"
    if derivados.exists():
        ids = {c["id"] for c in json.loads(derivados.read_text(encoding="utf-8"))}
        if case_id in ids:
            return "derivados"
    return "avulso"


def processar(case: dict, *, run_id: str, gabarito: dict | None = None) -> dict:
    """Processa um ticket como a plataforma faria: sem aprovar nada sozinha.

    Devolve um resumo do que aconteceu — se congelou esperando humano, qual ação
    foi pedida, e a nota de trajetória quando havia gabarito.
    """
    ticket_id = case["ticket_id"]
    # thread_id carimbado com a rodada: cada ingestão cria checkpoints novos, em
    # vez de tentar retomar um checkpoint pausado de uma rodada anterior.
    thread_id = f"{ticket_id}@{run_id}"
    config = {"configurable": {"thread_id": thread_id}}

    inicio = time.time()
    with run_in_phoenix_trace(case["id"], ticket_id, asset_id=case.get("asset_id")):
        resultado = agent_graph.invoke(_estado_inicial(case), config=config)
    duracao = time.time() - inicio

    pausado = bool(resultado.get("__interrupt__"))
    payload = resultado["__interrupt__"][0].value if pausado else {}

    # Avaliação, quando há gabarito. Não altera o que o agente fez — só anota.
    nota, esperada = None, None
    if gabarito:
        from eval.assertions.trajectory import assert_trajectory, expected_decision
        esperada = expected_decision(gabarito)
        try:
            nota = assert_trajectory(resultado, gabarito).get("score")
        except Exception as e:
            print(f"  [aviso] avaliacao falhou para {ticket_id}: {e}")

    registrar_ticket(
        resultado,
        agent_version=AGENT_VERSION,
        thread_id=thread_id,
        status="aguardando_humano" if pausado else "concluido",
        split=_split_de(case),
        decisao_esperada=esperada,
        trajectory_score=nota,
    )

    if pausado:
        enfileirar_aprovacao(
            ticket_id=ticket_id,
            thread_id=thread_id,
            agent_version=AGENT_VERSION,
            asset_id=case.get("asset_id"),
            payload=payload,
        )

    return {
        "ticket_id": ticket_id,
        "decisao": resultado.get("decision"),
        "esperada": esperada,
        "nota": nota,
        "pausado": pausado,
        "acao": payload.get("action_type"),
        "alvo": payload.get("action_target"),
        "duracao": duracao,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Ingestao de tickets na plataforma")
    p.add_argument("--derivados", action="store_true",
                   help="inclui tambem os 6 cenarios derivados")
    p.add_argument("--tickets", nargs="*", default=None,
                   help="processa apenas estes ticket_ids")
    args = p.parse_args()

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    setup_phoenix_tracing()
    if not init_db():
        print("ERRO: sem Postgres a fila de aprovacoes nao persiste. "
              "Rode `make postgres-up` antes.")
        return 1

    tipo, motivo = checkpointer_status()
    if tipo != "postgres":
        print(f"ERRO: checkpointer em '{tipo}' ({motivo}).")
        print("Sem checkpointer persistente as acoes pausadas morrem com este "
              "processo, e a interface nao as enxerga.")
        return 1

    casos = _carregar_casos(args.derivados)
    if args.tickets:
        alvo = set(args.tickets)
        casos = [c for c in casos if c["ticket_id"] in alvo]
    if not casos:
        print("Nenhum ticket a processar.")
        return 1

    gabaritos = _carregar_gabaritos()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    substituidas = substituir_pendencias([c["ticket_id"] for c in casos], AGENT_VERSION)
    if substituidas:
        print(f"{substituidas} pendencia(s) anterior(es) marcada(s) como substituida(s).\n")

    print(f"Ingerindo {len(casos)} ticket(s) - versao {AGENT_VERSION}, rodada {run_id}")
    print("Acoes que exigem escrita na plataforma ficam congeladas na fila.\n")

    resumos, falhas = [], 0
    for i, caso in enumerate(casos, 1):
        tid = caso["ticket_id"]
        print(f"[{i}/{len(casos)}] {tid} ...", end=" ", flush=True)
        try:
            r = processar(caso, run_id=run_id, gabarito=gabaritos.get(tid))
        except Exception as e:
            falhas += 1
            print(f"FALHOU: {type(e).__name__}: {str(e)[:120]}")
            continue
        resumos.append(r)
        marca = "AGUARDA HUMANO" if r["pausado"] else "concluido"
        nota = f" nota {r['nota']:.2f}" if r["nota"] is not None else ""
        print(f"{r['decisao']} - {marca} ({r['duracao']:.0f}s){nota}")

    flush()

    linha = "-" * 62
    pendentes = [r for r in resumos if r["pausado"]]
    print(f"\n{linha}")
    print(f"Processados      : {len(resumos)}" + (f"  ({falhas} falha(s))" if falhas else ""))
    print(f"Autonomos        : {len(resumos) - len(pendentes)}")
    print(f"Aguardando humano: {len(pendentes)}")
    for r in pendentes:
        print(f"   - {r['ticket_id']}: {r['acao']} em {r['alvo']}")
    avaliados = [r for r in resumos if r["esperada"]]
    if avaliados:
        acertos = [r for r in avaliados if r["decisao"] == r["esperada"]]
        print(f"Decisao correta  : {len(acertos)}/{len(avaliados)}")
    print(linha)
    print("A fila esta no Postgres. Abra a aba Notificacoes da plataforma.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
