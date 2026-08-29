# ADR-0001 — Camada MCP via FastMCP como única interface entre agente e API

## Status: Aceita
## Data: 2026-08-29

## Contexto
O agente se conecta à API industrial Tractian com 18 operações em 7 categorias. Precisamos
escolher como expor essas operações ao agente de IA.

## Decisão
Usar **MCP (Model Context Protocol) via FastMCP** como camada intermediária. Cada uma das
17 operações (excluindo getAsset que tem path vermelho) vira uma tool Python registrada
no servidor MCP. O agente se conecta ao servidor MCP via stdio ou HTTP, não diretamente
à API.

## Rationale
- **Padronização**: MCP já é suportado por todos os principais agentes (Claude, Copilot,
  LangChain, OpenCode). Trocar de framework de agente não requer reescrever as tools.
- **Separação de responsabilidades**: a camada MCP cuida de autenticação (headers),
  parsing do envelope de resposta e tratamento básico de erros; o agente cuida de decidir.
- **Testabilidade**: cada tool pode ser testada isoladamente via `__main__` (já temos o
  padrão no `tools.py` existente).
- **Uniformidade**: helper central `fetch_envelope` garante tratamento consistente dos modos
  probabilísticos (`complete/partial/inconclusive/conflict/unavailable`).

## Consequências
- Se a API de produção precisar de autenticação diferente (API key por empresa), a mudança
  se concentra no helper `client.py`, não nas tools.
- Se amanhã precisarmos de server-sent events ou streaming, o MCP suporta.
