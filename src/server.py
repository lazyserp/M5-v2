import os
import logging
from typing import Optional
from dotenv import load_dotenv

load_dotenv(override=True)
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.parser.ast_parser import ASTParser, EXTENSION_MAP
from src.indexer.progressive_indexer import progressive_indexer
from src.indexer.git_manager import git_manager
from src.api.webhooks import webhook_router
from src.tools.hybrid_search import HybridRetriever, get_hybrid_retriever
from src.tools.dependency_graph import PersistentDependencyGraph

logger = logging.getLogger("m5")

# ── Feature flags (read from environment) ───────────────────────────────────
DEV_AGENT_MODE = os.getenv("M5_ENABLE_DEV_AGENT_MODE", "false").lower() == "true"
ADMIN_KEY = os.getenv("M5_ADMIN_KEY", "")

# ── Startup warning when dev mode is on ─────────────────────────────────────
if DEV_AGENT_MODE:
    import warnings
    warnings.warn(
        "[WARN] Dev agent mode is ON — M5 is invoking its own LLM and departing from "
        "the pure context-provider architecture. Do not enable in production.",
        stacklevel=1
    )

# ── Initialize FastAPI ───────────────────────────────────────────────────────
app = FastAPI(
    title="M5 v2 Context Engine API",
    description=(
        "A compliance-grade, permission-aware context engine. "
        "M5 retrieves and proves; it does not reason or answer by default."
    ),
    version="3.0.0"
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(webhook_router)

# ── Pydantic Models ───────────────────────────────────────────────────────────
class IndexRequest(BaseModel):
    workspace_root: str = "."
    org_id: str = Field(default="default_org", description="Enterprise organization identifier")
    dept_id: str = Field(default="default_dept", description="Department / team namespace")
    repo_id: str = Field(default="default_repo", description="Repository identifier")
    async_embedding: bool = Field(default=True, description="Enable non-blocking background vector embedding")

class GitIndexRequest(BaseModel):
    repo_url: str = Field(..., description="GitHub/GitLab repository URL")
    branch: Optional[str] = Field(default=None, description="Optional branch or tag name")
    access_token: Optional[str] = Field(default=None, description="Optional personal access token for private repos")
    dept_id: str = Field(default="engineering", description="Department / team namespace")
    async_embedding: bool = Field(default=True, description="Enable non-blocking background vector embedding")

class ContextRequest(BaseModel):
    query: str = Field(..., description="Natural language query or code snippet to search for")
    top_k: int = Field(default=5, description="Number of top code chunks to retrieve")
    expand_dependencies: bool = Field(default=True, description="Also fetch imports/dependencies of matched files")
    expand_depth: int = Field(default=1, description="How many hops deep to expand dependencies (1 or 2)")
    max_chunk_chars: Optional[int] = Field(default=None, description="Optional snippet limit. Defaults to full AST method/class body.")
    org_id: str = Field(default="default_org")
    dept_id: str = Field(default="default_dept")
    repo_id: str = Field(default="default_repo")
    requesting_user: Optional[str] = Field(default=None, description="Optional: human user identity")

# ── Static UI ─────────────────────────────────────────────────────────────────
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def serve_ui():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"message": "M5 v2 Context Engine API is online. Access /docs for Swagger UI."}

# ── Lifecycle ─────────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup_event():
    """Auto-index default workspace and vectorize 100% of codebase into Qdrant on startup."""
    from src.tools.vector_search import get_shared_embedder, VectorStore
    get_shared_embedder()

    workspace_root = os.getenv("WORKSPACE_ROOT", ".")
    org_id = os.getenv("DEFAULT_ORG_ID", "default_org")
    dept_id = os.getenv("DEFAULT_DEPT_ID", "default_dept")
    repo_id = os.getenv("DEFAULT_REPO_ID", "default_repo")

    print(f"\n[+] M5 Startup: Parsing & Vectorizing codebase '{workspace_root}' into Qdrant...", flush=True)
    files_count, blocks = progressive_indexer.tier0_instant_boot(
        workspace_root=workspace_root,
        org_id=org_id,
        dept_id=dept_id,
        repo_id=repo_id
    )

    if blocks:
        v_store = VectorStore(org_id=org_id, dept_id=dept_id, repo_id=repo_id)
        indexed_count = v_store.index_blocks(blocks, batch_size=64)
        print(f"[SUCCESS] Qdrant Vectorization Complete: {indexed_count} AST blocks permanently indexed.", flush=True)

    print(
        f"[+] M5 v2 Server Online: Ready to serve queries with 100% vectorized context.",
        flush=True
    )

# ── Health & Readiness ────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    return {
        "status": "online",
        "engine": "M5 v2 Context Engine",
        "version": "3.0.0",
        "dev_agent_mode": DEV_AGENT_MODE
    }

@app.get("/ready")
def readiness_check():
    """Readiness probe checking storage and indexing status."""
    return {
        "status": "ready",
        "engine": "M5 v2 Context Engine",
        "version": "3.0.0",
        "storage": "ok"
    }

