import sys
import json
import os
import time
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv(override=True)

from src.tools.hybrid_search import HybridRetriever, get_hybrid_retriever
from src.tools.dependency_graph import PersistentDependencyGraph
from src.tools.line_reader import read_file_lines
from src.indexer.progressive_indexer import progressive_indexer
from src.indexer.git_manager import git_manager

MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "m5-context-engine"
try:
    from importlib.metadata import version as _get_pkg_ver
    SERVER_VERSION = _get_pkg_ver("m5-engine")
except Exception:
    SERVER_VERSION = "1.1.1"

def _ensure_workspace_indexed(org_id: str, dept_id: str, repo_id: str) -> None:
    """Auto-indexes the default workspace on stdio boot if the default index is currently empty."""
    workspace_root = os.getenv("WORKSPACE_ROOT", ".")
    if os.path.exists("/workspace") and not os.path.exists(workspace_root):
        workspace_root = "/workspace"

    if os.getenv("M5_LOCAL_MODE") == "true":
        from src.storage.local_db import LocalCodeGraphDB
        local_db = LocalCodeGraphDB(workspace_root=workspace_root)
        stats = local_db.get_stats()
        if stats.get("total_files", 0) > 0:
            return
        if os.path.exists(workspace_root):
            from src.indexer.file_watcher import LocalFileWatcher
            watcher = LocalFileWatcher(workspace_root)
            watcher.initial_scan()
        return

    default_org = os.getenv("DEFAULT_ORG_ID", "default_org")
    default_dept = os.getenv("DEFAULT_DEPT_ID", "default_dept")
    default_repo = os.getenv("DEFAULT_REPO_ID", "default_repo")
    if (org_id, dept_id, repo_id) != (default_org, default_dept, default_repo):
        return

    status = progressive_indexer.get_status(org_id=org_id, dept_id=dept_id, repo_id=repo_id)
    if status.get("total_blocks", 0) == 0:
        if os.path.exists(workspace_root):
            files_count, blocks = progressive_indexer.tier0_instant_boot(
                workspace_root=workspace_root,
                org_id=org_id,
                dept_id=dept_id,
                repo_id=repo_id
            )
            if blocks:
                from src.tools.vector_search import VectorStore
                v_store = VectorStore(org_id=org_id, dept_id=dept_id, repo_id=repo_id)
                v_store.index_blocks(blocks, batch_size=64)


# ── Lean retrieval helper (no LLM / agent machinery) ─────────────────────────
def get_retrieval_tools(
    org_id: Optional[str] = None,
    dept_id: Optional[str] = None,
    repo_id: Optional[str] = None
):
    """
    Returns tenant-scoped retrieval primitives dynamically resolved from
    environment variables or active Qdrant collections.
    """
    resolved_org = org_id or os.getenv("DEFAULT_ORG_ID", "default_org")
    resolved_dept = dept_id or os.getenv("DEFAULT_DEPT_ID", "default_dept")
    resolved_repo = repo_id or os.getenv("DEFAULT_REPO_ID", "default_repo")

    # If still pointing to default_org, check for single active collection in Qdrant
    if os.getenv("M5_LOCAL_MODE") != "true" and resolved_org == "default_org" and resolved_repo == "default_repo":
        try:
            from src.tools.vector_search import get_shared_qdrant_client
            client = get_shared_qdrant_client()
            collections = [c.name for c in client.get_collections().collections if c.name.startswith("m5_")]
            if len(collections) == 1 and collections[0] != "m5_default_org_default_dept_default_repo":
                parts = collections[0][3:].split("_")
                if len(parts) >= 3:
                    resolved_org, resolved_dept, resolved_repo = parts[0], parts[1], "_".join(parts[2:])
        except Exception:
            pass

    _ensure_workspace_indexed(resolved_org, resolved_dept, resolved_repo)
    retriever = get_hybrid_retriever(org_id=resolved_org, dept_id=resolved_dept, repo_id=resolved_repo)
    d_graph = PersistentDependencyGraph(org_id=resolved_org, dept_id=resolved_dept, repo_id=resolved_repo)
    return retriever, d_graph

