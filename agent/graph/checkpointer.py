"""Checkpointer do grafo — persistente quando há Postgres, em memória quando não há.

Por que isto existe
-------------------
O `interrupt()` do HITL congela o grafo no meio da execução: o estado fica no
checkpointer até alguém retomar. Com o `MemorySaver` esse estado vive na RAM do
processo, o que tem duas consequências que inviabilizam a plataforma:

1. Um ticket pausado por um processo é invisível para qualquer outro. A
   ingestão roda num script, a interface roda no Streamlit — sem estado
   compartilhado, a fila de aprovações da interface nasce sempre vazia.
2. Reiniciar a aplicação descarta silenciosamente todas as ações que estavam
   esperando aprovação humana.

Com o `PostgresSaver` o checkpoint vira uma linha no banco. Quem pausa e quem
retoma podem ser processos diferentes, em máquinas diferentes, com horas de
distância — que é como uma fila de aprovações precisa funcionar.

O `MemorySaver` continua como fallback para que os testes e o uso offline não
exijam um banco de pé.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Motivo pelo qual o checkpointer persistente não subiu, para a UI poder explicar
# ao operador em vez de só mostrar uma fila vazia.
_motivo: str = "não inicializado"
_tipo: str = "desconhecido"
_pool = None


def _construir_postgres():
    """Tenta montar o PostgresSaver. Devolve None (e preenche `_motivo`) se falhar."""
    global _motivo, _pool

    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg_pool import ConnectionPool
        from psycopg.rows import dict_row
    except ImportError as e:
        _motivo = f"pacote ausente ({e}) — rode `uv pip install -e .`"
        return None

    url = os.getenv("DATABASE_URL")
    if not url:
        _motivo = "DATABASE_URL não definida em agent/.env"
        return None

    try:
        # `open=False` + `open(wait=...)` para falhar rápido: o pool aberto na
        # construção tentaria reconectar em background e o import travaria.
        pool = ConnectionPool(
            conninfo=url,
            max_size=10,
            open=False,
            # autocommit é exigido pelo PostgresSaver; dict_row idem.
            kwargs={"autocommit": True, "row_factory": dict_row},
        )
        pool.open(wait=True, timeout=5)
        saver = PostgresSaver(pool)
        saver.setup()  # cria as tabelas de checkpoint (idempotente)
    except Exception as e:
        safe = url.rsplit("@", 1)[-1] if "@" in url else url
        _motivo = f"{type(e).__name__} ao conectar em {safe}: {str(e).strip()[:160]}"
        return None

    _pool = pool
    _motivo = "conectado"
    return saver


def build_checkpointer():
    """Devolve o checkpointer a usar, preferindo o persistente."""
    global _tipo

    if os.getenv("CHECKPOINTER", "").lower() == "memory":
        # Escape hatch para os testes e para rodar sem Docker.
        from langgraph.checkpoint.memory import MemorySaver
        _tipo, _motivo_local = "memory", "forçado por CHECKPOINTER=memory"
        globals()["_motivo"] = _motivo_local
        return MemorySaver()

    saver = _construir_postgres()
    if saver is not None:
        _tipo = "postgres"
        return saver

    from langgraph.checkpoint.memory import MemorySaver
    _tipo = "memory"
    print(f"[checkpointer] Postgres indisponível, usando memória: {_motivo}")
    return MemorySaver()


def status() -> tuple[str, str]:
    """(tipo, motivo) do checkpointer em uso — para o badge da interface."""
    return _tipo, _motivo
