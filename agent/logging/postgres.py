"""Logger de execuções do agente — salva no Postgres.

Schema:
  execucoes(id, ticket_id, agent_version, user_id, asset_id,
             decision, quality_verdict, data_gaps, trace, response, created_at)
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


# Motivo da última falha de conexão. Guardado porque `_get_connection` devolve
# None para causas muito diferentes (driver ausente, banco fora do ar, senha
# errada) e antes não havia como distingui-las — o badge da UI ficava cinza sem
# dizer o porquê.
_last_error: str | None = None


def _get_connection():
    """Retorna conexão com Postgres usando psycopg2, ou None em caso de falha.

    A causa da falha fica em `_last_error` e é exposta por `check_health()`.
    """
    global _last_error
    try:
        import psycopg2
    except ImportError as e:
        _last_error = f"psycopg2 não instalado ({e}) — rode `uv pip install -e .`"
        return None

    url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/tractian_agent")
    try:
        conn = psycopg2.connect(url)
        _last_error = None
        return conn
    except Exception as e:
        # A URL pode conter senha; reporta só o host/porta.
        safe = url.rsplit("@", 1)[-1] if "@" in url else url
        _last_error = f"{type(e).__name__} ao conectar em {safe}: {str(e).strip()[:160]}"
        return None


def check_health() -> tuple[bool, str]:
    """Testa a conexão e devolve (ok, motivo).

    Interface pública para a UI e o Makefile — evita que consumidores chamem
    `_get_connection` diretamente só para saber se o banco responde.
    """
    conn = _get_connection()
    if conn is None:
        return False, _last_error or "causa desconhecida"
    try:
        conn.close()
    except Exception:
        pass
    return True, "conectado"


def init_db():
    """Cria a tabela execucoes se não existir."""
    conn = _get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS execucoes (
                id              SERIAL PRIMARY KEY,
                ticket_id       TEXT NOT NULL,
                agent_version   TEXT NOT NULL DEFAULT 'v1',
                user_id         TEXT,
                asset_id        TEXT,
                decision        TEXT,
                quality_verdict TEXT,
                data_gaps       JSONB,
                trace           JSONB,
                response        TEXT,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        conn.commit()
        return True
    except Exception as e:
        print(f"[postgres] Erro ao criar tabela: {e}")
        return False
    finally:
        conn.close()


def log_execution(result: dict, agent_version: str = "v1"):
    """Salva uma execução do agente no Postgres.
    
    Args:
        result: estado final do grafo (dict com decision, trace, etc.)
        agent_version: versão do agente (para comparação entre versões)
    
    Returns:
        True se salvou, False se não (DB indisponível ou erro)
    """
    conn = _get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO execucoes
                (ticket_id, agent_version, user_id, asset_id,
                 decision, quality_verdict, data_gaps, trace, response)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            result.get("ticket_id"),
            agent_version,
            result.get("user_id"),
            result.get("asset_id"),
            result.get("decision"),
            result.get("quality_verdict"),
            json.dumps(result.get("data_gaps") or {}),
            json.dumps(result.get("trace") or []),
            result.get("response"),
        ))
        conn.commit()
        return True
    except Exception as e:
        print(f"[postgres] Erro ao salvar execução: {e}")
        return False
    finally:
        conn.close()


def _rows(conn, query, params=()):
    cur = conn.cursor()
    cur.execute(query, params)
    if cur.description is None:
        # DML (INSERT/UPDATE/DELETE): sem result set → retorna linhas afetadas
        affected = cur.rowcount
        conn.commit()
        cur.close()
        return {"affected": affected}
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def query(query: str, params=()):
    """Executa uma query arbitrária e retorna as linhas como dicts.

    - SELECT → lista de dicts
    - DML (INSERT/UPDATE/DELETE) → dict com {'affected': N}
    """
    conn = _get_connection()
    if not conn:
        return None
    try:
        return _rows(conn, query, params)
    except Exception as e:
        print(f"[postgres] Erro na query: {e}")
        return None
    finally:
        conn.close()


def count_by_version() -> dict:
    """Quantas execuções por versão do agente."""
    rows = query(
        "SELECT agent_version, COUNT(*) AS n FROM execucoes GROUP BY agent_version"
    ) or []
    return {r["agent_version"]: r["n"] for r in rows}


def summary_by_version(agent_version: str) -> list:
    """Resumo agregado de decisões/veredictos de uma versão."""
    rows = query(
        """SELECT decision, quality_verdict, COUNT(*) AS n
           FROM execucoes
           WHERE agent_version = %s
           GROUP BY decision, quality_verdict""",
        (agent_version,),
    ) or []
    return rows


def compare_versions(v_a: str, v_b: str) -> list:
    """Compara a distribuição de decisões entre duas versões.

    Returns:
        lista de linhas com {decision, quality_verdict, v_a, v_b}
    """
    rows = query(
        """SELECT * FROM (
            SELECT
                COALESCE(a.decision, b.decision) AS decision,
                COALESCE(a.quality_verdict, b.quality_verdict) AS quality_verdict,
                COALESCE(a.n, 0) AS v_a,
                COALESCE(b.n, 0) AS v_b
            FROM (SELECT decision, quality_verdict, COUNT(*) n FROM execucoes
                  WHERE agent_version = %s GROUP BY decision, quality_verdict) a
            FULL OUTER JOIN (SELECT decision, quality_verdict, COUNT(*) n FROM execucoes
                  WHERE agent_version = %s GROUP BY decision, quality_verdict) b
              ON a.decision = b.decision
             AND a.quality_verdict = b.quality_verdict
        ) t
        ORDER BY v_a + v_b DESC""",
        (v_a, v_b),
    ) or []
    return rows
