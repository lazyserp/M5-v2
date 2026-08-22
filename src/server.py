import os
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.parser.ast_parser import ASTParser, EXTENSION_MAP
from src.agents.react_loop import run_agent_loop, get_tenant_tools
from src.indexer.progressive_indexer import progressive_indexer
from src.api.webhooks import webhook_router

# 1. Initialize FastAPI Application
app = FastAPI(
    title="M5 v2 Enterprise Context Engine API",
    description="Multi-Tenant Codebase Context & Memory REST Infrastructure with Tiered Ingestion & Webhooks",
    version="2.2.0"
)

# 2. Enable CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Mount Webhook Router
app.include_router(webhook_router)

# 4. Pydantic Request & Response Models
class IndexRequest(BaseModel):
    workspace_root: str = "."
    org_id: str = Field(default="default_org", description="Enterprise organization identifier")
    dept_id: str = Field(default="default_dept", description="Department / team namespace")
    repo_id: str = Field(default="default_repo", description="Repository identifier")
    async_embedding: bool = Field(default=True, description="Enable non-blocking background vector embedding")

class ChatRequest(BaseModel):
    query: str
    max_turns: int = 5
    org_id: str = Field(default="default_org", description="Enterprise organization identifier")
    dept_id: str = Field(default="default_dept", description="Department / team namespace")
    repo_id: str = Field(default="default_repo", description="Repository identifier")

class ChatResponse(BaseModel):
    query: str
    answer: str
    org_id: str
    dept_id: str
    repo_id: str

# 5. Mount Static UI Assets
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def serve_ui():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"message": "M5 v2 Multi-Tenant Context Engine API is online. Access /docs for Swagger UI."}

# 6. API Endpoints
@app.on_event("startup")
def startup_event():
    """Auto-index default workspace with Tier 0 instant boot on startup."""
    files_count, blocks = progressive_indexer.tier0_instant_boot(
        workspace_root=".",
        org_id="default_org",
        dept_id="default_dept",
        repo_id="default_repo"
    )
    progressive_indexer.start_background_embedding(
        blocks=blocks,
        org_id="default_org",
        dept_id="default_dept",
        repo_id="default_repo"
    )
    print(f"[+] M5 v2 Server Started: Tier-0 catalog ready ({files_count} files, {len(blocks)} AST blocks). Background vector embedding running.")

@app.get("/health")
def health_check():
    return {"status": "online", "engine": "M5 v2 Multi-Tenant Context Engine", "version": "2.2.0"}

@app.get("/api/index/status")
def index_status_endpoint(
    org_id: str = "default_org",
    dept_id: str = "default_dept",
    repo_id: str = "default_repo"
):
    return progressive_indexer.get_status(org_id=org_id, dept_id=dept_id, repo_id=repo_id)

@app.post("/api/index")
def index_endpoint(req: IndexRequest, background_tasks: BackgroundTasks):
    if not os.path.exists(req.workspace_root):
        raise HTTPException(status_code=400, detail=f"Path '{req.workspace_root}' does not exist.")

    # 1. Tier 0 Instant Graph Boot
    file_count, blocks = progressive_indexer.tier0_instant_boot(
        workspace_root=req.workspace_root,
        org_id=req.org_id,
        dept_id=req.dept_id,
        repo_id=req.repo_id
    )

    # 2. Asynchronous Vector Embedding
    if req.async_embedding:
        progressive_indexer.start_background_embedding(
            blocks=blocks,
            org_id=req.org_id,
            dept_id=req.dept_id,
            repo_id=req.repo_id
        )
        msg = f"Tier-0 catalog built in <1s. Background embedding queued for {len(blocks)} blocks."
    else:
        _, retriever, _ = get_tenant_tools(org_id=req.org_id, dept_id=req.dept_id, repo_id=req.repo_id)
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

@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    answer = run_agent_loop(
        query=req.query,
        max_turns=req.max_turns,
        org_id=req.org_id,
        dept_id=req.dept_id,
        repo_id=req.repo_id
    )
    return ChatResponse(
        query=req.query,
        answer=answer,
        org_id=req.org_id,
        dept_id=req.dept_id,
        repo_id=req.repo_id
    )
