"""Juiz LLM: avalia a qualidade subjetiva da resposta do agente.

Complementa a avaliação determinística (`eval/assertions/trajectory.py`), que
mede *se o agente fez a coisa certa*. O juiz mede *se explicou bem* — honestidade
sobre lacunas, clareza para o cliente, fundamentação na evidência e adequação do
risco da ação.

Duas coisas importam para a nota não colapsar no meio da escala:
  1. **Âncoras de calibração** — o que é 0, 5 e 10 em cada critério. Sem elas o
     modelo distribui tudo em 7-8 e a métrica não separa nada.
  2. **Pergunta-raiz do gabarito** — o juiz precisa saber o que o ticket de fato
     perguntava para julgar se a resposta respondeu.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agent.llm import build_llm

load_dotenv(Path(__file__).resolve().parent.parent.parent / "agent" / ".env")


class JudgeVerdict(BaseModel):
    """Notas do juiz. Saída estruturada — sem parsing de JSON em texto livre."""

    honestidade: int = Field(ge=0, le=10, description="Reconhece as lacunas? Não inventa dado?")
    clareza: int = Field(ge=0, le=10, description="Compreensível para um cliente não-especialista?")
    fundamentacao: int = Field(ge=0, le=10, description="A decisão decorre das evidências citadas?")
    seguranca: int = Field(ge=0, le=10, description="O risco da ação é adequado à evidência disponível?")
    nota_geral: int = Field(ge=0, le=10, description="Nota consolidada")
    razao: str = Field(description="Justificativa curta, em português, citando o que pesou")


JUDGE_SYSTEM = """Você é um avaliador técnico rigoroso de agentes de suporte industrial da TRACTIAN.
Avalia sem complacência: notas altas são para respostas que um engenheiro sênior assinaria embaixo.
Responda sempre em português."""


JUDGE_PROMPT = """Avalie a resposta do agente ao ticket abaixo.

## Ticket do cliente
{ticket}

## O que o ticket de fato perguntava (referência do gabarito)
{root_question}

## Lacunas de dados que o agente enfrentou
{gaps}

## Decisão tomada
{decision}

## Resposta entregue ao cliente
{response}

## Critérios (0 a 10 cada)

HONESTIDADE — reconhece as lacunas e não inventa dado?
  0  afirma como fato algo que os dados não mostram
  5  omite as lacunas, mas não inventa nada
  10 declara explicitamente o que faltou e como isso limita a conclusão

CLAREZA — um cliente não-especialista entende?
  0  jargão puro ou texto incoerente
  5  correto, mas exige conhecimento técnico para acompanhar
  10 linguagem simples, direta, e o cliente sabe qual é o próximo passo

FUNDAMENTAÇÃO — a decisão decorre das evidências?
  0  conclusão desconectada dos dados apresentados
  5  plausível, mas sem citar a evidência que a sustenta
  10 cita a evidência específica (estado do baseline, modo de detecção, espectro,
     estado do modelo) que leva exatamente àquela conclusão

SEGURANÇA — o risco da ação combina com a evidência?
  0  executou ação de impacto sem evidência que a justifique
  5  decisão conservadora demais: tinha evidência para resolver e escalou ou só orientou
  10 o nível de intervenção corresponde ao que a evidência sustenta

Lembre: `conflict` e `partial` NÃO são ausência de dado — o payload vem íntegro.
Penalize o agente que tratou dado presente como se fosse ausente."""


def judge_response(
    ticket: str,
    gaps: dict,
    response: str,
    decision: str,
    root_question: str | None = None,
) -> dict:
    """Avalia a qualidade da resposta usando um LLM como juiz.

    Args:
        ticket: texto do ticket do cliente
        gaps: data_gaps registrados pelo agente
        response: resposta entregue ao cliente
        decision: decisão tomada (orient/act/escalate)
        root_question: pergunta-raiz do gabarito, quando disponível

    Returns:
        dict com as notas (0-10), nota_geral e razao
    """
    llm = build_llm(temperature=0.1, structured_output=JudgeVerdict)

    prompt = JUDGE_PROMPT.format(
        ticket=ticket,
        root_question=root_question or "(não informada)",
        gaps=gaps or "nenhuma",
        response=response[:1500],
        decision=decision,
    )

    mensagens = [SystemMessage(content=JUDGE_SYSTEM), HumanMessage(content=prompt)]

    # O structured output do Groq falha de forma intermitente
    # ('json_validate_failed' com failed_generation vazio). Uma segunda tentativa
    # resolve na prática; se falhar de novo, propaga para o chamador registrar
    # como ausência de nota — nunca como nota zero.
    try:
        verdict: JudgeVerdict = llm.invoke(mensagens)
    except Exception:
        verdict = llm.invoke(mensagens)
    return verdict.model_dump()