# ── MCP Tool Schemas (read-only core tools only) ──────────────────────────────
MCP_TOOLS_SCHEMA = [
    {
        "name": "m5_get_context",
        "description": (
            "[MANDATORY FIRST STEP / PREFER OVER GREP] Instant 1-call AST context. "
            "Call this FIRST before searching or reading files. Returns exact ranked symbol definitions, "
            "upstream callers, downstream dependencies, and token estimates in 1 step with zero token waste."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language query or code snippet"},
                "org_id": {"type": "string", "description": "Optional tenant organization"},
                "dept_id": {"type": "string", "description": "Optional department namespace"},
                "repo_id": {"type": "string", "description": "Optional repository identifier"},
                "top_k": {"type": "integer", "default": 5, "description": "Top-k code blocks to retrieve"},
                "expand_dependencies": {"type": "boolean", "default": True, "description": "Also fetch imports of matched files"},
                "expand_depth": {"type": "integer", "default": 1, "description": "Dependency expansion hops (1 or 2)"},
                "max_chunk_chars": {"type": "integer", "description": "Optional snippet limit. Defaults to full AST method/class body."},
                "requesting_user": {"type": "string", "description": "Optional: human user identity for per-file ACL"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "m5_search_code",
        "description": "[FAST HYBRID CODE SEARCH] High-speed AST symbol & semantic code search across all repository functions and classes. Use this INSTEAD of ripgrep or blind file searching.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language query or code snippet"},
                "org_id": {"type": "string", "description": "Optional tenant organization"},
                "dept_id": {"type": "string", "description": "Optional department namespace"},
                "repo_id": {"type": "string", "description": "Optional repository identifier"},
                "top_k": {"type": "integer", "default": 3, "description": "Number of top results to return"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "m5_read_lines",
        "description": "[SURGICAL LINE VIEWER] Streams exact source code lines directly from disk with configurable context padding. Use this instead of reading entire files into memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative workspace file path"},
                "start_line": {"type": "integer", "description": "Starting line number (1-indexed)"},
                "end_line": {"type": "integer", "description": "Ending line number (1-indexed)"},
                "context_padding": {"type": "integer", "default": 5, "description": "Lines of context padding"}
            },
            "required": ["file_path", "start_line", "end_line"]
        }
    },
    {
        "name": "m5_get_dependencies",
        "description": "[CALL GRAPH / IMPORTS] Returns all upstream files and symbols imported by this file. Call this before modifying code to understand dependencies.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative workspace file path"},
                "org_id": {"type": "string", "description": "Optional tenant organization"},
                "dept_id": {"type": "string", "description": "Optional department namespace"},
                "repo_id": {"type": "string", "description": "Optional repository identifier"}
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "m5_get_dependents",
        "description": "[BLAST RADIUS ANALYSIS] Returns all downstream files and functions that depend on or import this symbol/file. Crucial for refactoring safely without breaking callers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative workspace file path"},
                "org_id": {"type": "string", "description": "Optional tenant organization"},
                "dept_id": {"type": "string", "description": "Optional department namespace"},
                "repo_id": {"type": "string", "description": "Optional repository identifier"}
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "m5_find_symbol_references",
        "description": "[EXACT AST SYMBOL LOOKUP] Finds exact definition line ranges and usages for any function, class, or variable with Tree-sitter AST precision (zero false positives).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol_name": {"type": "string", "description": "Function, class, or variable name to locate"},
                "org_id": {"type": "string", "description": "Optional tenant organization"},
                "dept_id": {"type": "string", "description": "Optional department namespace"},
                "repo_id": {"type": "string", "description": "Optional repository identifier"}
            },
            "required": ["symbol_name"]
        }
    },
    {
        "name": "m5_index_git_repo",
        "description": "Shallow-clones a GitHub/GitLab repository and immediately indexes it (AST + vectors + dependency graph).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_url": {"type": "string", "description": "Repository URL (e.g. https://github.com/psf/requests)"},
                "branch": {"type": "string", "description": "Optional branch name"},
                "dept_id": {"type": "string", "default": "engineering"}
            },
            "required": ["repo_url"]
        }
    },
    {
        "name": "m5_index_status",
        "description": "Returns the current indexing status and file/block counts for a tenant namespace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string", "description": "Optional tenant organization"},
                "dept_id": {"type": "string", "description": "Optional department namespace"},
                "repo_id": {"type": "string", "description": "Optional repository identifier"}
            }
        }
    },
    {
        "name": "m5_list_skills",
        "description": "Lists all discoverable workspace skills and cheatsheets in .agents/skills/.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "m5_load_skill",
        "description": "Loads detailed workflow instructions for a specific skill by name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "skill_name": {"type": "string", "description": "Name of the skill to load"}
            },
            "required": ["skill_name"]
        }
    },
    {
        "name": "m5_get_test_impact",
        "description": "[SURGICAL TEST IMPACT] Calculates call-graph blast radius and identifies exact companion unit/integration test files affected by modifying a function or file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol_name": {"type": "string", "description": "The function/class name being modified"},
                "file_path": {"type": "string", "description": "Optional path to the source file"}
            },
            "required": ["symbol_name"]
        }
    },
    {
        "name": "m5_cross_repo_search",
        "description": "Searches across multiple federated microservice repositories for matching symbol definitions or API contracts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Symbol name or API route pattern to search across repos"}
            },
            "required": ["query"]
        }
    }
]

