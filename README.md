# M5 Engine

> **The zero-cost, air-gapped AST code intelligence & dependency graph engine for AI coding agents.**  
> Give Cursor, Claude Code, Windsurf, or Copilot instant whole-repo execution context without burning LLM tokens, cluttering your repo with markdown summaries, or waiting on grep. Runs 100% locally on your machine — zero API keys to index, zero Docker, zero open ports, zero code egress.

[![PyPI version](https://img.shields.io/pypi/v/m5-engine.svg)](https://pypi.org/project/m5-engine/)
[![License: Proprietary](https://img.shields.io/badge/License-Proprietary-red.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)

---

## Why M5?

If you've used AI coding agents on codebases with more than 50 files, you've probably hit the **Agent Context Trap**:

```
Without M5 (The Grep / Naive RAG Death Spiral):
1. You ask your agent to fix a bug or trace an execution flow.
2. The agent runs grep, gets 150 hits, and starts reading entire 1,500-line files one by one.
3. Within 3 turns, it burns 50,000 tokens, loses track of previous instructions, and still
   misses the actual caller because it went through an interface or helper.

With M5 (Surgical 1-Shot Retrieval):
1. The agent calls m5_get_context("checkout_flow").
2. M5 traverses the AST call graph and dense semantic index in <20ms.
3. The agent receives:
   - The exact target function at Rank 1 (verbatim source, never truncated).
   - All upstream entry points (controllers, routes, CLI handlers).
   - All downstream callees (database queries, external APIs).
   - An ASCII execution flow diagram and a verified completeness check.
   Total context cost: under 2,000 tokens (up to 90% token savings).
```

---

## How M5 Compares

Not all code graph tools are built the same. Other tools either bill your API key to summarize files, clutter your repository with generated markdown documents, or dump fuzzy multi-modal graphs into your agent's context window.

| Feature / Metric | **M5 Engine** | **Graft** (`@nanonets/graft`) | **Graphify** (`graphifyy`) | **Naive Grep / Flat RAG** |
| :--- | :---: | :---: | :---: | :---: |
| **Cost to Index** | **$0.00 (Zero LLM tokens)** | Burns LLM API tokens for summaries | Burns LLM tokens for extractions | $0.00 |
| **Privacy & Security** | **100% Offline & Air-Gapped** | May leak code to LLM APIs | May send content to LLM APIs | Local |
| **Index Footprint** | **Clean local SQLite + Rust Qdrant (`.m5/`)** | Pollutes repo with markdown files | Bulky multi-file graph export | None |
| **Live Sync on Save** | **<50ms incremental watcher (`m5 live`)** | Slow re-summarization pass | Manual re-run | Instant (raw text) |
| **Call Graph Precision** | **Exact AST call paths + leaf terminations** | High-level summary links | Entity relationship graph | None (keyword text matches) |
| **Completeness Check** | **Yes (`fully_traced: true/false`)** | No | No | No |
| **Visual Flow Diagram** | **ASCII execution chain in prompt** | No | Graph visualization files | None |
| **Visual Dependency UI** | **Built-in (`m5 view` local web UI)** | None | Static graph viewer | None |
| **CI/CD Cache Sharing** | **`m5 dump` & `m5 pull` bundles** | No standard bundle | No | Git |
| **Git Impact Analysis** | **`m5 blast` & `m5 diff-tests`** | No | Blast radius only | None |

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

## What Makes M5 Different?

### 1. Zero LLM Cost, Zero Docker, Zero Network Egress
M5 is **100% pure embedded**:
- **Graph & Symbols**: Local SQLite database (`.m5/local_graph.db`).
- **Semantic Vectors**: Embedded Qdrant Rust engine (`.m5/qdrant_db`) running on CPU via ONNX Runtime (`BAAI/bge-small-en-v1.5`).
- **Syntax Parsing**: Tree-sitter native C bindings.

No external LLM calls are needed to index your project. No Docker containers. No open ports. No code ever leaves your workstation.

### 2. Exact AST Match Ranking (No More Nearby File Noise)
Traditional vector search often ranks nearby files, READMEs, or comments above the actual function definition. M5 runs a dedicated AST symbol pass first. If you ask for `calculate_tax`, the actual `def calculate_tax(...)` function is always returned at **Rank 1 with 100% confidence**.

### 3. Full Verbatim Source Code (No Truncation Slop)
Target definitions are returned with their complete bodies intact — never chopped in half with `... [truncated]` markers. Secondary/supporting chunks include structured summaries (`signature`, `line_range`, `callers_count`, `callees_count`) to keep context windows compact without overflowing IDE buffers into annoying temporary files.

### 4. End-to-End Execution Flow Diagrams
M5 traces the multi-hop call graph and provides a visual flow summary directly into the agent's prompt:
```text
Entry: [src/api/routes.py (checkout_endpoint)] --> Target: [process_payment] --> Leaves: [stripe.Charge.create, db.save_order]
```

### 5. Automated Completeness Checks
M5 explicitly tells the agent whether the full execution path was resolved or where it terminated:
```json
"completeness_check": {
  "fully_traced": false,
  "entry_points": ["src/api/routes.py (checkout_endpoint)"],
  "target_symbols": ["process_payment"],
  "terminations": ["external/stdlib (stripe.Charge.create)", "db.save_order"],
  "unresolved_calls": ["stripe.Charge.create"]
}
```

### 6. Transparent Token Savings Metrics
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

### 7. Auto-Healing Indexes & Real-Time Sync
If an agent connects to a new workspace where `m5 build` hasn't been run yet, M5 detects the empty index and automatically runs an initial scan on the first request. While coding, `m5 live` updates the call graph incrementally on file save in under 50ms.

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

Copyright (c) 2024-2026 Aman. All rights reserved.

M5 is free for personal use, testing, and evaluation. Commercial redistribution, re-hosting, or sublicensing without prior written permission is prohibited. For enterprise or team commercial licensing, contact: lazyserp@gmail.com.
