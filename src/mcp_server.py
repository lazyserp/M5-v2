import sys
import json
import os
from typing import Dict, Any, Optional
from src.tools.hybrid_search import HybridRetriever, get_hybrid_retriever
from src.tools.dependency_graph import PersistentDependencyGraph
from src.tools.line_reader import read_file_lines
from src.indexer.progressive_indexer import progressive_indexer
from src.indexer.git_manager import git_manager

MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "m5-context-engine"
SERVER_VERSION = "3.0.0"

# ── Lean retrieval helper (no LLM / agent machinery) ─────────────────────────
def get_retrieval_tools(
    org_id: str = "default_org",
    dept_id: str = "default_dept",
    repo_id: str = "default_repo"
):
    """
    Returns tenant-scoped retrieval primitives only.
    No LLM, no agent loop, no write/execute tools.
    """
    retriever = get_hybrid_retriever(org_id=org_id, dept_id=dept_id, repo_id=repo_id)
    d_graph = PersistentDependencyGraph(org_id=org_id, dept_id=dept_id, repo_id=repo_id)
    return retriever, d_graph

# ── MCP Tool Schemas (read-only core tools only) ──────────────────────────────
MCP_TOOLS_SCHEMA = [
    {
        "name": "m5_get_context",
        "description": (
            "ONE-CALL context fetch: hybrid search + dependency expansion + dedup + audit log. "
            "Returns a structured ContextBundle with ranked code chunks, dependency edges, "
            "and token estimates. Use this instead of chaining m5_search_code + m5_get_dependencies."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language query or code snippet"},
                "org_id": {"type": "string", "default": "default_org"},
                "dept_id": {"type": "string", "default": "default_dept"},
                "repo_id": {"type": "string", "default": "default_repo"},
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
        "description": "Hybrid retrieval (BM25 + dense vectors + RRF) across AST code blocks. Use m5_get_context for most cases; use this when you need raw ranked results only.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language query or code snippet"},
                "org_id": {"type": "string", "default": "default_org"},
                "dept_id": {"type": "string", "default": "default_dept"},
                "repo_id": {"type": "string", "default": "default_repo"},
                "top_k": {"type": "integer", "default": 3, "description": "Number of top results to return"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "m5_read_lines",
        "description": "Streams source code lines directly from disk with configurable context padding.",
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
        "description": "Returns what files a given file imports (outgoing dependencies).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative workspace file path"},
                "org_id": {"type": "string", "default": "default_org"},
                "dept_id": {"type": "string", "default": "default_dept"},
                "repo_id": {"type": "string", "default": "default_repo"}
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "m5_get_dependents",
        "description": "Returns which files import a given file (incoming dependencies / reverse lookup).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative workspace file path"},
                "org_id": {"type": "string", "default": "default_org"},
                "dept_id": {"type": "string", "default": "default_dept"},
                "repo_id": {"type": "string", "default": "default_repo"}
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "m5_find_symbol_references",
        "description": "Finds where a function, class, or variable is defined — returns file paths and exact line ranges.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol_name": {"type": "string", "description": "Function, class, or variable name to locate"},
                "org_id": {"type": "string", "default": "default_org"},
                "dept_id": {"type": "string", "default": "default_dept"},
                "repo_id": {"type": "string", "default": "default_repo"}
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
                "org_id": {"type": "string", "default": "default_org"},
                "dept_id": {"type": "string", "default": "default_dept"},
                "repo_id": {"type": "string", "default": "default_repo"}
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
    }
]

class MCPServer:
    """
    Model Context Protocol (MCP) JSON-RPC 2.0 Server over STDIO.
    Exposes read-only context retrieval tools only.
    Write/execute/agent tools are in experimental/ and not exposed by default.
    """
    def __init__(self):
        self.running = True
        self.mcp_api_key = os.getenv("M5_MCP_API_KEY", "")

    def handle_request(self, request_json: Dict[str, Any], api_key_override: Optional[str] = None) -> Optional[Dict[str, Any]]:
        req_id = request_json.get("id")
        method = request_json.get("method")
        params = request_json.get("params", {})

        if method == "initialize":
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
            return self._execute_tool_call(req_id, tool_name, args, api_key_override=api_key_override)

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
        api_key_override: Optional[str] = None
    ) -> Dict[str, Any]:
        org_id = args.get("org_id", "default_org")
        dept_id = args.get("dept_id", "default_dept")
        repo_id = args.get("repo_id", "default_repo")
        caller_name = "mcp/client"

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
                    requesting_user=args.get("requesting_user"),
                    caller_identity=caller_name,
                )
                output = json.dumps(bundle, indent=2)

            # ── Raw search ────────────────────────────────────────────────
            elif tool_name == "m5_search_code":
                query = args.get("query", "")
                top_k = args.get("top_k", 3)
                output = retriever.search_code(query=query, top_k=top_k)

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
                status_dict = progressive_indexer.get_status(org_id=org_id, dept_id=dept_id, repo_id=repo_id)
                output = json.dumps(status_dict, indent=2)

            # ── Skills ────────────────────────────────────────────────────
            elif tool_name == "m5_list_skills":
                from src.parser.customizations import customization_manager
                output = json.dumps(customization_manager.list_skills(), indent=2)

            elif tool_name == "m5_load_skill":
                from src.parser.customizations import customization_manager
                output = json.dumps(customization_manager.load_skill(args.get("skill_name", "")), indent=2)

            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": f"Unknown tool: '{tool_name}'"}
                }

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": str(output)}]
                }
            }

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": f"Tool execution failed: {str(e)}"}
            }

    def run_stdio(self):
        """Standard synchronous I/O loop for MCP client communication over STDIO."""
        while self.running:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                req_json = json.loads(line)
                resp_json = self.handle_request(req_json)
                if resp_json:
                    sys.stdout.write(json.dumps(resp_json) + "\n")
                    sys.stdout.flush()
            except Exception as e:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {str(e)}"}
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()

mcp_server = MCPServer()

def main():
    server = MCPServer()
    server.run_stdio()

if __name__ == "__main__":
    main()
