# M5 v2 — Deployment & Infrastructure Guide

This is the authoritative guide for running M5 across **Development** and **AWS Production**.

---

## The 2-Model Framework

```
 MODEL 1: Local Development Model (Your Machine)
 ────────────────────────────────────────────────
 • Stack: Docker Compose (FastAPI Engine + Qdrant on localhost:6333)
 • Dashboard: http://localhost:6333/dashboard
 • MCP Endpoint: http://localhost:8000/mcp
 • Purpose: Local development, feature testing, vector inspection

 MODEL 2: Deployed Paying Model (AWS Production SaaS)
 ────────────────────────────────────────────────────
 • Stack: AWS EC2 (Docker) + EBS Encrypted Storage + S3 Snapshots + Nginx TLS 1.3
 • Encryption: AWS KMS AES-256 at-rest, TLS 1.3 in-transit
 • MCP Endpoint: https://api.yourm5domain.com/mcp
 • Purpose: Serve paying B2B clients who connect Claude/Copilot via API keys
```

---

# Model 1: Local Development Setup

### 1. Requirements
- Docker Desktop installed and running.
- Local repository configured in `.env`.

### 2. Commands
```powershell
# Start the full stack (FastAPI + Qdrant container)
docker compose up --build -d

# View live logs
docker compose logs -f m5-engine

# Stop the stack
docker compose down
```

### 3. Local Endpoints
- **M5 Context Engine**: `http://localhost:8000`
- **Qdrant Vector Dashboard**: `http://localhost:6333/dashboard`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`

---

# Model 2: AWS Production Deployment (Paying Clients)

In production, M5 runs as a managed SaaS on AWS. Paying clients **do not run Docker or servers on their machines**; they simply connect over HTTPS.

```
┌────────────────────────────────────────────────────────┐
│  AWS Cloud (EC2 + Encrypted EBS + S3)                  │
│                                                        │
│  ┌───────────────────────┐   ┌──────────────────────┐  │
│  │  Nginx Reverse Proxy  │   │  AWS KMS Encryption  │  │
│  │  (HTTPS / TLS 1.3)    │   │  (AES-256 at rest)   │  │
│  └───────────┬───────────┘   └──────────┬───────────┘  │
│              │                          │              │
│  ┌───────────▼───────────┐   ┌──────────▼───────────┐  │
│  │  M5 Engine (FastAPI)  │───│  Qdrant (Encrypted)  │  │
│  │  • API Key Auth       │   │  • Tenant Isolation  │  │
│  │  • Git Webhooks       │   │  • S3 Snapshots      │  │
│  └───────────────────────┘   └──────────────────────┘  │
└──────────────────────────────┬─────────────────────────┘
                               │ HTTPS (`https://api.yourm5domain.com/mcp`)
             ┌─────────────────┴─────────────────┐
             ▼                                   ▼
┌─────────────────────────┐         ┌─────────────────────────┐
│  Developer A (VS Code)  │         │  Developer B (Cursor)   │
│  Key: `m5_live_clientA` │         │  Key: `m5_live_clientB` │
└─────────────────────────┘         └─────────────────────────┘
```

### Production Setup on AWS EC2 (Ubuntu 22.04 LTS / 24.04 LTS)

#### 1. EC2 Instance Sizing
- **Instance Type**: `t3.large` (2 vCPU, 8GB RAM) or `c6i.large` (Compute-optimized for vector embeddings).
- **Storage**: 50GB gp3 EBS Volume (enable **EBS Encryption with AWS KMS**).

#### 2. Install Docker on EC2
```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo usermod -aG docker ubuntu
```

#### 3. Clone and Configure M5 on EC2
```bash
git clone https://github.com/your-org/m5-v2.git /opt/m5-v2
cd /opt/m5-v2

# Generate a strong production admin key
python3 -c "import secrets; print('m5_admin_' + secrets.token_hex(32))"

# Copy and edit production .env
cp .env.example .env
nano .env
```

#### 4. Configure Nginx with SSL (Let's Encrypt)
Create `/etc/nginx/sites-available/m5.conf`:
```nginx
server {
    server_name api.yourm5domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Keep alive for MCP streaming
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
```

Enable SSL:
```bash
sudo ln -s /etc/nginx/sites-available/m5.conf /etc/nginx/sites-enabled/
sudo certbot --nginx -d api.yourm5domain.com
```

#### 5. Launch Production M5
```bash
docker compose up --build -d
```

---

## 🔒 Security, Encryption & Client Trust

### 1. In-Transit Encryption
All communication between client IDEs and your M5 server is encrypted using **TLS 1.3 / HTTPS**.

### 2. At-Rest Encryption
- Vector data on EBS is encrypted with **AWS KMS (AES-256)**.
- S3 backups and snapshots use **SSE-KMS**.

### 3. Multi-Tenant Isolation
- Every company / customer is assigned a distinct tenant ID (`org_id`).
- Qdrant collections and SQLite AST graphs are namespaced strictly: `m5_{org_id}_{dept_id}_{repo_id}`.
- Client API keys can **only** query their own tenant namespace.

---

## 💳 Customer Onboarding & Monetization Workflow

1. **Client Signs Up**: On your website, client selects a plan (e.g. 5 seats for $150/month).
2. **Issue API Key**: Your backend calls your M5 server to create their key:
   ```bash
   POST https://api.yourm5domain.com/api/admin/keys
   Body: {"caller_name": "Acme Corp Team", "org_id": "acme_corp"}
   ```
3. **Index Their Repo**: Call `/api/index/git` with their GitHub repository URL and webhook secret.
4. **Client Setup**: Acme Corp developers paste into their `.vscode/mcp.json`:
   ```json
   {
     "servers": {
       "m5-context": {
         "type": "http",
         "url": "https://api.yourm5domain.com/mcp",
         "headers": {
           "Authorization": "Bearer m5_live_acme_corp_key"
         }
       }
     }
   }
   ```
5. **Subscription Cancellation / Revocation**: If subscription ends, call `DELETE /api/admin/keys/{key_id}`. Access is immediately revoked.
