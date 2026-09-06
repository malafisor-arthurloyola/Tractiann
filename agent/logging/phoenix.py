"""Integração com Phoenix (Arize) — tracing open source.

Phoenix é o substituto open source e gratuito da LangSmith. Ele recebe traces
via OpenTelemetry (OTLP) e mostra um dashboard local em :6006.

Arquitetura:
  - Servidor Phoenix: roda via Docker (`make up-obs`), expõe OTLP em :6006 e
    persiste os traces no Postgres (schema `phoenix`).
  - Cliente (este módulo): instrumenta LangChain/LangGraph **e** o cliente HTTP
    httpx, e envia os spans para o servidor.

Instrumentar o httpx é o que torna a fase de investigação visível: sem isso o
Phoenix mostra o raciocínio do LLM mas não as chamadas à API industrial, que é
justamente onde a evidência (ou a falta dela) aparece.

Ativação: `PHOENIX_ENABLED=1` no `agent/.env`. Se estiver ligado e a
instrumentação falhar, este módulo **grita** — a versão anterior engolia o erro
em silêncio e o projeto passou semanas achando que tinha tracing sem ter.
"""
import atexit
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_PHOENIX_ENDPOINT = os.getenv("PHOENIX_ENDPOINT", "http://localhost:6006")

# Estado do processo: evita instrumentar duas vezes (a UI Streamlit reexecuta o
# script inteiro a cada interação) e guarda o provider para o flush final.
_tracer_provider = None
_instrumented = False


def _is_enabled() -> bool:
    return os.getenv("PHOENIX_ENABLED", "0") == "1"


def project_name() -> str:
    """Nome do projeto no Phoenix, versionado pelo AGENT_VERSION.

    Versionar aqui é o que permite comparar v1 vs v2 dentro do próprio dashboard
    — antes só dava para comparar no Postgres.
    """
    from ..version import AGENT_VERSION
    return os.getenv("PHOENIX_PROJECT", f"tractian-agent-{AGENT_VERSION}")


def setup_phoenix_tracing(force: bool = False) -> bool:
    """Instrumenta LangChain/LangGraph + httpx apontando para o Phoenix.

    Returns:
        True se instrumentou, False se está desativado por configuração.

    Raises:
        RuntimeError: se o tracing está LIGADO mas a instrumentação falhou.
            É proposital: falha silenciosa aqui é indistinguível de "não há o
            que tracear", e foi assim que o problema passou despercebido.
    """
    global _tracer_provider, _instrumented

    if not force and not _is_enabled():
        return False
    if _instrumented:
        return True

    try:
        from phoenix.otel import register
        from openinference.instrumentation.langchain import LangChainInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        _tracer_provider = register(
            project_name=project_name(),
            endpoint=f"{_PHOENIX_ENDPOINT}/v1/traces",
            # Não deixa o register instrumentar sozinho — fazemos abaixo, de
            # forma explícita, para incluir o httpx.
            auto_instrument=False,
            batch=True,
            set_global_tracer_provider=True,
        )

        LangChainInstrumentor().instrument(tracer_provider=_tracer_provider)
        # Torna visíveis as chamadas GET/POST à API industrial.
        HTTPXClientInstrumentor().instrument(tracer_provider=_tracer_provider)

        # O BatchSpanProcessor exporta em lote. Processos curtos (`make eval`)
        # terminam antes do lote sair e os spans se perdem em silêncio.
        atexit.register(flush)

        _instrumented = True
        return True
    except Exception as e:
        raise RuntimeError(
            f"PHOENIX_ENABLED=1 mas a instrumentação falhou: {type(e).__name__}: {e}\n"
            f"  - dependências instaladas? `uv pip install -e .`\n"
            f"  - servidor no ar? `make up-obs` e abra {_PHOENIX_ENDPOINT}\n"
            f"  - para rodar sem tracing, use PHOENIX_ENABLED=0"
        ) from e


def flush() -> None:
    """Força o envio dos spans pendentes. Chamado no atexit e no fim do runner."""
    if _tracer_provider is None:
        return
    try:
        _tracer_provider.force_flush()
    except Exception as e:  # pragma: no cover - best effort no shutdown
        print(f"[phoenix] flush falhou: {e}", file=sys.stderr)


def get_tracer():
    """Tracer do módulo, ou None quando o tracing está desligado.

    Os nós do grafo usam para anexar atributos de domínio aos spans.
    """
    if not _instrumented:
        return None
    from opentelemetry import trace
    return trace.get_tracer(project_name())


def _coerce(value):
    """Converte um valor para um tipo que o OpenTelemetry aceita."""
    if isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value]
    return str(value)


def record_node(name: str, **attrs) -> None:
    """Emite um span filho carregando os atributos de domínio de um nó.

    Por que um span próprio em vez de anotar o span do nó: o instrumentador do
    LangChain cria os spans `investigate`/`quality_check`/`decide` a partir de
    *callbacks*, fora do contexto OpenTelemetry em que o corpo do nó roda. Um
    `trace.get_current_span()` dentro do nó não devolve aquele span — os
    atributos iam parar no span pai, ou em lugar nenhum.

    O resultado no Phoenix é uma árvore assim:

        ticket:TKT-INV-06
          LangGraph
            quality_check                 (LangChain: input/output do nó)
              quality_check.evidence      (este: quality.verdict, evidence.*)

    Os atributos ficam filtráveis na busca do Phoenix, em vez de enterrados no
    JSON do `output.value`.
    """
    if not _instrumented:
        return
    try:
        from opentelemetry import trace
        tracer = trace.get_tracer(project_name())
        with tracer.start_as_current_span(name) as span:
            for key, value in attrs.items():
                if value is not None:
                    span.set_attribute(key, _coerce(value))
    except Exception:
        # Tracing nunca pode derrubar o agente.
        pass


def run_in_phoenix_trace(thread_id: str, ticket_id: str, **attrs):
    """Context manager: cria o span raiz de uma execução do agente.

    Uso:
        with run_in_phoenix_trace(thread_id, ticket_id, asset_id=...):
            result = agent_graph.invoke(...)
    """
    if not _instrumented:
        from contextlib import nullcontext
        return nullcontext()

    from opentelemetry import trace
    from ..version import AGENT_VERSION

    tracer = trace.get_tracer(project_name())

    class _Ctx:
        def __enter__(self):
            span = tracer.start_span(f"ticket:{ticket_id}")
            span.set_attribute("ticket.id", ticket_id)
            span.set_attribute("thread.id", thread_id)
            span.set_attribute("agent.version", AGENT_VERSION)
            for key, value in attrs.items():
                if value is not None:
                    span.set_attribute(key, str(value))
            # Torna o span raiz o span atual (os filhos do LangChain/httpx
            # penduram nele).
            self._token = trace.use_span(span, end_on_exit=True)
            self._token.__enter__()
            return span

        def __exit__(self, *exc):
            self._token.__exit__(None, None, None)
            return False

    return _Ctx()
