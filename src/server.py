import os
import time
import logging
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv(override=True)
from fastapi import FastAPI, HTTPException, Request, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.logger import setup_m5_logger
from src.parser.ast_parser import ASTParser, EXTENSION_MAP
from src.indexer.progressive_indexer import progressive_indexer
from src.indexer.git_manager import git_manager
from src.api.webhooks import webhook_router
from src.tools.hybrid_search import HybridRetriever, get_hybrid_retriever
from src.tools.dependency_graph import PersistentDependencyGraph
from src.auth import verify_api_key, verify_admin_key, create_api_key, list_api_keys, revoke_api_key

logger = setup_m5_logger("m5.server")

# ── Feature flags ─────────────────────────────────────────────────────────────
DEV_AGENT_MODE = os.getenv("M5_ENABLE_DEV_AGENT_MODE", "false").lower() == "true"
ADMIN_KEY = os.getenv("M5_ADMIN_KEY", "")

if DEV_AGENT_MODE:
    logger.warning("Dev agent mode is ON — M5 is invoking its own LLM. Do not enable in production.")

if not ADMIN_KEY:
    logger.warning(
        "M5_ADMIN_KEY is not set in .env — admin endpoints and webhook security are disabled. "
        "Set a strong random value before sharing M5 with anyone."
    )

# ── CORS ──────────────────────────────────────────────────────────────────────
# Plain English: who is allowed to call M5 from a browser?
# By default, only localhost (your own machine). You can add more origins in .env:
#   M5_CORS_ORIGINS=https://yourdashboard.com,https://app.yourcompany.com
_raw_origins = os.getenv("M5_CORS_ORIGINS", "")
if _raw_origins.strip():
    CORS_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]