# ── Remote HTTP MCP Endpoint (JSON-RPC 2.0) ──────────────────────────────────
@app.post("/mcp")
async def mcp_http_endpoint(request: Request):
    """
    Remote HTTP MCP transport (JSON-RPC 2.0).
    Usable by Copilot, Claude Code, ChatGPT, Cursor, and any HTTP MCP client.
    """
    from src.mcp_server import mcp_server
    try:
        req_json = await request.json()
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": f"Parse error: {str(e)}"}
        }

    auth_header = request.headers.get("Authorization", "").strip()
    api_key = None
    if auth_header.lower().startswith("bearer "):
        api_key = auth_header[7:].strip()
    elif auth_header.startswith("m5_"):
        api_key = auth_header.strip()

    response = mcp_server.handle_request(req_json, api_key_override=api_key)
    if response is None:
        return {"jsonrpc": "2.0", "result": None}
    return response

# ── Indexing ──────────────────────────────────────────────────────────────────
@app.get("/api/index/status")
def index_status_endpoint(
    org_id: str = "default_org",
    dept_id: str = "default_dept",
    repo_id: str = "default_repo"
):
    return progressive_indexer.get_status(org_id=org_id, dept_id=dept_id, repo_id=repo_id)

@app.post("/api/index")
def index_endpoint(req: IndexRequest):
    if not os.path.exists(req.workspace_root):
        raise HTTPException(status_code=400, detail=f"Path '{req.workspace_root}' does not exist.")

    file_count, blocks = progressive_indexer.tier0_instant_boot(
        workspace_root=req.workspace_root,
        org_id=req.org_id,
        dept_id=req.dept_id,
        repo_id=req.repo_id
    )

    if req.async_embedding:
        progressive_indexer.start_background_embedding(
            blocks=blocks,
            org_id=req.org_id,
            dept_id=req.dept_id,
            repo_id=req.repo_id
        )
        msg = f"Tier-0 catalog built in <1s. Background embedding queued for {len(blocks)} blocks."
    else:
        retriever = get_hybrid_retriever(org_id=req.org_id, dept_id=req.dept_id, repo_id=req.repo_id)
        retriever.index_blocks(blocks)
        msg = f"Synchronously indexed {len(blocks)} blocks into Graph and Vector Stores."

    return {
        "status": "success",
        "org_id": req.org_id,
        "dept_id": req.dept_id,
        "repo_id": req.repo_id,
        "workspace_root": req.workspace_root,
        "files_cataloged": file_count,
        "blocks_extracted": len(blocks),
        "message": msg
    }

@app.post("/api/index/git")
def git_index_endpoint(req: GitIndexRequest):
    """Clones any remote GitHub/GitLab repository URL and indexes it."""
    try:
        dest_folder, org_id, repo_id = git_manager.clone_or_pull(
            repo_url=req.repo_url,
            branch=req.branch,
            access_token=req.access_token
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    file_count, blocks = progressive_indexer.tier0_instant_boot(
        workspace_root=dest_folder,
        org_id=org_id,
        dept_id=req.dept_id,
        repo_id=repo_id
    )

    if req.async_embedding:
        progressive_indexer.start_background_embedding(
            blocks=blocks,
            org_id=org_id,
            dept_id=req.dept_id,
            repo_id=repo_id
        )
        msg = (
            f"Cloned '{req.repo_url}'. Tier-0 catalog ready "
            f"({file_count} files, {len(blocks)} blocks). Background vector embedding queued."
        )
    else:
        retriever = get_hybrid_retriever(org_id=org_id, dept_id=req.dept_id, repo_id=repo_id)
        retriever.index_blocks(blocks)
        msg = f"Cloned '{req.repo_url}' and synchronously indexed {len(blocks)} blocks."

    return {
        "status": "success",
        "repo_url": req.repo_url,
        "org_id": org_id,
        "dept_id": req.dept_id,
        "repo_id": repo_id,
        "local_path": dest_folder,
        "files_cataloged": file_count,
        "blocks_extracted": len(blocks),
        "message": msg
    }

# ── Core Context Endpoint (the flagship) ──────────────────────────────────────
@app.post("/api/context")
def context_endpoint(req: ContextRequest):
    """
    One call → ranked + graph-expanded context bundle.
    This is the primary integration surface for any LLM that isn't already an MCP client.
    """
    from src.context.context_engine import get_context

    bundle = get_context(
        query=req.query,
        top_k=req.top_k,
        expand_dependencies=req.expand_dependencies,
        expand_depth=req.expand_depth,
        max_chunk_chars=req.max_chunk_chars,
        org_id=req.org_id,
        dept_id=req.dept_id,
        repo_id=req.repo_id,
        requesting_user=req.requesting_user,
        caller_identity="api_user",
    )
    return bundle

# ── Customizations (skills / rules) ──────────────────────────────────────────
@app.get("/api/customizations/rules")
def customizations_rules_endpoint():
    from src.parser.customizations import customization_manager
    rules = customization_manager.load_rules()
    return {"rules": rules, "has_rules": bool(rules)}

@app.get("/api/customizations/skills")
def customizations_skills_endpoint():
    from src.parser.customizations import customization_manager
    return {"skills": customization_manager.list_skills()}

@app.get("/api/customizations/skills/{skill_name}")
def customizations_skill_detail_endpoint(skill_name: str):
    from src.parser.customizations import customization_manager
    return customization_manager.load_skill(skill_name)
