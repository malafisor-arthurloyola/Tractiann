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
    """Cria/atualiza o schema da plataforma.

    Duas tabelas:

    - `execucoes` — um ticket processado. Ganhou colunas de plataforma
      (`thread_id`, `status`, avaliação) para deixar de ser só um log e passar a
      ser a fonte das métricas da interface.
    - `fila_aprovacoes` — a caixa de entrada do operador. Uma linha por ação que
      o agente quer executar e está congelada esperando decisão humana.

    Os `ALTER TABLE ... IF NOT EXISTS` deixam a função idempotente sobre bancos
    que já existem, sem exigir recriação.
    """
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
        # Colunas de plataforma, acrescentadas depois da tabela original.
        for coluna, tipo in (
            ("thread_id", "TEXT"),                 # chave para retomar o grafo
            ("status", "TEXT DEFAULT 'concluido'"),  # concluido|aguardando_humano|cancelado
            ("split", "TEXT"),                     # train|test|derivados|avulso
            ("decisao_esperada", "TEXT"),          # gabarito, quando existe
            ("trajectory_score", "REAL"),          # nota determinística, quando avaliado
        ):
            cur.execute(f"ALTER TABLE execucoes ADD COLUMN IF NOT EXISTS {coluna} {tipo};")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS fila_aprovacoes (
                id               SERIAL PRIMARY KEY,
                ticket_id        TEXT NOT NULL,
                thread_id        TEXT NOT NULL UNIQUE,
                agent_version    TEXT NOT NULL DEFAULT 'v1',
                asset_id         TEXT,
                action_type      TEXT,
                action_target    TEXT,
                justification    TEXT,
                customer_message TEXT,
                gaps             JSONB,
                status           TEXT NOT NULL DEFAULT 'pendente',
                criado_em        TIMESTAMPTZ DEFAULT NOW(),
                resolvido_em     TIMESTAMPTZ,
                resolvido_por    TEXT
            );
        """)
        cur.execute("""CREATE INDEX IF NOT EXISTS idx_fila_status
                       ON fila_aprovacoes (status, criado_em DESC);""")
        cur.execute("""CREATE INDEX IF NOT EXISTS idx_execucoes_versao
                       ON execucoes (agent_version, created_at DESC);""")
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


# ---------------------------------------------------------------------------
# Plataforma: registro de tickets e fila de aprovações
#
# `log_execution` acima continua servindo o caminho antigo (uma linha por
# execução concluída). As funções abaixo são o que a plataforma usa: um ticket
# entra, é registrado, e — se o agente quiser executar uma ação — fica congelado
# na fila até um humano decidir. É a mesma linha do banco do começo ao fim, o
# que permite consultar a autonomia sem depender de arquivo nenhum.
# ---------------------------------------------------------------------------

def registrar_ticket(result: dict, *, agent_version: str, thread_id: str,
                     status: str, split: str | None = None,
                     decisao_esperada: str | None = None,
                     trajectory_score: float | None = None) -> int | None:
    """Grava um ticket processado e devolve o id da linha.

    `status` distingue quem terminou sozinho (`concluido`) de quem parou
    esperando aprovação (`aguardando_humano`) — é essa coluna que sustenta a
    taxa de autonomia.
    """
    conn = _get_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO execucoes
                (ticket_id, agent_version, user_id, asset_id, decision,
                 quality_verdict, data_gaps, trace, response,
                 thread_id, status, split, decisao_esperada, trajectory_score)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (
            result.get("ticket_id"), agent_version, result.get("user_id"),
            result.get("asset_id"), result.get("decision"),
            result.get("quality_verdict"),
            json.dumps(result.get("data_gaps") or {}),
            json.dumps(result.get("trace") or []),
            result.get("response"),
            thread_id, status, split, decisao_esperada, trajectory_score,
        ))
        linha_id = cur.fetchone()[0]
        conn.commit()
        return linha_id
    except Exception as e:
        print(f"[postgres] Erro ao registrar ticket: {e}")
        return None
    finally:
        conn.close()


def enfileirar_aprovacao(*, ticket_id: str, thread_id: str, agent_version: str,
                         asset_id: str | None, payload: dict) -> bool:
    """Coloca uma ação pendente na caixa de entrada do operador.

    `payload` é o dicionário que o `interrupt()` carrega — tipo da ação, alvo,
    justificativa e as lacunas de dado que o agente reconhece ter. As lacunas
    entram porque são justamente o que um humano precisa ver antes de autorizar
    uma escrita na plataforma.

    O `ON CONFLICT (thread_id)` torna a ingestão repetível: rodar duas vezes na
    mesma thread não duplica pendências. Reexecutar o ticket, porém, cria uma
    thread nova — e sem a chamada a `substituir_pendencias` abaixo o operador
    veria o mesmo ticket duas vezes na caixa de entrada, apontando para
    checkpoints diferentes; aprovar um deixaria o outro pendurado. **Um ticket
    tem no máximo uma aprovação em aberto** é invariante da fila, então é
    garantido aqui e não em cada chamador.
    """
    substituir_pendencias([ticket_id], agent_version)

    conn = _get_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO fila_aprovacoes
                (ticket_id, thread_id, agent_version, asset_id, action_type,
                 action_target, justification, customer_message, gaps, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'pendente')
            ON CONFLICT (thread_id) DO UPDATE SET
                action_type      = EXCLUDED.action_type,
                action_target    = EXCLUDED.action_target,
                justification    = EXCLUDED.justification,
                customer_message = EXCLUDED.customer_message,
                gaps             = EXCLUDED.gaps,
                status           = 'pendente',
                criado_em        = NOW(),
                resolvido_em     = NULL,
                resolvido_por    = NULL
        """, (
            ticket_id, thread_id, agent_version, asset_id,
            payload.get("action_type"), payload.get("action_target"),
            payload.get("justification"), payload.get("customer_message"),
            json.dumps(payload.get("gaps") or {}),
        ))
        conn.commit()
        return True
    except Exception as e:
        print(f"[postgres] Erro ao enfileirar aprovação: {e}")
        return False
    finally:
        conn.close()


