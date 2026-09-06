"""Construção do LLM, com cadeia de fallback entre provedores.

Groq, OpenRouter, OpenAI e qualquer gateway compatível com a API da OpenAI
(incluindo roteadores pessoais) falam o mesmo protocolo — muda só a `base_url`.
Isso permite encadear provedores: quando o primeiro estoura a cota ou falha, a
chamada cai automaticamente no seguinte, sem o agente saber.

## Configuração

O provedor principal continua nas variáveis de sempre:

    OPENAI_API_KEY=...
    OPENAI_BASE_URL=https://api.groq.com/openai/v1
    OPENAI_MODEL=openai/gpt-oss-20b

Os fallbacks são numerados a partir de 1, e a busca para no primeiro número
ausente:

    LLM_FALLBACK_1_API_KEY=sk-or-...
    LLM_FALLBACK_1_BASE_URL=https://openrouter.ai/api/v1
    LLM_FALLBACK_1_MODEL=meta-llama/llama-3.3-70b-instruct

    LLM_FALLBACK_2_API_KEY=...
    LLM_FALLBACK_2_BASE_URL=...
    LLM_FALLBACK_2_MODEL=...

Sem nenhum `LLM_FALLBACK_*`, o comportamento é idêntico ao de antes.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv(Path(__file__).resolve().parent / ".env")

# Quantos fallbacks procurar no ambiente antes de desistir.
_MAX_FALLBACKS = 5


def _provedores() -> list[dict]:
    """Lista ordenada de provedores: o principal e depois os fallbacks."""
    provedores = [{
        "nome": _rotular(os.getenv("OPENAI_BASE_URL", "")),
        "api_key": os.getenv("OPENAI_API_KEY", ""),
        "base_url": os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1"),
        "model": os.getenv("OPENAI_MODEL", "openai/gpt-oss-20b"),
    }]

    for i in range(1, _MAX_FALLBACKS + 1):
        chave = os.getenv(f"LLM_FALLBACK_{i}_API_KEY")
        if not chave:
            break  # numeração é contígua: o primeiro buraco encerra
        base_url = os.getenv(f"LLM_FALLBACK_{i}_BASE_URL", "")
        provedores.append({
            "nome": _rotular(base_url),
            "api_key": chave,
            "base_url": base_url,
            "model": os.getenv(f"LLM_FALLBACK_{i}_MODEL", ""),
        })

    return [p for p in provedores if p["api_key"] and p["base_url"] and p["model"]]


def _rotular(base_url: str) -> str:
    """Nome legível do provedor, deduzido da URL — só para log e trace."""
    u = (base_url or "").lower()
    if "groq" in u:
        return "groq"
    if "openrouter" in u:
        return "openrouter"
    if "api.openai.com" in u:
        return "openai"
    if not u:
        return "desconhecido"
    return u.split("//")[-1].split("/")[0]


def descrever_provedores() -> list[str]:
    """`['groq:openai/gpt-oss-20b', 'openrouter:...']` — para a UI e o log."""
    return [f"{p['nome']}:{p['model']}" for p in _provedores()]


def build_llm(temperature: float = 0.3, structured_output=None):
    """LLM pronto para uso, com fallback automático entre provedores.

    Args:
        temperature: temperatura do modelo.
        structured_output: modelo Pydantic para `with_structured_output`.
            Aplicado a CADA provedor da cadeia — sem isso o fallback devolveria
            texto livre quando entrasse em ação, quebrando quem espera o objeto.

    Returns:
        Runnable do LangChain. Com um só provedor configurado, é o próprio
        ChatOpenAI; com mais, um runnable com `.with_fallbacks(...)`.

    Raises:
        RuntimeError: se nenhum provedor estiver configurado.
    """
    provedores = _provedores()
    if not provedores:
        raise RuntimeError(
            "Nenhum provedor de LLM configurado. Defina OPENAI_API_KEY, "
            "OPENAI_BASE_URL e OPENAI_MODEL em agent/.env"
        )

    def _montar(p: dict):
        llm = ChatOpenAI(
            model=p["model"],
            base_url=p["base_url"],
            api_key=p["api_key"],
            temperature=temperature,
            max_retries=1,  # o retry longo atrasa o fallback; melhor cair logo
        )
        return llm.with_structured_output(structured_output) if structured_output else llm

    principal = _montar(provedores[0])
    reservas = [_montar(p) for p in provedores[1:]]

    return principal.with_fallbacks(reservas) if reservas else principal
