"""Logger de execuções do agente — salva no Postgres.

Schema:
  execucoes(id, ticket_id, agent_version, user_id, asset_id,
             decision, quality_verdict, data_gaps, trace, response, created_at)
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _get_connection():
    """Retorna conexão com Postgres usando psycopg2."""
    try:
        import psycopg2
        return psycopg2.connect(os.getenv("DATABASE_URL", "postgresql://localhost:5432/tractian_agent"))
    except ImportError:
        return None
    except Exception:
        return None


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


def summary_by_version(agent_version: str) -> dict:
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