def listar_pendencias(agent_version: str | None = None) -> list:
    """Ações congeladas aguardando decisão humana, mais antigas primeiro.

    A ordem importa: numa fila de manutenção, o que espera há mais tempo é o que
    corre mais risco de virar parada não planejada.
    """
    sql = """SELECT * FROM fila_aprovacoes WHERE status = 'pendente'"""
    params: tuple = ()
    if agent_version:
        sql += " AND agent_version = %s"
        params = (agent_version,)
    sql += " ORDER BY criado_em ASC"
    return query(sql, params) or []


def resolver_pendencia(thread_id: str, *, aprovado: bool, por: str = "operador") -> bool:
    """Marca uma pendência como decidida. Não retoma o grafo — quem faz isso é a
    interface, que precisa do `thread_id` para chamar o `Command(resume=...)`."""
    r = query(
        """UPDATE fila_aprovacoes
              SET status = %s, resolvido_em = NOW(), resolvido_por = %s
            WHERE thread_id = %s""",
        ("aprovado" if aprovado else "rejeitado", por, thread_id),
    )
    return bool(r and r.get("affected"))


def historico_aprovacoes(limite: int = 50) -> list:
    """Pendências já decididas — o registro de quem autorizou o quê."""
    return query(
        """SELECT * FROM fila_aprovacoes
            WHERE status <> 'pendente'
            ORDER BY resolvido_em DESC LIMIT %s""",
        (limite,),
    ) or []


def estatisticas_autonomia(agent_version: str, split: str | None = None) -> dict:
    """Quantos tickets o agente resolveu sozinho e quantos exigiram um humano.

    Conta a execução **mais recente de cada ticket**, e não toda linha de
    `execucoes`. A tabela também guarda o histórico (reprocessamentos, execuções
    avulsas pela interface, logs de avaliações antigas); somar tudo faria um
    ticket rodado cinco vezes pesar cinco vezes na taxa de autonomia.

    Sai do banco, e não de `eval/results-*.json`, porque a pergunta é sobre o que
    a plataforma processou — inclusive tickets sem gabarito, que arquivo de
    avaliação nenhum contém.
    """
    # `thread_id IS NOT NULL` restringe às execuções da plataforma (ingestão e
    # interface). O `eval.runner` também grava em `execucoes`, mas aprova todo
    # `interrupt()` automaticamente: sem este filtro, rodar `make eval` depois de
    # `make demo` tornaria as linhas da avaliação as mais recentes e mascararia
    # as ações que estão de fato congeladas esperando um humano.
    sql = """SELECT status, COUNT(*) AS n FROM (
                 SELECT DISTINCT ON (ticket_id) ticket_id, status
                   FROM execucoes
                  WHERE agent_version = %s AND thread_id IS NOT NULL"""
    params: list = [agent_version]
    if split:
        sql += " AND split = %s"
        params.append(split)
    sql += """  ORDER BY ticket_id, created_at DESC
             ) ultimas GROUP BY status"""
    linhas = query(sql, tuple(params)) or []
    por_status = {l["status"]: l["n"] for l in linhas}
    total = sum(por_status.values())
    com_humano = por_status.get("aguardando_humano", 0)
    return {
        "total": total,
        "com_humano": com_humano,
        "autonomos": total - com_humano,
        "por_status": por_status,
    }


