# M5 Engine

> **AST code intelligence and dependency graph engine for AI coding agents.**  
> Give Cursor, Claude Code, Windsurf, or Copilot instant whole-repo context without burning tokens or waiting on grep. Runs completely offline on your machine — zero Docker, zero open ports, zero cloud dependencies.

[![PyPI version](https://img.shields.io/pypi/v/m5-engine.svg)](https://pypi.org/project/m5-engine/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)

---

## Why we built this

If you've used AI coding agents on codebases with more than 50 files, you've probably seen this loop:

1. You ask the agent to fix a bug or trace a feature.
2. The agent runs `grep` or `find`, gets 120 hits, and starts reading entire 1,500-line files one by one.
3. Within 3 turns, it burns 40,000 tokens, hits context limits, forgets previous instructions, and still misses the actual function that handles the request because it was called through an interface or helper.

**M5 fixes this.**

Instead of making your agent wander blindly, M5 parses your codebase's AST (Abstract Syntax Tree) using Tree-sitter, builds a local call graph in SQLite, and indexes symbols with sub-token BM25 and embedded dense vectors. 

When your agent asks `m5_get_context`, M5 returns:
- The **exact target function/class** at Rank 1 (complete verbatim source, no arbitrary line truncation).
- **Upstream entry points** (which API routes, CLI commands, or controllers call it).
- **Downstream dependencies** (which queries, utilities, or external APIs it calls).
- An **ASCII execution flow diagram** showing the full call path.
- A **completeness check** confirming whether the execution chain was fully resolved.
- **Token metrics** showing exactly how many tokens were saved compared to reading whole files.

All in **one single MCP call**, usually under 2,000 tokens.

---

## Quick Start (Under 60 Seconds)

### 1. Install
```bash
pip install m5-engine
```
*(Requires Python 3.9+)*

### 2. Set up your workspace
Run this inside your project root:
```bash
cd /path/to/your/project
m5 setup
```
This does two things:
1. Runs an initial scan (< 1 second for most projects) and creates a `.m5/` folder containing the SQLite call graph and embedded vector store.
2. Displays the exact MCP configuration snippet for your editor and injects agent instructions into your project's `AGENTS.md` so your agent automatically uses M5 instead of grep.

### 3. Add to your editor / agent

#### Cursor
Go to **Settings $\rightarrow$ Features $\rightarrow$ MCP $\rightarrow$ Add New MCP Server**:
- **Name**: `m5`
- **Type**: `command`
- **Command**: `m5 serve`

#### Claude Code / Claude Desktop
Add to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "m5": {
      "command": "m5",
      "args": ["serve"]
    }
  }
}
```

#### Windsurf / VS Code (Cline / Roo Code)
Add under your MCP server settings:
```json
{
  "m5": {
    "command": "m5",
    "args": ["serve"]
  }
}
```

That's it. Your agent now has whole-codebase AST awareness.

---

## What makes M5 different?

### 1. Zero Docker, zero background daemons, zero network egress
M5 is **100% pure embedded**:
- **Graph & Symbols**: Local SQLite database (`.m5/local_graph.db`).
- **Semantic Vectors**: Embedded Qdrant Rust engine (`.m5/qdrant_db`) running on CPU via ONNX Runtime (`BAAI/bge-small-en-v1.5`).
- **Syntax Parsing**: Tree-sitter C bindings.

Nothing runs in the background when you aren't using it. No Docker containers. No ports open. No code ever leaves your machine.

### 2. Exact AST match ranking (No more nearby file noise)
Traditional vector search often ranks nearby files, READMEs, or comments above the actual function definition. M5 runs a dedicated AST symbol pass first. If you ask for `calculate_tax`, the actual `def calculate_tax(...)` function is always returned at **Rank 1 with 100% confidence**.

### 3. Full verbatim source code (No truncation slop)
Target definitions are returned with their complete bodies intact — never chopped in half with `... [truncated]` markers. Secondary/supporting chunks include structured summaries (`signature`, `line_range`, `callers_count`, `callees_count`) to keep context windows compact without overflowing IDE buffers into annoying temporary files.

### 4. End-to-end execution flow diagrams
M5 traces the multi-hop call graph and provides a visual flow summary:
```text
Entry: [src/api/routes.py (checkout_endpoint)] --> Target: [process_payment] --> Leaves: [stripe.Charge.create, db.save_order]
```

### 5. Automated completeness checks
M5 tells the agent whether the full path was traced or where it terminated:
```json
"completeness_check": {
  "fully_traced": false,
  "entry_points": ["src/api/routes.py (checkout_endpoint)"],
  "target_symbols": ["process_payment"],
  "terminations": ["external/stdlib (stripe.Charge.create)", "db.save_order"],
  "unresolved_calls": ["stripe.Charge.create"]
}
```

### 6. Transparent token savings metrics
Every retrieval reports the exact token impact:
```json
"metrics": {
  "retrieved_tokens": 1420,
  "whole_files_tokens": 12850,
  "tokens_saved": 11430,
  "token_savings_percent": 88.9,
  "confidence_score": 0.96,
  "confidence_rating": "VERY_HIGH",
  "search_precision": "exact_ast_symbol"
}
```

### 7. Auto-healing indexes
If an agent connects to a new workspace where `m5 build` hasn't been run yet, M5 detects the empty index and automatically runs an initial scan on the first request. The agent never fails with an empty-index error.

---

## CLI Commands

M5 comes with a full CLI for terminal power users:

| Command | What it does | Example |
| :--- | :--- | :--- |
| `m5 setup` | Interactive setup guide for Cursor, Claude, Windsurf, and VS Code | `m5 setup` |
| `m5 build` | Scans workspace and builds the AST graph + vectors | `m5 build .` |
| `m5 trace <query>` | 1-shot deep investigation: verbatim source + callers + callees + flow | `m5 trace "calculate_tax"` |
| `m5 peek <sym\|file>` | Inspect a symbol's code & callers, or view a line-numbered file | `m5 peek HybridRetriever` |
| `m5 find <pattern>` | Search AST symbols by name or type (`--kind function`, `--limit 10`) | `m5 find "AuthToken"` |
| `m5 callers <sym>` | List every function and file that calls this symbol | `m5 callers process_payment` |
| `m5 callees <sym>` | List every function called by this symbol | `m5 callees handle_request` |
| `m5 blast <sym>` | Multi-hop blast radius analysis before refactoring (`--depth 2`) | `m5 blast DatabasePool` |
| `m5 diff-tests` | Find which tests are impacted by staged git changes | `git diff --name-only \| m5 diff-tests --stdin` |
| `m5 live` | Incremental file watcher (<50ms re-index on save) | `m5 live` |
| `m5 view` | Launches interactive browser visualizer on `http://127.0.0.1:5555` | `m5 view` |
| `m5 stats` | Shows indexed files, symbols, call edges, and DB size | `m5 stats` |
| `m5 dump [file]` | Export pre-computed index bundle for team sharing or CI | `m5 dump index.tar.gz` |
| `m5 pull <url>` | Pull pre-computed index bundle from CI cache | `m5 pull https://ci.internal/m5.tar.gz` |
| `m5 rules` | Injects agent rules into `AGENTS.md` / `CLAUDE.md` / `.cursorrules` | `m5 rules` |
| `m5 purge` | Safely removes `.m5/` index folder from the project | `m5 purge` |
| `m5 serve` | Starts the Model Context Protocol (MCP) server over stdio | `m5 serve` |
| `m5 version` | Prints installed M5 version | `m5 version` |

