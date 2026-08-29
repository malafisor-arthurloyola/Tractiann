import os
import httpx
from typing import Any, Dict

API_BASE_URL = os.getenv("TRACTIAN_API_URL", "http://localhost:8000")

def tractian_request(
    method: str,
    path: str,
    user_id: str | None = None,
    params: Dict[str, Any] | None = None,
    json_data: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Helper central para chamadas HTTP à API industrial.
    Centraliza: Base URL, headers (x-user-id), e tratamento de erro.
    """
    url = f"{API_BASE_URL}{path}"
    headers = {}
    if user_id:
        headers["x-user-id"] = user_id
    
    with httpx.Client(timeout=10.0) as client:
        response = client.request(
            method=method,
            url=url,
            params=params,
            json=json_data,
            headers=headers
        )
        response.raise_for_status()
        return response.json()
