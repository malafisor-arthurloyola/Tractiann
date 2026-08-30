"""Integração com Phoenix (Arize) — tracing open source.

Phoenix é o substituto open source e gratuito da LangSmith. Ele recebe traces
via OpenTelemetry (OTLP) e mostra um dashboard local.

Arquitetura:
  - Servidor Phoenix: roda via Docker (`phoenix-up` no Makefile), expõe OTLP em :6006.
  - Cliente (este módulo): instrumenta as chamadas do LangChain/LangGraph e envia
    os spans para o servidor.

Ativação: a instrumentação é opcional. Ela só faz efeito se `PHOENIX_ENABLED=1`
e o servidor estiver no ar. Caso contrário, tudo continua funcionando normalmente
(sem tracing), sem afetar o agente.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_PHOENIX_ENDPOINT = os.getenv("PHOENIX_ENDPOINT", "http://localhost:6006")
_TRACER_NAME = os.getenv("PHOENIX_TRACER", "tractian-agent")


def _is_enabled() -> bool:
    return os.getenv("PHOENIX_ENABLED", "0") == "1"


def is_within_trace() -> bool:
    """True se já estamos dentro de um trace ativo (exceto o nó raiz)."""
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        if span is None or span.get_span_context().trace_id == 0:
            return False
        # Se há um span ativo, estamos dentro de um trace
        return span.get_span_context().trace_id != 0
    except Exception:
        return False


def setup_phoenix_tracing(force: bool = False) -> bool:
    """Configura o tracing OpenTelemetry apontando para o Phoenix.

    Returns:
        True se instrumentou, False se desativado ou falhou.
    """
    if not force and not _is_enabled():
        return False

    try:
        from opentelemetry import trace as otel_trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from openinference.instrumentation.langchain import LangChainInstrumentor

        resource = Resource(attributes={"service.name": _TRACER_NAME})

        # Protocolo HTTP (mais simples no Windows/Docker)
        endpoint = f"{_PHOENIX_ENDPOINT}/v1/traces"
        exporter = OTLPSpanExporter(endpoint=endpoint)

        provider = TracerProvider(resource=resource)
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)
        otel_trace.set_tracer_provider(provider)

        LangChainInstrumentor().instrument()
        return True
    except Exception as e:
        print(f"[phoenix] Instrumentação não ativada ({e})")
        return False


def run_in_phoenix_trace(thread_id: str, ticket_id: str):
    """Context manager: cria um trace raiz no Phoenix para uma execução.

    Uso:
        with run_in_phoenix_trace("thread-1", "TKT-INV-07"):
            result = agent_graph.invoke(...)
    """
    if not _is_enabled():
        from contextlib import nullcontext
        return nullcontext()

    from opentelemetry import trace
    tracer = trace.get_tracer(_TRACER_NAME)

    class _Ctx:
        def __enter__(self):
            span = tracer.start_span(f"ticket:{ticket_id}")
            span.set_attribute("ticket.ticket_id", ticket_id)
            span.set_attribute("thread.id", thread_id)
            # Torna o span raiz o span atual (spans filhos do LangChain penduram nele)
            self._token = trace.use_span(span, end_on_exit=True)
            self._token.__enter__()
            return span

        def __exit__(self, *exc):
            self._token.__exit__(None, None, None)
            return False

    return _Ctx()
