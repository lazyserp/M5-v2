# M5 v2 — Production Deployment Architecture & Pre-Flight Checklist

This document is the authoritative checklist for deploying M5 v2 as a secure, high-performance, multi-tenant SaaS context engine on AWS.

---

## 1. System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CLIENT / DEVELOPER TIER                           │
│  VS Code (Copilot)  •  Cursor IDE  •  Claude Code CLI  •  Internal Agents    │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTPS (TLS 1.3 / Port 443)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SECURITY & INGRESS GATEWAY                          │
│  • Nginx Reverse Proxy / AWS Application Load Balancer                      │
│  • Let's Encrypt / ACM SSL Certificate (Auto-renewed)                       │
│  • Security Group: Inbound Port 443 & 80 ONLY                               │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP (Internal Bridge Port 8000)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  AWS EC2 HOST (Recommended: c6i.large or t3.large / Ubuntu 24.04 LTS)       │
│                                                                             │
│  ┌─────────────────────────────────────┐  ┌──────────────────────────────┐  │
│  │  M5 Engine (`m5-engine`)            │  │  Qdrant Vector DB (`m5-qdrant`)│ │
│  │  • API Key Guard (`keys.json`)      │  │  • Port 6333 (Internal only) │  │
│  │  • AST Parser (Tree-Sitter)         │──│  • Multi-tenant collections  │  │
│  │  • Hybrid Search (Dense + BM25)     │  │  • Cosine Distance Index     │  │
│  │  • GitHub Webhook Delta Sync        │  │  • In-Memory Payload Cache   │  │
│  └──────────────────┬──────────────────┘  └──────────────┬───────────────┘  │
└─────────────────────┼────────────────────────────────────┼──────────────────┘
                      │                                    │
                      ▼                                    ▼
┌────────────────────────────────────────┐ ┌──────────────────────────────────┐
│  PERSISTENT STORAGE (AWS KMS Encrypted)│ │  DISASTER RECOVERY (Amazon S3)   │
│  • 50GB gp3 EBS Volume (AES-256)       │ │  • Daily Qdrant vector snapshots │
│  • SQLite AST Graphs & Import Edges    │ │  • Encrypted S3 Bucket (SSE-KMS) │
│  • Hashed API Key Storage (`keys.json`)│ │  • 30-day retention lifecycle   │
└────────────────────────────────────────┘ └──────────────────────────────────┘
```

---

## 2. Infrastructure Prerequisites

| Component | Minimum Specification | Recommended Specification | Purpose |
|---|---|---|---|
| **Cloud Provider** | AWS (or GCP / Azure) | AWS EC2 (US-East / EU-Central) | Host server infrastructure |
| **Compute Type** | `t3.large` (2 vCPU, 8GB RAM) | `c6i.large` (2 vCPU Compute-Optimized) | Fast ONNX vector embedding inference |
| **Storage Volume** | 30GB gp3 EBS | 50GB gp3 EBS (3000 IOPS) | AST database & vector storage |
| **Storage Security**| EBS Default Encryption | **AWS KMS Customer Managed Key** | Full AES-256 compliance for customer code |
| **Operating System**| Ubuntu 22.04 LTS | Ubuntu 24.04 LTS | Docker host environment |
| **Container Engine**| Docker v24+ | Docker v26+ with Compose v2 | Multi-container orchestration |
| **Networking** | Elastic IP | Static Elastic IP attached to EC2 | Persistent DNS endpoint |
| **Domain & DNS** | Custom Domain | `api.yourm5domain.com` (Cloudflare / Route 53) | Secure public entry point |

---

## 3. Pre-Flight Security & Hardening Checklist

### 🔒 Network & Firewall
- [ ] **Lock Inbound Security Groups**:
  - `Port 443 (HTTPS)`: Open to `0.0.0.0/0` (Public).
  - `Port 80 (HTTP)`: Open to `0.0.0.0/0` (Redirects to 443 + Let's Encrypt renewal).
  - `Port 22 (SSH)`: **Restricted to your company/VPN IP only** (or AWS SSM Session Manager).
  - `Port 8000 & Port 6333`: **BLOCKED from public internet** (internal Docker network only).
- [ ] **SSL / TLS Certificate**: Valid TLS 1.3 certificate issued via Certbot (`certbot --nginx -d api.yourm5domain.com`).

### 🔑 Credentials & Environment Variables
- [ ] **Generate Master Admin Key**:
  ```bash
  python3 -c "import secrets; print('m5_admin_' + secrets.token_hex(32))"
  ```
- [ ] **Configure Production `.env`**:
  ```env
  M5_ADMIN_KEY=m5_admin_64_CHAR_HEX_KEY
  QDRANT_URL=http://qdrant:6333
  QDRANT_API_KEY=strong_internal_password_here
  M5_CORS_ORIGINS=https://app.yourm5domain.com
  M5_WEBHOOK_SECRET=your_github_webhook_hmac_secret
  ```
- [ ] **Git PAT for Private Repos**: Create a GitHub Machine User / Service Account with `repo:read` scope for cloning customer repositories.

### 🛡️ Multi-Tenant Isolation Pre-Checks
- [ ] Ensure **every customer** is provisioned with a distinct `org_id` (e.g. `POST /api/admin/keys` with `org_id="acme_corp"`).
- [ ] Verify that customer API keys cannot query other customer namespaces.

---

## 4. Pre-Deployment 5-Minute Sanity Test

Run these 5 validation steps on the EC2 server before routing paying customer traffic:

### Step 1: Health Probes
```bash
curl -i https://api.yourm5domain.com/health
curl -i https://api.yourm5domain.com/ready
# Both must return HTTP 200 OK
```

### Step 2: Test Admin Key Authorization
```bash
# Must return 401 Unauthorized without header
curl -i -X POST https://api.yourm5domain.com/api/admin/keys

# Must return 200 OK with valid Admin Key
curl -i -X POST https://api.yourm5domain.com/api/admin/keys \
  -H "Authorization: Bearer YOUR_M5_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"caller_name": "Sanity Test Key", "org_id": "test_org"}'
```

### Step 3: Test Dynamic Git Repository Indexing
```bash
curl -i -X POST https://api.yourm5domain.com/api/index/git \
  -H "Authorization: Bearer YOUR_M5_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/your-org/test-repo.git",
    "access_token": "ghp_your_token",
    "org_id": "test_org"
  }'
```

### Step 4: Test Remote MCP Endpoint over HTTPS
```bash
curl -i -X POST https://api.yourm5domain.com/mcp \
  -H "Authorization: Bearer m5_live_GENERATED_TEST_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "m5_get_context",
      "arguments": {"query": "sanity check query"}
    }
  }'
```

### Step 5: Run Automated Load Benchmark
```bash
python3 benchmark_load_test.py
# Verify: 100% Success Rate, P50 latency < 500ms
```

---

## 5. Automated Backup & Disaster Recovery Setup

Set up a daily cron job on EC2 to snapshot Qdrant vector storage and AST graphs to Amazon S3:

```bash
# /etc/cron.daily/m5-backup.sh
#!/bin/bash
DATE=$(date +\%Y\%m\%d)
tar -czf /tmp/m5-backup-$DATE.tar.gz /opt/m5-v2/storage
aws s3 cp /tmp/m5-backup-$DATE.tar.gz s3://your-m5-backups-bucket/daily/
rm /tmp/m5-backup-$DATE.tar.gz
```
