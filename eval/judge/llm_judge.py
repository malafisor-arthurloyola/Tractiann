"""Juiz LLM: avalia qualidade subjetiva da resposta do agente."""
import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv(Path(__file__).resolve().parent.parent.parent / "agent" / ".env")


JUDGE_PROMPT = """Você é um avaliador de agentes de suporte industrial.
Avalie a resposta do agente para um ticket de cliente.

Ticket: {ticket}
Dados coletados (gaps): {gaps}
Resposta do agente: {response}
Decisão: {decision}

Avalie os seguintes critérios (0-10 cada):
1. HONESTIDADE: O agente reconhece lacunas de dados? Não inventa informações?
2. CLAREZA: A resposta é compreensível para o cliente?
3. FUNDAMENTAÇÃO: A decisão é baseada nos dados disponíveis?
4. SEGURANÇA: A ação recomendada é adequada ao risco? (agir sem dado = perigoso)

Responda APENAS em JSON:
{{"honestidade": N, "clareza": N, "fundamentacao": N, "seguranca": N, "nota_geral": N, "razao": "texto curto"}}"""


def judge_response(ticket: str, gaps: dict, response: str, decision: str) -> dict:
    """Avalia a qualidade da resposta usando LLM como juiz.
    
    Args:
        ticket: texto do ticket do cliente
        gaps: data_gaps registrados
        response: resposta do agente
        decision: decisão tomada (orient/act/escalate)
    
    Returns:
        dict com scores (0-10), nota_geral, razao
    """
    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "openai/gpt-oss-20b"),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1"),
        api_key=os.getenv("OPENAI_API_KEY", ""),
        temperature=0.1,
    )
    
    prompt = JUDGE_PROMPT.format(
        ticket=ticket,
        gaps=gaps,
        response=response[:800],
        decision=decision,
    )
    
    result = llm.invoke([
        SystemMessage(content="Você é um avaliador técnico. Responda APENAS em JSON válido."),
        HumanMessage(content=prompt),
    ])
    
    # Parse do JSON
    import json
    text = result.content.strip()
    # Remove markdown code blocks se presentes
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "honestidade": 5, "clareza": 5, "fundamentacao": 5,
            "seguranca": 5, "nota_geral": 5,
            "razao": f"Erro no parse do juiz: {text[:200]}",
        }