class MCPServer:
    """
    Model Context Protocol (MCP) JSON-RPC 2.0 Server over STDIO and HTTP.
    Exposes read-only context retrieval tools only.
    """
    def __init__(self):
        self.running = True
        self.mcp_api_key = os.getenv("M5_MCP_API_KEY", "")
        self.client_name = "mcp_client"
        self.client_info = {}

    def handle_request(
        self,
        request_json: Dict[str, Any],
        api_key_override: Optional[str] = None,
        caller_identity: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        req_id = request_json.get("id")
        method = request_json.get("method")
        params = request_json.get("params", {})

        if method == "initialize":
            self.client_info = params.get("clientInfo", {})
            if self.client_info and self.client_info.get("name"):
                self.client_name = self.client_info.get("name")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "capabilities": {"tools": {"listChanged": False}}
                }
            }

        elif method == "notifications/initialized":
            return None

        elif method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": MCP_TOOLS_SCHEMA}
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments", {})
            return self._execute_tool_call(
                req_id,
                tool_name,
                args,
                api_key_override=api_key_override,
                caller_identity=caller_identity
            )

        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method '{method}' not found."}
            }

    def _execute_tool_call(
        self,
        req_id: Any,
        tool_name: str,
        args: Dict[str, Any],
        api_key_override: Optional[str] = None,
        caller_identity: Optional[str] = None
    ) -> Dict[str, Any]:
        # Smart Namespace Fallback:
        default_org = os.getenv("DEFAULT_ORG_ID", "default_org")
        default_dept = os.getenv("DEFAULT_DEPT_ID", "default_dept")
        default_repo = os.getenv("DEFAULT_REPO_ID", "default_repo")

        raw_org = args.get("org_id")
        raw_dept = args.get("dept_id")
        raw_repo = args.get("repo_id")

        org_id = default_org if (not raw_org or raw_org == "default_org") else raw_org
        dept_id = default_dept if (not raw_dept or raw_dept == "default_dept") else raw_dept
        repo_id = default_repo if (not raw_repo or raw_repo == "default_repo") else raw_repo

        # If still default_org, check if there is an active non-default collection in Qdrant
        if os.getenv("M5_LOCAL_MODE") != "true" and org_id == "default_org" and repo_id == "default_repo":
            try:
                from src.tools.vector_search import get_shared_qdrant_client
                client = get_shared_qdrant_client()
                collections = [c.name for c in client.get_collections().collections if c.name.startswith("m5_")]
                if len(collections) == 1 and collections[0] != "m5_default_org_default_dept_default_repo":
                    parts = collections[0][3:].split("_")
                    if len(parts) >= 3:
                        org_id, dept_id, repo_id = parts[0], parts[1], "_".join(parts[2:])
            except Exception:
                pass

        start_time = time.perf_counter()
        transport = "mcp_http" if api_key_override else "mcp_stdio"
        system_user = os.getenv("USERNAME") or os.getenv("USER") or "developer"

        if caller_identity:
            caller_name = caller_identity
        elif api_key_override:
            try:
                from src.auth import _lookup_key, _get_admin_key
                if api_key_override == _get_admin_key():
                    caller_name = f"admin ({system_user})"
                else:
                    key_rec = _lookup_key(api_key_override)
                    caller_name = key_rec.get("caller_name", f"api_user ({system_user})") if key_rec else f"api_user ({system_user})"
            except Exception:
                caller_name = f"api_user ({system_user})"
        else:
            caller_name = f"{system_user} ({self.client_name})"

        retriever, d_graph = get_retrieval_tools(org_id=org_id, dept_id=dept_id, repo_id=repo_id)

        try:
            # ── Flagship: bundled context ─────────────────────────────────
            if tool_name == "m5_get_context":
                from src.context.context_engine import get_context
                bundle = get_context(
                    query=args.get("query", ""),
                    top_k=args.get("top_k", 5),
                    expand_dependencies=args.get("expand_dependencies", True),
                    expand_depth=args.get("expand_depth", 1),
                    max_chunk_chars=args.get("max_chunk_chars"),
                    org_id=org_id,
                    dept_id=dept_id,
                    repo_id=repo_id,
                    repo_filter=args.get("repo_filter"),
                    requesting_user=args.get("requesting_user") or caller_name,
                    caller_identity=caller_name,
                )
                output = json.dumps(bundle, indent=2)

            # ── Raw search ────────────────────────────────────────────────
            elif tool_name == "m5_search_code":
                query = args.get("query", "")
                top_k = args.get("top_k", 3)
                if retriever is not None:
                    output = retriever.search_code(query=query, top_k=top_k)
                else:
                    from src.storage.local_db import LocalCodeGraphDB
                    local_db = LocalCodeGraphDB()
                    syms = local_db.search_fts(query, limit=top_k)
                    output = json.dumps(syms, indent=2)

            # ── Line reader ───────────────────────────────────────────────
            elif tool_name == "m5_read_lines":
                output = read_file_lines(
                    file_path=args.get("file_path", ""),
                    start_line=args.get("start_line", 1),
                    end_line=args.get("end_line", 50),
                    context_padding=args.get("context_padding", 5)
                )

            # ── Dependency graph ──────────────────────────────────────────
            elif tool_name == "m5_get_dependencies":
                output = d_graph.get_dependencies(file_path=args.get("file_path", ""))

            elif tool_name == "m5_get_dependents":
                output = d_graph.get_dependents(file_path=args.get("file_path", ""))

            elif tool_name == "m5_find_symbol_references":
                output = d_graph.find_symbol_references(symbol_name=args.get("symbol_name", ""))

            # ── Indexing ──────────────────────────────────────────────────
            elif tool_name == "m5_index_git_repo":
                repo_url = args.get("repo_url", "")
                branch = args.get("branch")
                dept = args.get("dept_id", "engineering")
                dest_folder, g_org, g_repo = git_manager.clone_or_pull(repo_url=repo_url, branch=branch)
                f_count, blocks = progressive_indexer.tier0_instant_boot(
                    workspace_root=dest_folder,
                    org_id=g_org,
                    dept_id=dept,
                    repo_id=g_repo
                )
                progressive_indexer.start_background_embedding(
                    blocks=blocks, org_id=g_org, dept_id=dept, repo_id=g_repo
                )
                output = (
                    f"[SUCCESS] Cloned '{repo_url}' -> Indexed {f_count} files, "
                    f"{len(blocks)} code blocks into namespace [{g_org}/{dept}/{g_repo}]."
                )

            elif tool_name == "m5_index_status":
                _ensure_workspace_indexed(org_id, dept_id, repo_id)
                from src.storage.local_db import LocalCodeGraphDB
                from src.indexer.progressive_indexer import _detect_git_commit
                workspace_root = os.getenv("WORKSPACE_ROOT", ".")
                local_db = LocalCodeGraphDB(workspace_root=workspace_root)
                stats = local_db.get_stats()

                if stats.get("total_files", 0) > 0:
                    status_dict = {
                        "org_id": org_id,
                        "dept_id": dept_id,
                        "repo_id": repo_id,
                        "status": "ready",
                        "is_fresh": True,
                        "total_files": stats.get("total_files", 0),
                        "total_blocks": stats.get("total_symbols", 0),
                        "indexed_blocks": stats.get("total_symbols", 0),
                        "is_indexing": False,
                        "progress_percentage": 100.0,
                        "commit_sha": _detect_git_commit(workspace_root),
                        "database_path": local_db.db_path,
                        "database_size_kb": stats.get("db_size_kb", 0),
                        "last_error": None
                    }
                else:
                    status_dict = progressive_indexer.get_status(org_id=org_id, dept_id=dept_id, repo_id=repo_id)
                output = json.dumps(status_dict, indent=2)

            # ── Skills ────────────────────────────────────────────────────
            elif tool_name == "m5_list_skills":
                from src.parser.customizations import customization_manager
                skills = customization_manager.list_skills()
                output = json.dumps({"skills": skills}, indent=2)

            elif tool_name == "m5_load_skill":
                skill_name = args.get("skill_name", "")
                from src.parser.customizations import customization_manager
                detail = customization_manager.load_skill(skill_name)
                output = json.dumps(detail, indent=2)

            elif tool_name == "m5_get_test_impact":
                from src.tools.test_impact import test_impact_engine
                sym = args.get("symbol_name", "")
                f_path = args.get("file_path")
                impact = test_impact_engine.calculate_blast_radius(symbol_name=sym, file_path=f_path)
                output = json.dumps(impact, indent=2)

            elif tool_name == "m5_cross_repo_search":
                from src.tools.multi_repo_graph import multi_repo_graph
                q = args.get("query", "")
                results = multi_repo_graph.cross_repo_symbol_search(symbol_name=q)
                output = json.dumps(results, indent=2)

            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Tool '{tool_name}' not recognized."}
                }

            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            try:
                from src.audit.telemetry import log_mcp_tool_trace
                log_mcp_tool_trace(
                    tool_name=tool_name,
                    args=args,
                    output=output,
                    duration_ms=duration_ms,
                    caller_identity=caller_name,
                    org_id=org_id,
                    dept_id=dept_id,
                    repo_id=repo_id,
                    transport=transport,
                )
            except Exception:
                pass

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": output}]
                }
            }
        except Exception as e:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            try:
                from src.audit.telemetry import log_mcp_tool_trace
                log_mcp_tool_trace(
                    tool_name=tool_name,
                    args=args,
                    output="",
                    duration_ms=duration_ms,
                    caller_identity=caller_name,
                    org_id=org_id,
                    dept_id=dept_id,
                    repo_id=repo_id,
                    transport=transport,
                    error=str(e),
                )
            except Exception:
                pass
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": f"Tool execution failed: {str(e)}"}
            }

mcp_server = MCPServer()

def run_stdio():
    """
    Standard I/O JSON-RPC loop for local IDE MCP connections.
    Listens on sys.stdin and responds on sys.stdout.
    """
    server = mcp_server
    sys.stderr.write("[M5] Starting M5 MCP Server in STDIO mode...\n")
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            res = server.handle_request(req)
            if res is not None:
                sys.stdout.write(json.dumps(res) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError:
            err_res = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error: Invalid JSON"}
            }
            sys.stdout.write(json.dumps(err_res) + "\n")
            sys.stdout.flush()
        except Exception as e:
            sys.stderr.write(f"[M5 STDIO ERROR] {e}\n")
            sys.stderr.flush()

if __name__ == "__main__":
    run_stdio()

