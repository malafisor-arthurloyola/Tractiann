"""
Tools MCP para o agente Tractian.

Cada função aqui representa UMA operação da API Tractian, exposta como
tool no padrão MCP (via FastMCP). Começamos com UMA tool só —
get_baseline — pra provar que a conexão agente → MCP → API funciona
de ponta a ponta antes de adicionar as outras 16.
"""

import os
import httpx
from mcp.server.fastmcp import FastMCP

API_BASE_URL = os.getenv("TRACTIAN_API_URL", "http://localhost:8000")

# "tractian-tools" é só o nome do servidor MCP — aparece pra quem se conectar nele.
mcp = FastMCP("tractian-tools")


@mcp.tool()
def get_baseline(
    asset_id: str,
    user_id: str,
    point_id: str | None = None,
    seed: int | None = None,
) -> dict:
    """
    Consulta o estado do baseline (o "normal" aprendido) de um ativo/ponto.

    Retorna o estado (learning/established/invalidated), o modo de
    detecção (baseline/symptom) e, quando aplicável, as features com
    seus pares reference/tolerance.

    Use esta tool sempre que precisar saber se dá pra confiar num
    alarme de desvio, ou por que um insight não foi gerado.

    Args:
        asset_id: ID do ativo (ex.: "asset_G501").
        user_id: ID de quem abriu o ticket — vai no header x-user-id,
            define permissões e contexto de empresa.
        point_id: ID do ponto de medição, se o ticket já especificar um.
        seed: fixa o modo de resposta probabilístico da API (útil na
            avaliação, pra reprodutibilidade). Deixe None em uso normal.
    """
    params = {}
    if point_id:
        params["point_id"] = point_id
    if seed is not None:
        params["seed"] = seed

    response = httpx.get(
        f"{API_BASE_URL}/assets/{asset_id}/baseline",
        params=params,
        headers={"x-user-id": user_id},
        timeout=10.0,
    )
    response.raise_for_status()

    # A API sempre devolve um "envelope": {"mode": ..., "data": ..., "notes": ...}
    # mode pode ser complete/partial/inconclusive/conflict/unavailable —
    # o agente (não esta função) é quem decide o que fazer com isso.
    return response.json()


if __name__ == "__main__":
    # Teste manual rápido — NÃO faz parte do agente, é só pra você conferir
    # que a tool funciona antes de conectar ela em qualquer coisa.
    #
    # Como rodar:
    #   1. make up          (sobe a API industrial em :8000)
    #   2. python agent/tools.py
    import json

    resultado = get_baseline(asset_id="asset_G501", user_id="usr_ana")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