def listar_tickets(agent_version: str, split: str | None = None) -> list:
    """Tickets processados pela plataforma, mais recentes primeiro.

    `DISTINCT ON (ticket_id)` mantém só a execução mais recente de cada ticket:
    reprocessar não polui a tela com duplicatas.
    """
    # Mesmo filtro de `estatisticas_autonomia`: só o que a plataforma processou.
    sql = """SELECT DISTINCT ON (ticket_id)
                    ticket_id, asset_id, decision, quality_verdict, status,
                    split, decisao_esperada, trajectory_score, thread_id,
                    response, data_gaps, created_at
               FROM execucoes
              WHERE agent_version = %s AND thread_id IS NOT NULL"""
    params: list = [agent_version]
    if split:
        sql += " AND split = %s"
        params.append(split)
    sql += " ORDER BY ticket_id, created_at DESC"
    return query(sql, tuple(params)) or []


def limpar_plataforma(agent_version: str) -> None:
    """Apaga tickets e fila de uma versão — usado pela ingestão com `--limpar`."""
    query("DELETE FROM fila_aprovacoes WHERE agent_version = %s", (agent_version,))
    query("DELETE FROM execucoes WHERE agent_version = %s", (agent_version,))


def substituir_pendencias(ticket_ids: list, agent_version: str) -> int:
    """Aposenta pendências antigas dos tickets que estão sendo reprocessados.

    Reprocessar um ticket cria um novo `thread_id`; a pendência anterior aponta
    para um checkpoint que ninguém mais vai retomar. Marcá-la como `substituido`
    preserva o histórico sem deixar lixo na caixa de entrada.
    """
    if not ticket_ids:
        return 0
    r = query(
        """UPDATE fila_aprovacoes
              SET status = 'substituido', resolvido_em = NOW(), resolvido_por = 'sistema'
            WHERE status = 'pendente' AND agent_version = %s AND ticket_id = ANY(%s)""",
        (agent_version, list(ticket_ids)),
    )
    return (r or {}).get("affected", 0)


def carregar_ticket(ticket_id: str, agent_version: str) -> dict | None:
    """Última execução de um ticket feita pela plataforma, ou None.

    É o que permite a interface mostrar um ticket já processado sem reexecutá-lo:
    a ingestão roda uma vez, e qualquer navegador que abrir depois lê daqui.
    Sem isso, o resultado só existia em `st.session_state` — ou seja, só para
    quem tivesse clicado em "Executar Agente" naquela aba do navegador.
    """
    linhas = query(
        """SELECT ticket_id, asset_id, user_id, decision, quality_verdict,
                  data_gaps, trace, response, status, thread_id, split,
                  decisao_esperada, trajectory_score, created_at
             FROM execucoes
            WHERE agent_version = %s AND ticket_id = %s AND thread_id IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 1""",
        (agent_version, ticket_id),
    )
    return linhas[0] if linhas else None


def pendencia_de(ticket_id: str, agent_version: str) -> dict | None:
    """Pendência aberta de um ticket, se houver.

    Carrega o que o `interrupt()` guardou — ação, alvo, justificativa e lacunas —
    para a interface montar o painel de confirmação a partir do banco, e não de
    um objeto `Interrupt` que só existe na memória de quem executou.
    """
    linhas = query(
        """SELECT * FROM fila_aprovacoes
            WHERE agent_version = %s AND ticket_id = %s AND status = 'pendente'
            ORDER BY criado_em DESC
            LIMIT 1""",
        (agent_version, ticket_id),
    )
    return linhas[0] if linhas else None
