# ADR-0001 — Camada MCP como única interface entre agente e API

## Status: Aceita
## Data: 2026-08-29
## Revisado: 2026-09-06 (implementado — ver "Histórico")

## Contexto
O agente se conecta à API industrial Tractian com 18 operações em 7 categorias. Precisamos
escolher como expor essas operações ao agente de IA.

## Decisão
Usar **MCP (Model Context Protocol)** como camada intermediária. Cada uma das 18
operações da API vira uma tool registrada no servidor MCP (`agent/tools/mcp_server.py`).
O agente sobe esse servidor como subprocesso e conversa por **stdio**, usando o protocolo
MCP — não chama a API por HTTP direto.

```
nós do LangGraph
      ↓  call_tool("getBaseline", assetId=...)
agent/tools/mcp_client.py        ponte síncrona + span no Phoenix
      ↓  protocolo MCP sobre stdio
agent/tools/mcp_server.py        subprocesso: 18 tools
      ↓  agent/tools/client.py   (httpx: base URL, x-user-id, erro)
API industrial (:8000)
```

## Rationale
- **Padronização**: MCP é suportado pelos principais agentes (Claude, Copilot,
  LangChain, OpenCode). Trocar de framework de agente não requer reescrever as tools.
- **Separação de responsabilidades**: a camada MCP cuida de autenticação (headers),
  serialização do envelope e tratamento de erro; o agente cuida de decidir.
- **Testabilidade**: cada tool pode ser exercitada isoladamente com
  `python -m agent.tools.mcp_server`, sem subir o agente.
- **Uniformidade**: `client.py` centraliza o tratamento dos modos probabilísticos
  (`complete/partial/inconclusive/conflict/unavailable`).

## Consequências
- Se a API de produção precisar de autenticação diferente (API key por empresa), a
  mudança se concentra em `client.py`, dentro do servidor MCP.
- Se amanhã precisarmos de streaming, o MCP suporta.
- Os nós do grafo não conhecem URLs. `ACTION_TOOLS` em `nodes.py` mapeia a decisão do
  agente para a tool MCP correspondente.
- **Custo de observabilidade**: a requisição HTTP acontece dentro do subprocesso do
  servidor, que não é instrumentado. Por isso `mcp_client.call_tool` emite o span
  `mcp.<tool>` com o modo do envelope resultante — sem ele, a fase de investigação
  ficaria invisível no Phoenix.
- **Custo de latência**: um subprocesso a mais e o handshake do protocolo na primeira
  chamada. A sessão é persistente e reusada por toda a execução, então o custo é pago
  uma vez, não por tool.

## Alternativa considerada e rejeitada
**HTTP direto do agente para a API** (era o que o código de fato fazia até 06/09/2026,
enquanto este ADR já dizia MCP). Mais simples e com um span HTTP nativo por chamada, mas
abre mão da padronização e da portabilidade entre frameworks, que são o motivo de existir
desta decisão. Mantido apenas como detalhe interno do servidor MCP.

## Histórico
- **2026-08-29** — decisão registrada.
- **2026-09-06** — auditoria constatou que a decisão **nunca havia sido implementada**:
  `mcp_server.py` existia com as 18 tools, mas o pacote `mcp` não estava instalado
  (o `pyproject.toml` da raiz nunca era instalado — ver `Ambiente e Reprodutibilidade`),
  o módulo não tinha bloco `__main__` (rodado como módulo, encerrava sem subir servidor),
  e **nenhum arquivo do projeto o importava**: os nós chamavam `tractian_request` direto.
  Este ADR descrevia uma arquitetura inexistente.
  Corrigido: pacote instalado, `__main__` adicionado, cliente síncrono criado
  (`mcp_client.py`) e todos os nós migrados. A decisão agora vale.

  Nota: o import `from mcp.server.mcpserver import MCPServer` estava **correto** — no
  `mcp` 2.x o `FastMCP` foi renomeado para `MCPServer`. A suspeita inicial de que o
  caminho estava errado partia da API do `mcp` 1.x.
