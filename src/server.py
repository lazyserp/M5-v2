import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.parser.ast_parser import ASTParser, EXTENSION_MAP
from src.agents.react_loop import run_agent_loop, vector_store, dep_graph

# 1. Initialize FastAPI Application
app = FastAPI(
    title="M5 v2 Context Engine API",
    description="Enterprise Codebase Context & Memory REST Infrastructure",
    version="2.0.0"
)

# 2. Enable CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Pydantic Request & Response Models
class IndexRequest(BaseModel):
    workspace_root: str = "."

class ChatRequest(BaseModel):
    query: str
    max_turns: int = 5

class ChatResponse(BaseModel):
    query: str
    answer: str

# Helper function to crawl and index workspace
def perform_indexing(workspace_root: str = "."):
    all_blocks = []
    ignore_dirs = {".git", "__pycache__", "venv", ".venv", "node_modules"}

    for root, dirs, files in os.walk(workspace_root):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]

        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in EXTENSION_MAP:
                rel_path = os.path.relpath(os.path.join(root, f), workspace_root).replace("\\", "/")
                dep_graph.add_file(rel_path)

                try:
                    with open(rel_path, "r", encoding="utf-8", errors="ignore") as code_file:
                        code_content = code_file.read()

                    lang = EXTENSION_MAP[ext]
                    parser = ASTParser(language_name=lang)
                    blocks = parser.parse_code(code_content)

                    for b in blocks:
                        b["file_path"] = rel_path
                    all_blocks.extend(blocks)
                except Exception:
                    continue

    if all_blocks:
        vector_store.index_blocks(all_blocks)
    return len(all_blocks)

# 4. API Endpoints
@app.on_event("startup")
def startup_event():
    """Auto-index workspace when the server starts."""
    count = perform_indexing(".")
    print(f"[+] M5 v2 Server Started: Auto-indexed {count} AST blocks across workspace.")

@app.get("/health")
def health_check():
    return {"status": "online", "engine": "M5 v2 Context Engine"}

@app.post("/api/index")
def index_endpoint(req: IndexRequest):
    if not os.path.exists(req.workspace_root):
        raise HTTPException(status_code=400, detail=f"Path '{req.workspace_root}' does not exist.")

    count = perform_indexing(req.workspace_root)
    return {
        "status": "success",
        "workspace_root": req.workspace_root,
        "blocks_indexed": count
    }

@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    answer = run_agent_loop(req.query, max_turns=req.max_turns)
    return ChatResponse(query=req.query, answer=answer)
