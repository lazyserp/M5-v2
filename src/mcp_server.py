import sys
import json
import asyncio
from typing import Dict, Any, List, Optional
from src.agents.react_loop import get_tenant_tools
from src.indexer.progressive_indexer import progressive_indexer

MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "m5-context-engine"
SERVER_VERSION = "2.3.0"

# Tool Schemas exposed via MCP Tools List
MCP_TOOLS_SCHEMA = [
    {
        "name": "m5_search_code",
        "description": "Performs hybrid retrieval (BM25 keyword search + dense semantic vectors with Reciprocal Rank Fusion) across AST code blocks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query, function name, error string, or code snippet to search for."
                },
                "org_id": {"type": "string", "default": "default_org", "description": "Organization namespace"},
                "dept_id": {"type": "string", "default": "default_dept", "description": "Department namespace"},
                "repo_id": {"type": "string", "default": "default_repo", "description": "Repository identifier"},
                "top_k": {"type": "integer", "default": 3, "description": "Number of top results to return"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "m5_read_lines",
        "description": "Streams source code lines directly from disk with configurable context padding without loading entire file into memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative workspace file path"},
                "start_line": {"type": "integer", "description": "Starting line number (1-indexed)"},
                "end_line": {"type": "integer", "description": "Ending line number (1-indexed)"},
                "context_padding": {"type": "integer", "default": 5, "description": "Lines of context padding before and after range"}
            },
            "required": ["file_path", "start_line", "end_line"]
        }
    },
    {
        "name": "m5_get_dependencies",
        "description": "Queries the dependency graph to inspect local workspace imports for a specific file (outgoing dependencies).",
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
        "description": "Queries the dependency graph to find which workspace files import / depend on a specific file (incoming dependencies).",
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
        "description": "Finds AST function, class, and method definitions with exact line ranges across the codebase.",
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
        "name": "m5_index_status",
        "description": "Queries the real-time background indexing status and file count metrics for a tenant.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string", "default": "default_org"},
                "dept_id": {"type": "string", "default": "default_dept"},
                "repo_id": {"type": "string", "default": "default_repo"}
            }
        }
    }
]

class MCPServer:
    """
    Model Context Protocol (MCP) JSON-RPC 2.0 Server over STDIO.
    Enables native connectivity to Cursor, Claude Desktop, Antigravity IDE, and Zed.
    """
    def __init__(self):
        self.running = True

    def handle_request(self, request_json: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        req_id = request_json.get("id")
        method = request_json.get("method")
        params = request_json.get("params", {})

        # 1. Initialize Protocol Handshake
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION
                    },
                    "capabilities": {
                        "tools": {
                            "listChanged": False
                        }
                    }
                }
            }

        # 2. Initialized Notification (no response required)
        elif method == "notifications/initialized":
            return None

        # 3. Ping Health Check
        elif method == "ping":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {}
            }

        # 4. Tools List
        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": MCP_TOOLS_SCHEMA
                }
            }

        # 5. Tool Call Execution
        elif method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments", {})
            return self._execute_tool_call(req_id, tool_name, args)

        # 6. Unknown Method
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method '{method}' not found."
                }
            }

    def _execute_tool_call(self, req_id: Any, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        org_id = args.get("org_id", "default_org")
        dept_id = args.get("dept_id", "default_dept")
        repo_id = args.get("repo_id", "default_repo")

        registry, retriever, d_graph = get_tenant_tools(org_id=org_id, dept_id=dept_id, repo_id=repo_id)

        try:
            if tool_name == "m5_search_code":
                query = args.get("query", "")
                top_k = args.get("top_k", 3)
                output = retriever.search_code(query=query, top_k=top_k)

            elif tool_name == "m5_read_lines":
                file_path = args.get("file_path", "")
                start_line = args.get("start_line", 1)
                end_line = args.get("end_line", 50)
                padding = args.get("context_padding", 5)
                output = registry["read_file_lines"](file_path=file_path, start_line=start_line, end_line=end_line, context_padding=padding)

            elif tool_name == "m5_get_dependencies":
                file_path = args.get("file_path", "")
                output = d_graph.get_dependencies(file_path=file_path)

            elif tool_name == "m5_get_dependents":
                file_path = args.get("file_path", "")
                output = d_graph.get_dependents(file_path=file_path)

            elif tool_name == "m5_find_symbol_references":
                symbol_name = args.get("symbol_name", "")
                output = d_graph.find_symbol_references(symbol_name=symbol_name)

            elif tool_name == "m5_index_status":
                status_dict = progressive_indexer.get_status(org_id=org_id, dept_id=dept_id, repo_id=repo_id)
                output = json.dumps(status_dict, indent=2)

            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32602,
                        "message": f"Unknown tool: '{tool_name}'"
                    }
                }

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": str(output)
                        }
                    ]
                }
            }

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32000,
                    "message": f"Tool execution failed: {str(e)}"
                }
            }

    async def run_stdio_async(self):
        """Asynchronous standard I/O loop for MCP client communication."""
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        while self.running:
            line_bytes = await reader.readline()
            if not line_bytes:
                break

            line = line_bytes.decode("utf-8").strip()
            if not line:
                continue

            try:
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

def main():
    server = MCPServer()
    try:
        asyncio.run(server.run_stdio_async())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