---

## MCP Tools Reference (For AI Agents)

When running `m5 serve`, M5 exposes 7 native MCP tools:

### 1. `m5_get_context`
**The primary tool for agents.** Performs hybrid retrieval, extracts exact AST definitions, traces upstream callers and downstream callees, and builds the execution flow.
- **Parameters**: `query` (string), `top_k` (optional int, default 5), `expand_dependencies` (optional bool).

### 2. `m5_search_code`
Searches code using combined BM25 keyword matching + dense vector semantics with Reciprocal Rank Fusion.
- **Parameters**: `query` (string), `top_k` (optional int, default 10).

### 3. `m5_find_symbol_references`
Locates the exact AST definition and all known caller sites across the repository without false positives.
- **Parameters**: `symbol_name` (string).

### 4. `m5_get_dependencies`
Returns all files and external modules imported or used by a target file.
- **Parameters**: `file_path` (string).

### 5. `m5_get_dependents`
Returns all files that import or depend on a target file (essential for checking blast radius before deleting or refactoring).
- **Parameters**: `file_path` (string).

### 6. `m5_read_lines`
Reads a specific line range with line numbers and optional context padding, without reading the whole file.
- **Parameters**: `file_path` (string), `start_line` (int), `end_line` (int), `context_lines` (optional int).

### 7. `m5_index_status`
Returns real-time status of the local index: total files, symbols, call edges, database size, and whether the index is fresh.

---

## Supported Languages

M5 uses Tree-sitter grammars to parse AST structures across 16+ languages:

| Category | Languages |
| :--- | :--- |
| **Backend & Systems** | Python, Go, Rust, Java, C, C++, C#, Ruby, PHP |
| **Web & Frontend** | TypeScript, JavaScript, JSX, TSX, HTML, CSS |
| **Mobile & Other** | Swift, Kotlin, Dart, Scala |

---

## Interactive Visualizer (`m5 view`)

Want to inspect your codebase's call graph visually?
```bash
m5 view
```
Opens a lightweight local web interface at `http://127.0.0.1:5555` where you can:
- Explore dependency clusters and module boundaries.
- Search symbols and see their upstream and downstream connections in real time.
- Inspect symbol source code and docstrings side-by-side.

---

## CI/CD & Team Sharing

Don't want every team member to re-index large monorepos from scratch?
```bash
# In your CI pipeline after build:
m5 build .
m5 dump ./m5-cache.tar.gz

# In developer onboarding or devcontainer setup:
m5 pull https://your-internal-bucket/m5-cache.tar.gz
```

---

## Enterprise / Multi-Tenant Features

For teams running M5 as a centralized internal service or VPC deployment:
- **Repository ACL Pre-Filtering (`repo_filter`)**: Queries filter out unauthorized repositories at the database level before any similarity or ranking computation.
- **External Qdrant Support**: Set `QDRANT_URL` and `QDRANT_API_KEY` to connect to a centralized remote Qdrant cluster instead of embedded storage.
- **Tenant Isolation**: Namespaces graph databases and vector collections by `(org_id, dept_id, repo_id)`.
- **FastAPI REST Server**: Run `python -m src.server --host 0.0.0.0 --port 8000` to expose M5 over HTTP with Bearer token authentication.
- **Webhook Delta Sync**: Point GitHub/GitLab webhooks to `POST /api/v1/webhook/github` for automatic <300ms incremental re-indexing on commit pushes.

---

## Development & Testing

```bash
git clone https://github.com/lazyserp/M5-v2.git
cd M5-v2
pip install -e ".[dev]"

# Run full test suite (56 tests including the agent eval suite)
pytest test
```

---

## License

MIT License. Free to use, modify, and distribute.
