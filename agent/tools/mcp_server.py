from mcp.server.mcpserver import MCPServer
from .client import tractian_request

mcp = MCPServer(name="tractian-tools")

# --- GRUPO 1: Contexto e Ativos ---

@mcp.tool()
def getCompany(companyId: str, seed: int | None = None) -> dict:
    """Consulta dados de uma empresa."""
    params = {"seed": seed} if seed else {}
    return tractian_request("GET", f"/companies/{companyId}", params=params)

@mcp.tool()
def listAssetsByCompany(companyId: str, seed: int | None = None) -> dict:
    """Lista ativos de uma empresa."""
    params = {"seed": seed} if seed else {}
    return tractian_request("GET", f"/companies/{companyId}/assets", params=params)

@mcp.tool()
def getCurrentUser(user_id: str) -> dict:
    """Consulta perfil do usuário logado (requer x-user-id)."""
    return tractian_request("GET", "/users/me", user_id=user_id)

@mcp.tool()
def getAsset(assetId: str, seed: int | None = None) -> dict:
    """Consulta detalhes de um ativo."""
    params = {"seed": seed} if seed else {}
    return tractian_request("GET", f"/assets/{assetId}", params=params)

@mcp.tool()
def updateAssetConfig(
    assetId: str, 
    user_id: str, 
    justification: str, 
    changes: dict
) -> dict:
    """Atualiza configuração de um ativo. Exige justificação."""
    return tractian_request(
        "PATCH", 
        f"/assets/{assetId}", 
        user_id=user_id, 
        json_data={"justification": justification, "changes": changes}
    )

@mcp.tool()
def listAnalyses(assetId: str, status: str | None = None, seed: int | None = None) -> dict:
    """Lista análises de um ativo."""
    params = {}
    if status: params["status"] = status
    if seed: params["seed"] = seed
    return tractian_request("GET", f"/assets/{assetId}/analyses", params=params)

# --- GRUPO 2: Dados técnicos e Análises ---

@mcp.tool()
def getAnalysis(analysisId: str, seed: int | None = None) -> dict:
    """Consulta detalhes de uma análise."""
    params = {"seed": seed} if seed else {}
    return tractian_request("GET", f"/analyses/{analysisId}", params=params)

@mcp.tool()
def reprocessAnalysis(analysisId: str, user_id: str, justification: str, params: dict | None = None) -> dict:
    """Reprocessa análise. Exige justificação."""
    return tractian_request(
        "POST",
        f"/analyses/{analysisId}/reprocess",
        user_id=user_id,
        json_data={"justification": justification, "params": params or {}}
    )

@mcp.tool()
def requestSpecialistAnalysis(analysisId: str, user_id: str, justification: str, params: dict | None = None) -> dict:
    """Solicita análise especialista. Exige justificação."""
    return tractian_request(
        "POST",
        f"/analyses/{analysisId}/request-specialist",
        user_id=user_id,
        json_data={"justification": justification, "params": params or {}}
    )

@mcp.tool()
def getBaseline(assetId: str, point_id: str | None = None, seed: int | None = None) -> dict:
    """Consulta baseline de um ativo."""
    params = {}
    if point_id: params["point_id"] = point_id
    if seed: params["seed"] = seed
    return tractian_request("GET", f"/assets/{assetId}/baseline", params=params)

@mcp.tool()
def getRmsSeries(assetId: str, point_id: str | None = None, seed: int | None = None) -> dict:
    """Consulta série RMS de um ativo."""
    params = {}
    if point_id: params["point_id"] = point_id
    if seed: params["seed"] = seed
    return tractian_request("GET", f"/assets/{assetId}/rms", params=params)

@mcp.tool()
def getSpectrum(assetId: str, point_id: str | None = None, seed: int | None = None) -> dict:
    """Consulta espectro de um ativo."""
    params = {}
    if point_id: params["point_id"] = point_id
    if seed: params["seed"] = seed
    return tractian_request("GET", f"/assets/{assetId}/spectrum", params=params)

@mcp.tool()
def getDataQuality(assetId: str, seed: int | None = None) -> dict:
    """Consulta qualidade dos dados de um ativo."""
    params = {"seed": seed} if seed else {}
    return tractian_request("GET", f"/assets/{assetId}/data-quality", params=params)

# --- GRUPO 3: Modelos, Conhecimento e Ações ---

@mcp.tool()
def getModel(modelId: str, seed: int | None = None) -> dict:
    """Consulta detalhes de um modelo."""
    params = {"seed": seed} if seed else {}
    return tractian_request("GET", f"/models/{modelId}", params=params)

@mcp.tool()
def requestRetraining(modelId: str, user_id: str, justification: str, params: dict | None = None) -> dict:
    """Solicita retreinamento de modelo. Exige justificação."""
    return tractian_request(
        "POST",
        f"/models/{modelId}/request-retraining",
        user_id=user_id,
        json_data={"justification": justification, "params": params or {}}
    )

@mcp.tool()
def searchKnowledge(q: str, type: str | None = None, seed: int | None = None) -> dict:
    """Busca no conhecimento."""
    params = {"q": q}
    if type: params["type"] = type
    if seed: params["seed"] = seed
    return tractian_request("GET", "/knowledge/search", params=params)

@mcp.tool()
def getKnowledgeDoc(docId: str, seed: int | None = None) -> dict:
    """Consulta documento de conhecimento."""
    params = {"seed": seed} if seed else {}
    return tractian_request("GET", f"/knowledge/{docId}", params=params)

@mcp.tool()
def escalateCase(caseId: str, user_id: str, justification: str, params: dict | None = None) -> dict:
    """Escala um chamado para humano. Exige justificação."""
    return tractian_request(
        "POST",
        f"/cases/{caseId}/escalate",
        user_id=user_id,
        json_data={"justification": justification, "params": params or {}}
    )