else:
    # Safe default: only local origins. Never allow "*" in production.
    CORS_ORIGINS = [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ]

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Smart startup — only re-indexes if the Git commit changed since last run.

    Plain English:
    - On first run: M5 reads all files, builds the index, saves the commit SHA.
    - On later restarts: M5 checks the current commit. If it hasn't changed, it
      skips re-indexing entirely (startup goes from ~60s to ~2s).
    - If the commit changed (someone pushed code), it re-indexes only then.
    """
    from src.tools.vector_search import get_shared_embedder, VectorStore
    from src.indexer.progressive_indexer import _detect_git_commit

    logger.info("Initializing ONNX embedding model (BAAI/bge-small-en-v1.5)...")
    get_shared_embedder()

    auto_index = os.getenv("AUTO_INDEX", os.getenv("INDEX_ON_STARTUP", "true")).strip().lower() in ("true", "1", "yes")

    if not auto_index:
        logger.info("Startup repository indexing skipped (AUTO_INDEX is disabled).")
        logger.info("M5 v2 Context Engine Server Online on port 8000.")
    else:
        workspace_root = os.getenv("WORKSPACE_ROOT", ".")
        if os.path.exists("/workspace") and not os.path.exists(workspace_root):
            workspace_root = "/workspace"

        org_id = os.getenv("DEFAULT_ORG_ID", "default_org")
        dept_id = os.getenv("DEFAULT_DEPT_ID", "default_dept")
        repo_id = os.getenv("DEFAULT_REPO_ID", "default_repo")

        # Check what commit was last indexed
        current_commit = _detect_git_commit(workspace_root)
        existing_status = progressive_indexer.get_status(org_id=org_id, dept_id=dept_id, repo_id=repo_id)
        last_commit = existing_status.get("commit_sha")
        already_indexed = existing_status.get("total_blocks", 0) > 0

        if already_indexed and current_commit and current_commit == last_commit:
            logger.info(
                f"Skipping re-index: workspace '{workspace_root}' is up-to-date at commit {current_commit[:8]}. "
                f"({existing_status['total_blocks']} blocks already indexed)"
            )
            logger.info("M5 v2 Context Engine Server Online on port 8000.")
        else:
            if already_indexed and current_commit and last_commit and current_commit != last_commit:
                logger.info(
                    f"Commit changed ({last_commit[:8] if last_commit else 'unknown'} → {current_commit[:8]}). "
                    f"Re-indexing workspace '{workspace_root}'..."
                )
            else:
                logger.info(f"First-time indexing workspace '{workspace_root}'...")

            files_count, blocks = progressive_indexer.tier0_instant_boot(
                workspace_root=workspace_root,
                org_id=org_id,
                dept_id=dept_id,
                repo_id=repo_id
            )

            if blocks:
                v_store = VectorStore(org_id=org_id, dept_id=dept_id, repo_id=repo_id)
                indexed_count = v_store.index_blocks(blocks, batch_size=64)
                logger.info(f"Qdrant vectorization complete: {indexed_count} AST blocks indexed.")

            logger.info("M5 v2 Context Engine Server Online on port 8000.")

    try:
        yield
    finally:
        try:
            from src.audit.telemetry import flush_telemetry
            flush_telemetry()
        except Exception:
            pass


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="M5 v2 Context Engine API",
    description=(
        "A permission-aware code context engine. "
        "M5 retrieves and proves; it does not reason or answer by default."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── Request logging ───────────────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start_time) * 1000, 2)
    path = request.url.path
    if path not in ("/health", "/ready"):
        logger.info(f"{request.method} {path} -> status={response.status_code} elapsed={duration_ms}ms")
    response.headers["X-Process-Time"] = f"{duration_ms}ms"
    return response

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(webhook_router)

# ── Pydantic Models ───────────────────────────────────────────────────────────
class IndexRequest(BaseModel):
    workspace_root: str = "."
    org_id: str = Field(default="default_org")
    dept_id: str = Field(default="default_dept")
    repo_id: str = Field(default="default_repo")
    async_embedding: bool = Field(default=True)

class GitIndexRequest(BaseModel):
    repo_url: str = Field(..., description="GitHub/GitLab repository URL")
    branch: Optional[str] = Field(default=None)
    access_token: Optional[str] = Field(default=None, description="PAT for private repos")
    dept_id: str = Field(default="engineering")
    async_embedding: bool = Field(default=True)

class ContextRequest(BaseModel):
    query: str = Field(..., description="Natural language query or code snippet")
    top_k: int = Field(default=5)
    expand_dependencies: bool = Field(default=True)
    expand_depth: int = Field(default=1)
    max_chunk_chars: Optional[int] = Field(default=None)
    org_id: str = Field(default="default_org")
    dept_id: str = Field(default="default_dept")
    repo_id: str = Field(default="default_repo")
    requesting_user: Optional[str] = Field(default=None)

class CreateKeyRequest(BaseModel):
    caller_name: str = Field(..., description="Human label: who / what is this key for?")
    org_id: str = Field(default="default_org", description="Tenant org this key belongs to")
    scopes: list = Field(default=["read", "context"])

class RevokeKeyRequest(BaseModel):
    key_id: str = Field(..., description="key_id returned when the key was created")

# ── Static UI ─────────────────────────────────────────────────────────────────
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def serve_ui():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"message": "M5 v2 Context Engine API is online. See /docs for Swagger UI."}

# ── Health & Readiness ────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    """Unauthenticated — used by load balancers and uptime monitors."""
    return {
        "status": "online",
        "engine": "M5 v2 Context Engine",
        "version": "1.0.0",
        "dev_agent_mode": DEV_AGENT_MODE,
    }

@app.get("/ready")
def readiness_check():
    """Unauthenticated — Kubernetes readiness probe."""
    return {"status": "ready", "engine": "M5 v2 Context Engine", "version": "1.0.0", "storage": "ok"}


# ── Admin: API Key Management ─────────────────────────────────────────────────
# Plain English: these three endpoints let you create, list, and revoke API keys.
# They require your M5_ADMIN_KEY from .env — not a regular API key.

@app.post("/api/admin/keys", dependencies=[Depends(verify_admin_key)])
def admin_create_key(req: CreateKeyRequest):
    """
    Creates a new API key.
    Returns the raw key ONCE — save it immediately. It cannot be recovered later.

    Usage:
      curl -X POST http://localhost:8000/api/admin/keys \\
           -H "Authorization: Bearer <M5_ADMIN_KEY>" \\
           -H "Content-Type: application/json" \\
           -d '{"caller_name": "Alice - Claude Code", "org_id": "acme"}'
    """
    return create_api_key(
        caller_name=req.caller_name,
        org_id=req.org_id,
        scopes=req.scopes,
    )

@app.get("/api/admin/keys", dependencies=[Depends(verify_admin_key)])
def admin_list_keys():
    """
    Lists all API keys (without the raw key — only metadata).

    Usage:
      curl http://localhost:8000/api/admin/keys \\
           -H "Authorization: Bearer <M5_ADMIN_KEY>"
    """
    return {"keys": list_api_keys()}

@app.delete("/api/admin/keys/{key_id}", dependencies=[Depends(verify_admin_key)])
def admin_revoke_key(key_id: str):
    """
    Revokes an API key by key_id. The key stops working immediately.

    Usage:
      curl -X DELETE http://localhost:8000/api/admin/keys/kid_abc123 \\
           -H "Authorization: Bearer <M5_ADMIN_KEY>"
    """
    found = revoke_api_key(key_id)
    if not found:
        raise HTTPException(status_code=404, detail=f"Key '{key_id}' not found.")
    return {"status": "revoked", "key_id": key_id}


# ── Remote HTTP MCP Endpoint ──────────────────────────────────────────────────
@app.post("/mcp")
async def mcp_http_endpoint(request: Request, key_info: Dict[str, Any] = Depends(verify_api_key)):
    """
    Remote HTTP MCP transport (JSON-RPC 2.0).
    Used by Copilot, Claude Code, ChatGPT, Cursor.

    Plain English: Your AI editor sends a JSON-RPC message here.
    M5 looks up your code and sends back the relevant chunks.
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

    caller = key_info.get("caller_name", "mcp_http_client") if isinstance(key_info, dict) else "mcp_http_client"
    response = mcp_server.handle_request(req_json, api_key_override=api_key, caller_identity=caller)
    if response is None:
        return {"jsonrpc": "2.0", "result": None}
    return response


