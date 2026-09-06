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

## Juiz independente

O juiz LLM tem um namespace próprio, opcional. Definindo `JUDGE_API_KEY`,
`JUDGE_BASE_URL` e `JUDGE_MODEL`, quem avalia deixa de ser o mesmo modelo que
responde — autoavaliação infla nota, e um modelo tende a achar boa a resposta
que ele mesmo escreveria. Os fallbacks do juiz seguem o mesmo padrão numerado
(`JUDGE_FALLBACK_1_*`).

Sem `JUDGE_API_KEY`, o juiz usa a cadeia do agente, como antes.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv(Path(__file__).resolve().parent / ".env")

# Quantos fallbacks procurar no ambiente antes de desistir.
_MAX_FALLBACKS = 5

# Como pedir saída estruturada ao provedor. `function_calling` é o mais portátil:
# roteadores locais (omniroute) e gateways costumam repassar tool calling, mas
# nem sempre honram `json_schema` — quando não honram, devolvem prosa e o parse
# quebra com "Invalid JSON: expected value at line 1 column 1".
_METODO_PADRAO = os.getenv("LLM_STRUCTURED_METHOD", "function_calling")


# Namespaces de configuração: (prefixo do principal, prefixo dos fallbacks).
_NAMESPACES = {
    "agente": ("OPENAI", "LLM_FALLBACK"),
    "juiz": ("JUDGE", "JUDGE_FALLBACK"),
}


def _provedores(papel: str = "agente") -> list[dict]:
    """Lista ordenada de provedores para um papel: principal e depois fallbacks.

    O papel `juiz` cai para a cadeia do agente quando não está configurado —
    assim o comportamento antigo continua valendo sem nenhuma variável nova.
    """
    principal, fallback = _NAMESPACES.get(papel, _NAMESPACES["agente"])

    if papel != "agente" and not os.getenv(f"{principal}_API_KEY"):
        return _provedores("agente")

    provedores = [{
        "nome": _rotular(os.getenv(f"{principal}_BASE_URL", "")),
        "api_key": os.getenv(f"{principal}_API_KEY", ""),
        "base_url": os.getenv(f"{principal}_BASE_URL", "https://api.groq.com/openai/v1"),
        "model": os.getenv(f"{principal}_MODEL", "openai/gpt-oss-20b"),
        "metodo": os.getenv(f"{principal}_STRUCTURED_METHOD", _METODO_PADRAO),
    }]

    for i in range(1, _MAX_FALLBACKS + 1):
        chave = os.getenv(f"{fallback}_{i}_API_KEY")
        if not chave:
            break  # numeração é contígua: o primeiro buraco encerra
        base_url = os.getenv(f"{fallback}_{i}_BASE_URL", "")
        provedores.append({
            "nome": _rotular(base_url),
            "api_key": chave,
            "base_url": base_url,
            "model": os.getenv(f"{fallback}_{i}_MODEL", ""),
            "metodo": os.getenv(f"{fallback}_{i}_STRUCTURED_METHOD", _METODO_PADRAO),
        })

    return [p for p in provedores if p["api_key"] and p["base_url"] and p["model"]]


def juiz_independente() -> bool:
    """True quando o juiz roda num provedor próprio, separado do agente."""
    return bool(os.getenv("JUDGE_API_KEY"))


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


def descrever_provedores(papel: str = "agente") -> list[str]:
    """`['groq:openai/gpt-oss-20b', 'openrouter:...']` — para a UI e o log."""
    return [f"{p['nome']}:{p['model']}" for p in _provedores(papel)]


def modelo_efetivo(mensagem) -> str | None:
    """Qual modelo REALMENTE respondeu, lido da resposta do provedor.

    Roteadores (omniroute, OpenRouter com `auto/`) escolhem o modelo por
    requisição: o slug que pedimos é um combo, não um modelo. Sem registrar o
    que respondeu de fato, toda métrica vira média sobre uma mistura
    desconhecida e a comparação entre versões perde o sentido — um ticket pode
    ter sido decidido por um modelo mais cauteloso que o do ticket ao lado.

    A resposta compatível com a API da OpenAI traz o modelo real em
    `response_metadata`, e os roteadores preenchem esse campo corretamente.
    """
    if mensagem is None:
        return None
    meta = getattr(mensagem, "response_metadata", None) or {}
    for chave in ("model_name", "model"):
        if meta.get(chave):
            return str(meta[chave])
    return None


def build_llm(temperature: float = 0.3, structured_output=None, include_raw: bool = False,
              papel: str = "agente"):
    """LLM pronto para uso, com fallback automático entre provedores.

    Args:
        temperature: temperatura do modelo.
        structured_output: modelo Pydantic para `with_structured_output`.
            Aplicado a CADA provedor da cadeia — sem isso o fallback devolveria
            texto livre quando entrasse em ação, quebrando quem espera o objeto.
        include_raw: devolve `{"raw", "parsed", "parsing_error"}` em vez do
            objeto. Necessário para ler qual modelo respondeu — o objeto
            estruturado sozinho descarta os metadados da resposta.
        papel: `"agente"` ou `"juiz"`. O juiz pode ter provedor próprio, para
            que quem avalia não seja o mesmo modelo que responde.

    Returns:
        Runnable do LangChain. Com um só provedor configurado, é o próprio
        ChatOpenAI; com mais, um runnable com `.with_fallbacks(...)`.

    Raises:
        RuntimeError: se nenhum provedor estiver configurado.
    """
    provedores = _provedores(papel)
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
        if not structured_output:
            return llm
        # O método vem por provedor: cada gateway honra um subconjunto diferente.
        return llm.with_structured_output(
            structured_output,
            method=p.get("metodo") or _METODO_PADRAO,
            include_raw=include_raw,
        )

    principal = _montar(provedores[0])
    reservas = [_montar(p) for p in provedores[1:]]

    return principal.with_fallbacks(reservas) if reservas else principal
