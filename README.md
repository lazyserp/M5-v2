# M5 v2 — Context Engine for Regulated Codebases

**M5 is a pure context provider** — it finds and returns the right code to your AI. It does not reason or answer on its own.

Built for engineering teams at regulated companies (fintech, healthcare, legal, government) where source code cannot leave the building, but developers still want Claude, Copilot, or an internal AI to reason well over the codebase.

---

## How M5 fits in your stack

```
┌──────────────────────────────────────────────────────────┐
│                  Your Company's Perimeter                │
│                                                          │
│   ┌──────────────┐    MCP / REST    ┌────────────────┐  │
│   │  Your        │ ◄──────────────► │   M5 v2        │  │
│   │  AI of       │   context only   │   (runs here,  │  │
│   │  choice      │                  │   air-gapped)  │  │
│   │  (Claude,    │                  └───────┬────────┘  │
│   │  Copilot,    │                          │           │
│   │  internal)   │                  ┌───────▼────────┐  │
│   └──────────────┘                  │  Your Codebase │  │
│                                     └────────────────┘  │
│                                                          │
│   ✅ M5 never sends code to external APIs               │
│   ✅ M5 never reasons or answers on its own             │
│   ✅ Every retrieval is audit-logged                    │
└──────────────────────────────────────────────────────────┘
```

---

## 🌟 Core Capabilities

### Retrieval (the product)

| Feature | What it does |
|---------|-------------|
| **Hybrid Search** | BM25 keyword + dense vector embeddings fused with Reciprocal Rank Fusion |
| **Bundled `get_context`** | One call → ranked chunks + dependency graph expansion + dedup |
| **Dependency Graph** | SQLite-backed, maps imports/exports across the whole codebase |
| **Progressive Indexing** | Tier-0 instant boot (<1s via AST), Tier-1/2 async vector embedding |
| **Git URL Ingestion** | Shallow-clones any GitHub/GitLab repo and indexes it immediately |
| **Real-Time Webhook Sync** | HMAC-verified GitHub push webhook syncs diffs in <200ms |

### Compliance (the differentiator)

| Feature | What it does |
|---------|-------------|
| **Audit Log** | Every retrieval is immutably logged with exact file paths + line ranges returned |
| **API Keys** | Per-caller keys with repo-scoped access; stored as salted hashes (never plaintext) |
| **Denied-request logging** | Failed / out-of-scope requests are also logged — often more interesting to security teams |
| **ACL Hook** | `PermissionChecker` stub ready for Okta/Azure AD group sync |
| **Multi-Tenant Isolation** | Strict `(org_id, dept_id, repo_id)` namespacing; proven by automated tests |
| **Usage Reporting** | Token savings reports — M5 sends only relevant chunks, not whole files |

### Integration surfaces

| Surface | Use case |
|---------|---------|
| `POST /api/context` | Primary REST endpoint for any LLM integration |
| MCP tool `m5_get_context` | Native Cursor / Claude Desktop / Antigravity IDE integration |
| `GET /api/audit/query` | Compliance team review dashboard |
| `GET /api/audit/export` | SIEM ingestion (Splunk, Datadog, etc.) |
| `POST /api/admin/keys` | API key lifecycle management |

---

## 🚀 Quickstart

### 1. Install

```bash
git clone https://github.com/your-org/m5-v2.git
cd m5-v2

python -m venv venv
# Windows:
.\\venv\\Scripts\\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure (`.env`)

```env
# Admin key — required to create API keys and access audit logs
M5_ADMIN_KEY=your_strong_admin_secret

# Optional: MCP API key (used when running as Claude Desktop / Cursor MCP server)
# M5_MCP_API_KEY=m5_yourkey...

# Dev/Demo only — enables M5's own LLM agent loop (NOT for production)
# M5_ENABLE_DEV_AGENT_MODE=false
```

### 3. Start the server

```bash
python -m uvicorn src.server:app --host 0.0.0.0 --port 8000
```

### 4. Create an API key

```bash
curl -X POST "http://localhost:8000/api/admin/keys" \
     -H "Authorization: Bearer your_strong_admin_secret" \
     -H "Content-Type: application/json" \
     -d '{"caller_name": "Claude Desktop - Alice", "org_id": "acme", "scopes": ["*"]}'
```

Save the returned `key` — it is shown only once.

### 5. Index a repository

```bash
curl -X POST "http://localhost:8000/api/index/git" \
     -H "Content-Type: application/json" \
     -d '{"repo_url": "https://github.com/psf/requests", "dept_id": "core_infra"}'
```

### 6. Fetch context

```bash
curl -X POST "http://localhost:8000/api/context" \
     -H "Content-Type: application/json" \
     -d '{
       "query": "Where is the HTTP session adapter defined?",
       "org_id": "psf",
       "dept_id": "core_infra",
       "repo_id": "requests",
       "expand_dependencies": true
     }'
```

---

## 🔌 MCP Integration (Claude Desktop / Cursor)

Add to your `claude_desktop_config.json` or `mcp_config.json`:

```json
{
  "mcpServers": {
    "m5-engine": {
      "command": "python",
      "args": ["-m", "src.mcp_server"],
      "cwd": "/path/to/m5-v2",
      "env": {
        "M5_MCP_API_KEY": "m5_yourkey..."
      }
    }
  }
}
```

Available MCP tools: `m5_get_context`, `m5_search_code`, `m5_read_lines`, `m5_get_dependencies`, `m5_get_dependents`, `m5_find_symbol_references`, `m5_index_git_repo`, `m5_index_status`.

---

## 🔍 Audit & Compliance

```bash
# Query the audit log (who saw what, when)
curl "http://localhost:8000/api/audit/query?org_id=acme&page=1" \
     -H "Authorization: Bearer your_strong_admin_secret"

# Export full audit log as NDJSON (for SIEM ingestion)
curl "http://localhost:8000/api/audit/export?org_id=acme" \
     -H "Authorization: Bearer your_strong_admin_secret"

# Token usage summary (last 30 days)
curl "http://localhost:8000/api/usage/summary?org_id=acme&period=30d" \
     -H "Authorization: Bearer your_strong_admin_secret"
```

---

## 🧪 Testing

```bash
python -m pytest test/ -v
```

The test suite includes `test_tenant_isolation.py` — a hard gate that proves zero cross-tenant data leakage at the org, dept, and repo levels. This runs on every PR.

---

## ⚗️ Experimental (Opt-In Only)

The `experimental/` folder contains features that go beyond M5's core mission:

- **Agent loop** — M5 running its own LLM to reason over code (duplicates what Claude/Cursor already does)
- **File writing** — `write_to_file`, `replace_file_content`
- **Shell execution** — `run_command`

These are disabled by default. To enable for local demos:

```env
M5_ENABLE_DEV_AGENT_MODE=true
```

> ⚠️ Never enable in production. See `experimental/README.md` for details.