# ── Indexing (admin-only) ─────────────────────────────────────────────────────
@app.get("/api/index/status", dependencies=[Depends(verify_admin_key)])
def index_status_endpoint(
    org_id: str = "default_org",
    dept_id: str = "default_dept",
    repo_id: str = "default_repo"
):
    """Returns current indexing progress for a tenant namespace."""
    return progressive_indexer.get_status(org_id=org_id, dept_id=dept_id, repo_id=repo_id)

@app.post("/api/index", dependencies=[Depends(verify_admin_key)])
def index_endpoint(req: IndexRequest):
    """Indexes a local directory. Admin-only."""
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
            blocks=blocks, org_id=req.org_id, dept_id=req.dept_id, repo_id=req.repo_id
        )
        msg = f"Tier-0 catalog built. Background embedding queued for {len(blocks)} blocks."
    else:
        retriever = get_hybrid_retriever(org_id=req.org_id, dept_id=req.dept_id, repo_id=req.repo_id)
        retriever.index_blocks(blocks)
        msg = f"Indexed {len(blocks)} blocks."

    return {
        "status": "success",
        "org_id": req.org_id,
        "dept_id": req.dept_id,
        "repo_id": req.repo_id,
        "workspace_root": req.workspace_root,
        "files_cataloged": file_count,
        "blocks_extracted": len(blocks),
        "message": msg,
    }

@app.post("/api/index/git", dependencies=[Depends(verify_admin_key)])
def git_index_endpoint(req: GitIndexRequest):
    """Clones a GitHub/GitLab repository and indexes it. Admin-only."""
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
            blocks=blocks, org_id=org_id, dept_id=req.dept_id, repo_id=repo_id
        )
        msg = (
            f"Cloned '{req.repo_url}'. "
            f"Tier-0 catalog ready ({file_count} files, {len(blocks)} blocks). "
            f"Background vector embedding queued."
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
        "message": msg,
    }


# ── Core Context Endpoint (authenticated) ────────────────────────────────────
@app.post("/api/context")
def context_endpoint(req: ContextRequest, key_info: Dict[str, Any] = Depends(verify_api_key)):
    """
    The flagship M5 call: one request → ranked chunks + dependency graph.
    Requires a valid API key (or admin key).

    Plain English: Your application asks "where is the payment retry logic?"
    M5 finds the exact functions, their files, and line numbers, and returns them.
    """
    from src.context.context_engine import get_context

    caller = key_info.get("caller_name", "api_user") if isinstance(key_info, dict) else "api_user"
    user_name = req.requesting_user or caller

    bundle = get_context(
        query=req.query,
        top_k=req.top_k,
        expand_dependencies=req.expand_dependencies,
        expand_depth=req.expand_depth,
        max_chunk_chars=req.max_chunk_chars,
        org_id=req.org_id,
        dept_id=req.dept_id,
        repo_id=req.repo_id,
        requesting_user=user_name,
        caller_identity=caller,
    )
    return bundle


# ── Customizations (authenticated) ───────────────────────────────────────────
@app.get("/api/customizations/rules", dependencies=[Depends(verify_api_key)])
def customizations_rules_endpoint():
    from src.parser.customizations import customization_manager
    rules = customization_manager.load_rules()
    return {"rules": rules, "has_rules": bool(rules)}

@app.get("/api/customizations/skills", dependencies=[Depends(verify_api_key)])
def customizations_skills_endpoint():
    from src.parser.customizations import customization_manager
    return {"skills": customization_manager.list_skills()}

@app.get("/api/customizations/skills/{skill_name}", dependencies=[Depends(verify_api_key)])
def customizations_skill_detail_endpoint(skill_name: str):
    from src.parser.customizations import customization_manager
    return customization_manager.load_skill(skill_name)
