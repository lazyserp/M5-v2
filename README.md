# M5 v2 — Intelligent Code Context Engine

> **M5 is an invisible, permission-aware code context layer that plugs into AI tools developers already use.** Copilot, Claude Code, Cursor, and ChatGPT call M5 to retrieve precise, cited AST code chunks and dependency graphs from your repositories. **M5 supplies context; your AI produces the answer.**

---

## ⚡ 1-Minute Quickstart (Local Development)

### 1. Configure `.env`
```powershell
Copy-Item .env.example .env
```
Ensure your `.env` contains your target repository path:
```env
M5_ADMIN_KEY=m5_admin_1ad80533d21d9cec14f3ddb12859a7d0562954efc95c9f08
WORKSPACE_ROOT=D:\your-project\backend
QDRANT_URL=http://qdrant:6333
```

### 2. Start M5 with Docker Compose
```powershell
docker compose up --build -d
```
- **M5 Context Engine**: `http://localhost:8000`
- **Remote MCP Endpoint**: `http://localhost:8000/mcp`
- **Qdrant Web Dashboard**: `http://localhost:6333/dashboard`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`

---

## 🔑 Create an API Key for Your IDE

Generate a client API key using your master `M5_ADMIN_KEY`:

```powershell
Invoke-RestMethod -Method POST `
  -Uri "http://localhost:8000/api/admin/keys" `
  -Headers @{
    "Authorization" = "Bearer m5_admin_1ad80533d21d9cec14f3ddb12859a7d0562954efc95c9f08"
    "Content-Type"  = "application/json"
  } `
  -Body '{"caller_name": "Developer - Copilot", "org_id": "default_org"}'
```

Save the returned key (e.g. `m5_live_1a22c5e1b1f2b9dc576f8382a4cf5e69bc683d244b1dafe5`).

---

## 🔌 Connect to Your AI Editor

### VS Code / GitHub Copilot
Create `.vscode/mcp.json` in your workspace:
```json
{
  "servers": {
    "m5-context": {
      "type": "http",
      "url": "http://localhost:8000/mcp",
      "headers": {
        "Authorization": "Bearer m5_live_YOUR_KEY_HERE"
      }
    }
  }
}
```

### Claude Desktop / Cursor
Add to your Claude Desktop config (`%APPDATA%\Claude\claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "m5-context": {
      "url": "http://localhost:8000/mcp",
      "headers": {
        "Authorization": "Bearer m5_live_YOUR_KEY_HERE"
      }
    }
  }
}
```

Reload your IDE, open chat, and ask:
> *"Where is the payment retry logic defined and what services call it?"*

Your AI will automatically invoke `m5_get_context` and return exact, cited code lines.

---

## 🏛️ Architecture & Deployment

M5 is structured around **2 clean models**:
1. **Development Model**: Local Docker Compose (FastAPI + Qdrant Web UI).
2. **Production Paying Model**: Hosted on AWS EC2 behind HTTPS with KMS encryption for paying clients.

📖 **Read the complete [DEPLOYMENT_GUIDE.md](file:///D:/M5%20v2/DEPLOYMENT_GUIDE.md) for full AWS production setup, security, and multi-tenant isolation.**

---

## 🛠️ REST API Reference

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/health` | `GET` | Public | Health check & uptime probe |
| `/ready` | `GET` | Public | Kubernetes / load balancer readiness probe |
| `/api/admin/keys` | `POST` | Admin Key | Create a new developer API key |
| `/api/admin/keys` | `GET` | Admin Key | List active API keys |
| `/api/admin/keys/{id}`| `DELETE` | Admin Key | Revoke an API key |
| `/api/context` | `POST` | API Key | Query hybrid context bundle directly via JSON |
| `/mcp` | `POST` | API Key | JSON-RPC 2.0 Remote MCP endpoint for AI editors |
| `/api/index/status` | `GET` | Admin Key | Live indexing progress and block counts |
| `/api/index/git` | `POST` | Admin Key | Clone & index a remote GitHub/GitLab repo |
| `/api/webhooks/github`| `POST` | HMAC Secret | Sub-second delta sync on GitHub push events |
