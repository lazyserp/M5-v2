# M5 v2 — Complete Feature Specification & Capabilities Guide

> **M5 is an intelligent, permission-aware code context layer designed for AI coding agents.** It plugs seamlessly into Claude Code, Cursor, GitHub Copilot, VS Code, and JetBrains via the Model Context Protocol (MCP). Instead of brute-force dumping repositories into LLM prompts, M5 surgically extracts cited AST syntax trees, symbol relationships, and test impact graphs in milliseconds.

---

## 🏛️ Core Architectural Overview: The Dual-Engine Model

M5 operates on a **Dual-Engine Architecture** that adapts from a single developer laptop to a Fortune 500 enterprise VPC:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        M5 v2 DUAL-ENGINE MATRIX                        │
├───────────────────────────────────┬────────────────────────────────────┤
│ LOCAL ZERO-DOCKER MODE (FREE/OSS) │ ENTERPRISE CLOUD MODE (PAID SAAS)  │
├───────────────────────────────────┼────────────────────────────────────┤
│ • In-Process SQLite Engine (<25MB)│ • Central Multi-Tenant Cloud / VPC │
│ • 1-Click Auto-Installer          │ • "Zero-Minute Indexing" CI Sync   │
│ • 16+ Languages AST & Call Graph  │ • Cross-Repo & Microservice Graph  │
│ • Sub-300ms File Watcher Sync     │ • Test Blast-Radius Engine         │
│ • Native stdio MCP Protocol       │ • Air-Gapped GHES/GitLab RBAC/Logs │
└───────────────────────────────────┴────────────────────────────────────┘
```

---

## 🚀 Feature-by-Feature Deep Dive

---

### 1. 1-Click AI Editor Auto-Configuration (`m5 install`)
* **What It Does**: Eliminates 100% of the manual JSON configuration friction for developers.
* **How It Works**:
  * Scans the system for installed AI developer tools.
  * Automatically injects the correct MCP server configuration into:
    * **Claude Desktop** (`%APPDATA%/Claude/claude_desktop_config.json`)
    * **Claude Code CLI** (`~/.claude.json`)
    * **Cursor IDE** (`.cursor/mcp.json`)
    * **VS Code / GitHub Copilot** (`.vscode/mcp.json`)
    * **JetBrains IDEs / Antigravity**
* **Command**:
  ```powershell
  python -m src.cli.installer
  # Or with global pip: m5 install
  ```
* **Why It’s a Win**: Developers are up and running in **1 second** with zero copy-pasting.

---

### 2. Zero-Overhead In-Process SQLite Code Graph (`.m5/local_graph.db`)
* **What It Does**: Provides sub-millisecond symbol lookups and call graph traversals locally with zero infrastructure.
* **Technical Details**:
  * Runs an embedded **SQLite engine with Write-Ahead Logging (WAL)**.
  * Memory footprint is **$<25\text{MB}$** (down from 1.5GB previously).
  * Requires **Zero Docker, Zero Qdrant containers, and Zero background web daemons** on developer machines.
  * B-tree seeks locate symbol declarations and definitions in **$<0.5\text{ms}$**.

---

### 3. 16+ Language AST & Call-Edge Extractor
* **What It Does**: Performs deep syntactic parsing and dependency mapping across enterprise languages.
* **Supported Languages**:
  * **TypeScript (`.ts`), JavaScript (`.js`), TSX (`.tsx`), JSX (`.jsx`)**
  * **Python (`.py`)**
  * **Java (`.java`)**
  * **C (`.c`), C++ (`.cpp`, `.cc`, `.hpp`, `.h`)**
  * **C# (`.cs`)**
  * **Go (`.go`)**
  * **Rust (`.rs`)**
  * **Ruby (`.rb`)**
  * **PHP (`.php`)**
  * **Swift (`.swift`)**
  * **Kotlin (`.kt`, `.kts`)**
  * **Dart (`.dart`)**
  * **Scala (`.scala`)**
* **Extracted Entities**:
  * **Symbol Declarations**: Functions, methods, classes, structs, interfaces, type aliases, enums.
  * **Call Edges**: Direct function invocations, member calls, and caller/callee hierarchies.
  * **Imports**: Inter-file and third-party module imports.
  * **Resilient Fallback**: Automatically falls back to resilient syntax heuristics if optional language binaries are uninstalled, guaranteeing zero crashes.

---

### 4. Sub-300ms Real-Time File Watcher & Incremental Sync
* **What It Does**: Keeps the local code graph permanently synchronized with active code edits.
* **How It Works**:
  * An event-driven background watcher (`src/indexer/file_watcher.py`) monitors file system modification timestamps.
  * When a developer saves a file (Ctrl+S), M5 isolates and reparses **only that single file** in $<50\text{ms}$.
  * Clears stale symbol rows and updates the SQLite graph in a single atomic transaction.
* **Why It’s a Win**: The index is never stale, and developers never need to manually re-index.

---

### 5. Hybrid Reciprocal Rank Fusion (RRF) Search
* **What It Does**: Bridges the gap between exact compiler symbols and high-level human natural-language queries.
* **The Problem It Solves**:
  * Pure graph tools fail when developers ask conceptual questions (e.g., *"Where is the logic that checks if a user account is suspended?"* when the function is named `SanctionManager.verify_status()`).
* **M5 Solution**:
  * **Tier 1 (B-Tree Seek)**: Queries exact symbol matches in 0.1ms.
  * **Tier 2 (FTS5 BM25)**: Matches exact keywords and token stems across all code bodies.
  * **Tier 3 (Semantic Vectors)**: Uses dense vector embeddings (Qdrant / `sqlite-vec`) to find conceptual intent.
  * **Fusion (RRF)**: Combines scores using Reciprocal Rank Fusion to return 100% cited ground-truth AST blocks.

---

### 6. Automated Test Blast-Radius & Companion Test Discovery (`m5_get_test_impact`)
* **What It Does**: Informs AI coding agents which unit and integration test suites are affected when a function or file is modified.
* **How It Works**:
  * Traverses upstream caller edges to identify every function and file directly or indirectly dependent on the modified code.
  * Scans the workspace for matching companion test files (`test_*.py`, `*.spec.ts`, `*Test.java`).
  * Returns an actionable JSON payload with recommended test suites.
* **Example Agent Query**:
  ```json
  // Request
  {"name": "m5_get_test_impact", "arguments": {"symbol_name": "process_payment"}}
  
  // Response
  {
    "target_symbol": "process_payment",
    "impacted_callers_count": 8,
    "impacted_files": ["src/billing/service.py", "src/api/checkout.py"],
    "recommended_tests": ["test/test_billing.py", "test/test_checkout_flow.py"]
  }
  ```
* **Why It’s a Win**: Prevents AI agents from burning 5+ turns guessing which tests to run.

---

### 7. "Zero-Minute Indexing" via Team CI Sync (`m5 sync` & GitHub Actions)
* **What It Does**: Eliminates redundant local indexing across large engineering teams.
* **The Problem It Solves**:
  * In a 500-developer team with a 10M LOC monorepo, having every developer's laptop independently index the repository burns CPU, battery, and hours of setup.
* **M5 Solution**:
  * Headless GitHub Actions workflow ([`.github/workflows/m5-index.yml`](file:///d:/M5%20v2/.github/workflows/m5-index.yml)) pre-builds the AST graph on every git push.
  * Developers run `m5 sync` and download the pre-compiled graph cache in **under 3 seconds**.

---

### 8. Multi-Repository Context Federation (`m5_cross_repo_search`)
* **What It Does**: Connects distributed microservices and multiple repositories into a unified organizational context.
* **How It Works**:
  * Federates separate repository databases in `./storage/graphs/`.
  * Allows an AI agent working in a frontend Next.js repo to search API contracts, schemas, and endpoints defined in a backend Go or Python microservice.
* **Command / Tool**: `m5_cross_repo_search(query="createOrder")`.

---

### 9. Native `stdio` MCP JSON-RPC 2.0 Runner
* **What It Does**: Allows AI IDEs to communicate with M5 directly over standard input/output.
* **Why It Matters**:
  * Eliminates HTTP port bindings (`:8000`), port collisions, and firewall security warnings on local developer machines.
  * Cursor and Claude Code spawn M5 as an on-demand subprocess that exits cleanly when the session ends.

---

### 10. Enterprise Air-Gapped Governance & GHES Compliance
* **What It Does**: Solves data sovereignty and compliance requirements for enterprise companies in FinTech, Healthcare, and Defense.
* **Enterprise Features**:
  * **GitHub Enterprise Server (GHES) & GitLab Parity**: Functions 100% on-premise where cloud Copilot indexing is prohibited.
  * **Granular RBAC**: Admin-managed API keys with per-tenant/per-repository scoping and instant revocation (`/api/admin/keys`).
  * **Full Telemetry & Audit Trails**: Logs every code snippet retrieved by AI tools, duration, caller identity, and tenant namespace to Langfuse or local audit tables.
  * **Zero Cloud Code Leakage**: Code never leaves the enterprise VPC network.

---

## 🛠️ MCP Tool Reference Matrix for AI Editors

When M5 is connected to Claude Code, Cursor, or Copilot, the AI agent has access to these specialized tools:

| MCP Tool Name | Primary Purpose | Key Arguments |
|---|---|---|
| `m5_get_context` | **Flagship one-call context**: Returns ranked AST code chunks, dependency edges, companion tests, and token estimates. | `query`, `top_k`, `expand_dependencies` |
| `m5_get_test_impact` | **Test blast radius**: Recommends exact unit and integration tests affected by editing a function. | `symbol_name`, `file_path` |
| `m5_cross_repo_search`| **Multi-repo context**: Searches symbol definitions and API routes across microservice repositories. | `query` |
| `m5_search_code` | Raw hybrid keyword + AST block search. | `query`, `top_k` |
| `m5_get_dependencies`| Pulls direct import statements and outgoing dependencies for a file. | `file_path` |
| `m5_get_dependents` | Pulls all files and services that import or depend on a given file. | `file_path` |
| `m5_find_symbol_references`| Locates all files referencing a specific function/class name. | `symbol_name` |
| `m5_read_lines` | Streams exact line ranges from disk with configurable context padding. | `file_path`, `start_line`, `end_line` |
| `m5_index_git_repo` | Headless API to clone and index a remote repository into a tenant namespace. | `repo_url`, `branch`, `dept_id` |

---

## 💻 CLI Quick Reference (`m5` Command)

```bash
# Auto-configure all installed AI editors (Claude, Cursor, Copilot, VS Code)
m5 install

# Index current repository into local SQLite AST graph (<1s)
m5 init

# Start real-time file watcher (<50ms incremental sync on save)
m5 watch

# Pull pre-computed team index from CI cache ("Zero-Minute Indexing")
m5 sync <url>

# Export current index bundle for CI artifact upload
m5 export

# Check local SQLite graph statistics
m5 status

# Run MCP server in stdio mode (called automatically by IDEs)
m5 stdio
```
