"""Cliente MCP — como o agente fala com a API industrial (ADR-0001).

O agente **não** chama a API por HTTP direto. Ele sobe o servidor MCP
(`agent/tools/mcp_server.py`) como subprocesso, faz o handshake do protocolo e
invoca as tools por nome. É a camada que o ADR-0001 descreve.

## Por que uma ponte síncrona

O SDK do MCP é assíncrono; os nós do LangGraph e o Streamlit são síncronos.
Este módulo mantém um event loop num thread daemon e expõe `call_tool(...)`
síncrono. A sessão é **persistente**: o subprocesso sobe uma vez e é reusado por
todas as chamadas, em vez de um processo por tool.

## Transporte

stdio, o padrão do MCP. Auto-contido: não há serviço extra para subir antes de
rodar o agente. Trocar para HTTP é mudar só `_abrir_sessao`.
"""
from __future__ import annotations

import asyncio
import atexit
import json
import os
import sys
import threading
from typing import Any

_TIMEOUT_S = float(os.getenv("MCP_CALL_TIMEOUT", "30"))

_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None
_session: Any = None
_encerrar: asyncio.Event | None = None
_lock = threading.Lock()


class MCPUnavailable(RuntimeError):
    """O servidor MCP não pôde ser iniciado ou não respondeu."""


async def _abrir_sessao(pronto: asyncio.Future) -> None:
    """Sobe o servidor MCP e mantém a sessão viva até o encerramento.

    Os transportes do MCP são context managers assíncronos: precisam continuar
    abertos enquanto a sessão for usada. Por isso esta corrotina entra nos
    contextos, sinaliza que está pronta e fica bloqueada num Event — em vez de
    abrir e fechar a conexão a cada chamada.
    """
    global _session, _encerrar
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    try:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "agent.tools.mcp_server"],
            env=dict(os.environ),
        )
        async with stdio_client(params) as (leitura, escrita):
            async with ClientSession(leitura, escrita) as sessao:
                await sessao.initialize()
                _session = sessao
                _encerrar = asyncio.Event()
                pronto.get_loop().call_soon_threadsafe(pronto.set_result, True)
                await _encerrar.wait()
    except Exception as e:  # pragma: no cover - falha de inicialização
        if not pronto.done():
            pronto.get_loop().call_soon_threadsafe(pronto.set_exception, e)
    finally:
        _session = None


def _garantir_sessao() -> None:
    """Inicia o loop e a sessão MCP na primeira chamada (idempotente)."""
    global _loop, _thread

    if _session is not None:
        return

    with _lock:
        if _session is not None:
            return

        _loop = asyncio.new_event_loop()
        _thread = threading.Thread(
            target=_loop.run_forever, name="mcp-client-loop", daemon=True
        )
        _thread.start()

        pronto: asyncio.Future = asyncio.run_coroutine_threadsafe(
            asyncio.sleep(0), _loop
        ).result() or None  # aquece o loop
        futuro_pronto = asyncio.Future(loop=_loop)
        asyncio.run_coroutine_threadsafe(_abrir_sessao(futuro_pronto), _loop)

        try:
            # Espera o handshake do protocolo terminar.
            asyncio.run_coroutine_threadsafe(
                asyncio.wait_for(asyncio.shield(futuro_pronto), _TIMEOUT_S), _loop
            ).result(_TIMEOUT_S + 5)
        except Exception as e:
            raise MCPUnavailable(
                f"não foi possível iniciar o servidor MCP: {type(e).__name__}: {e}\n"
                f"  - o pacote `mcp` está instalado? `uv pip install -e .`\n"
                f"  - teste isolado: python -m agent.tools.mcp_server"
            ) from e

        atexit.register(fechar)


def _extrair_envelope(resultado: Any) -> dict:
    """Converte o retorno de uma tool MCP no envelope {mode, notes, data}.

    O MCP devolve conteúdo tipado; as nossas tools retornam dict, que o servidor
    serializa como texto JSON. `structuredContent`, quando presente, já vem
    desserializado.
    """
    estruturado = getattr(resultado, "structuredContent", None)
    if isinstance(estruturado, dict):
        # O SDK embrulha retornos não-objeto em {"result": ...}
        return estruturado.get("result", estruturado)

    for item in getattr(resultado, "content", None) or []:
        texto = getattr(item, "text", None)
        if not texto:
            continue
        try:
            return json.loads(texto)
        except json.JSONDecodeError:
            return {"mode": "unavailable", "notes": texto[:200], "data": None}

    return {"mode": "unavailable", "notes": "tool MCP não retornou conteúdo", "data": None}


def call_tool(nome: str, **argumentos) -> dict:
    """Invoca uma tool MCP pelo nome e devolve o envelope da API.

    Cada chamada vira um span no Phoenix. Isso é necessário porque a requisição
    HTTP em si acontece **dentro do subprocesso** do servidor MCP, que não é
    instrumentado — sem este span a fase de investigação voltaria a ser invisível.

    Args:
        nome: operationId da tool (`getBaseline`, `listAnalyses`, ...)
        **argumentos: parâmetros da tool

    Raises:
        MCPUnavailable: se o servidor não subir ou a chamada estourar o timeout.
    """
    _garantir_sessao()
    if _session is None or _loop is None:
        raise MCPUnavailable("sessão MCP indisponível")

    limpos = {k: v for k, v in argumentos.items() if v is not None}

    with _span(nome, limpos) as span:
        futuro = asyncio.run_coroutine_threadsafe(
            _session.call_tool(nome, limpos), _loop
        )
        try:
            resultado = futuro.result(_TIMEOUT_S)
        except Exception as e:
            raise MCPUnavailable(
                f"tool MCP '{nome}' falhou: {type(e).__name__}: {e}"
            ) from e

        if getattr(resultado, "isError", False):
            detalhe = _extrair_envelope(resultado)
            raise MCPUnavailable(f"tool MCP '{nome}' retornou erro: {detalhe}")

        envelope = _extrair_envelope(resultado)
        if span is not None:
            span.set_attribute("envelope.mode", str(envelope.get("mode")))
            if envelope.get("notes"):
                span.set_attribute("envelope.notes", str(envelope["notes"])[:200])
        return envelope


def _span(nome: str, argumentos: dict):
    """Context manager do span de uma chamada MCP (no-op sem tracing)."""
    from contextlib import contextmanager

    from ..logging.phoenix import get_tracer

    tracer = get_tracer()

    @contextmanager
    def _ctx():
        if tracer is None:
            yield None
            return
        with tracer.start_as_current_span(f"mcp.{nome}") as span:
            span.set_attribute("mcp.tool", nome)
            span.set_attribute("mcp.transport", "stdio")
            for chave, valor in argumentos.items():
                span.set_attribute(f"mcp.arg.{chave}", str(valor)[:120])
            yield span

    return _ctx()


def list_tools() -> list[str]:
    """Nomes das tools que o servidor MCP expõe. Útil em teste e diagnóstico."""
    _garantir_sessao()
    if _session is None or _loop is None:
        raise MCPUnavailable("sessão MCP indisponível")
    futuro = asyncio.run_coroutine_threadsafe(_session.list_tools(), _loop)
    return [t.name for t in futuro.result(_TIMEOUT_S).tools]


def fechar() -> None:
    """Encerra a sessão e o subprocesso do servidor MCP."""
    global _loop, _thread
    if _loop is None:
        return
    try:
        if _encerrar is not None:
            _loop.call_soon_threadsafe(_encerrar.set)
        _loop.call_soon_threadsafe(_loop.stop)
    except Exception:
        pass
    _loop = None
    _thread = None
