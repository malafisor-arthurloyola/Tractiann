"""Cliente HTTP da API industrial.

Detalhe interno do servidor MCP (ADR-0001): nenhum nó do grafo importa este
módulo. Centraliza base URL, header `x-user-id` e tradução de erro HTTP.
"""
import os
from typing import Any, Dict

import httpx

API_BASE_URL = os.getenv("TRACTIAN_API_URL", "http://localhost:8000")


def tractian_request(
    method: str,
    path: str,
    user_id: str | None = None,
    params: Dict[str, Any] | None = None,
    json_data: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Chama a API industrial e devolve sempre um envelope.

    Um erro HTTP é uma **resposta legítima da API**, não uma exceção: 403 quer
    dizer "este usuário não tem essa permissão", que é justamente um dos
    cenários que o case modela. Levantar exceção aqui fazia o servidor MCP
    despejar traceback no stderr e o agente registrar só "ERRO".

    Traduzimos para o mesmo envelope `{mode, notes, data}` que o resto do
    sistema já entende, com `http_status` para quem precisar do detalhe.
    """
    url = f"{API_BASE_URL}{path}"
    headers = {"x-user-id": user_id} if user_id else {}

    with httpx.Client(timeout=10.0) as client:
        response = client.request(
            method=method, url=url, params=params, json=json_data, headers=headers
        )

        if response.is_success:
            return response.json()

        return {
            "mode": "unavailable",
            "notes": _explicar_erro(response, user_id),
            "data": None,
            "http_status": response.status_code,
        }


def _explicar_erro(response: httpx.Response, user_id: str | None) -> str:
    """Mensagem legível para o agente e para o log."""
    detalhe = ""
    try:
        corpo = response.json()
        detalhe = str(corpo.get("detail") or corpo)[:160]
    except Exception:
        detalhe = response.text[:160]

    if response.status_code == 403:
        return (
            f"permissão negada para o usuário '{user_id}' nesta operação "
            f"(HTTP 403): {detalhe}"
        )
    if response.status_code == 404:
        return f"recurso não encontrado (HTTP 404): {detalhe}"
    return f"HTTP {response.status_code}: {detalhe}"
