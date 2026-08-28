# M5 v2 Product Launch Video — Script & Storyboard

**Title**: *M5 v2: The Invisible Code Context Layer for Enterprise AI*  
**Duration**: 2 Minutes (120 Seconds)  
**Style**: Stripe / Apple-style sleek product launch — smooth 2D motion graphics (0:00–1:00) transitioning into live terminal & IDE product demo (1:00–2:00).  
**Tone**: Technical, authoritative, futuristic, high-contrast dark mode aesthetic.

---

## Storyboard Overview

```
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                              VIDEO STRUCTURE (120 SECONDS)                             │
 └────────────────────────────────────────────────────────────────────────────────────────┘

  [ 0:00 - 0:15 ] Scene 1: The Problem (Cloud LLMs, Hallucinations & Context Slicing)
  [ 0:15 - 0:40 ] Scene 2: Introducing M5 (The Invisible Permission-Aware Context Layer)
  [ 0:40 - 1:00 ] Scene 3: Under the Hood (AST Parsing, Hybrid RRF & Instant Webhook Sync)
  [ 1:00 - 1:45 ] Scene 4: Live Product Demo (VS Code Copilot + M5 Remote MCP + Audit Log)
  [ 1:45 - 2:00 ] Scene 5: Outro & Call to Action (Enterprise Ready on Kubernetes)
```

---

## Scene-by-Scene Script & Animation Guide

### Scene 1: The Enterprise Problem (0:00 – 0:15)

* **Visuals (2D Animation)**:
  * Dark screen (`#0B0F19`). Red glowing alert lines.
  * An icon of an engineer typing in VS Code. A cloud LLM icon sits across a red security firewall.
  * Text pops up: `"Sending source code to external APIs breaks compliance."`
  * Text splits into two branches:
    * **Path A**: Naive text slicing cuts code in the middle of a function ➔ AI Hallucination icon (❌).
    * **Path B**: Sending full repository files ➔ Token budget exploding counter: `$1,200 / day` ➔ Context Window Overflow warning (⚠️).
* **Voiceover**:
  > *"Developers love AI coding tools. But enterprise engineering teams face a dilemma: sending full codebases to cloud APIs violates compliance, while naive search causes AI models to hallucinate or explode your token budget."*

---

### Scene 2: Introducing M5 v2 (0:15 – 0:40)

* **Visuals (2D Animation)**:
  * Smooth transition to a cyan/violet glowing architecture node labeled **`M5 v2 Context Engine`**.
  * A perimeter box forms around the company servers labeled `"Air-Gapped / Inside Your Perimeter"`.
  * An animated packet travels:
    `VS Code / Copilot` ──► `M5 MCP Layer` ──► `Local AST & Vector Index`.
  * Glowing checkmarks appear:
    * ✅ **100% Context Only** (M5 never sends code outside).
    * ✅ **Works with Existing Tools** (GitHub Copilot, Claude Code, Cursor, ChatGPT).
    * ✅ **Exact Line Range Provenance** (Line 42–85 cited).
* **Voiceover**:
  > *"Meet M5. M5 is an invisible, permission-aware code context layer that plugs directly into the AI tools your developers already use. M5 doesn't replace your AI — it feeds it exact, mathematically ranked context."*

---

### Scene 3: Under the Hood (0:40 – 1:00)

* **Visuals (2D Animation)**:
  * **AST Parsing Visual**: A Python script is parsed into clean AST method & class blocks (highlighted in glowing green boxes) instead of arbitrary character cuts.
  * **Hybrid RRF Search Engine**: Two search streams merge:
    * *Sparse BM25 Keyword Search* + *Dense ONNX Vector Search* ➔ Combined via **Reciprocal Rank Fusion (RRF)**.
  * **Webhook Sync Animation**: A `git push` event sends a pulse through a GitHub Webhook icon ➔ M5 updates the vector and symbol graph in **< 200ms**.
* **Voiceover**:
  > *"Under the hood, M5 parses AST symbol boundaries, builds SQLite and Postgres dependency graphs, and merges BM25 keyword search with dense vectors via Reciprocal Rank Fusion. And when engineers push code, M5's event-driven webhook sync updates the index in under 200 milliseconds."*

---

### Scene 4: Live Product Demo (1:00 – 1:45)

* **Visuals (Screen Recording / Live Video)**:
  * **01:00**: Terminal screen showing `docker compose up -d`. Clean ANSI colored logs spin up (`[m5.server] Online on port 8000`).
  * **01:15**: Switch to **VS Code Copilot Chat**.
  * Developer types: *"Where is the HTTP session adapter handling defined in requests?"*
  * Copilot calls the MCP tool `m5_get_context`.
  * **01:30**: M5 terminal logs show instant response (`POST /mcp -> status=200 elapsed=24ms`).
  * Copilot renders the answer with exact file links and line range citations (`requests/adapters.py#L42-L88`).
  * **01:40**: Quick cut to the M5 Compliance Audit Log (`GET /api/audit/query`), demonstrating immutable request provenance logging.
* **Voiceover**:
  > *"Let's see it in action. Here, VS Code Copilot queries M5 via standard Remote MCP. M5 resolves AST blocks, expands file dependencies, and returns cited context in 24 milliseconds. Complete accuracy, zero token waste, and full audit provenance."*

---

### Scene 5: Outro & Call to Action (1:45 – 2:00)

* **Visuals (2D Motion Graphics)**:
  * Sleek logo resolve of **M5 v2 Context Engine**.
  * Tagline in bold glowing typography:
    `"M5 supplies the context. Your AI produces the answer."`
  * Text overlays:
    * 📦 Deploy on Kubernetes (AKS / EKS / GKE)
    * 🔌 Native Remote HTTP MCP & REST Transport
    * 🛡️ Compliance-Grade Audit Provenance
* **Voiceover**:
  > *"Bring compliance-grade code intelligence to your enterprise today. M5 v2: M5 supplies the context; your AI produces the answer. Get started now."*

---

## Recommended Video Production Tools

| Component | Recommended Tool | Alternative |
| :--- | :--- | :--- |
| **2D Motion Graphics** | **Remotion** (React code-to-video) / **After Effects** | Figma + Motion Plugin / Canva |
| **Terminal / Code Demo** | **Screen Studio** (macOS) / **OBS Studio** | Camtasia |
| **Voiceover AI** | **ElevenLabs** (Adam or Rachel voice model) | Play.ht / Human Voiceover |
| **Background Music** | High-energy Synthwave / Tech Ambient (e.g. Epidemic Sound / Artlist) | Lofi Cyberpunk track |

---

## 🏷️ High-Impact Catchy Taglines & Slogans

### 💰 Cost & Token Efficiency
* **"Don't feed your LLM the haystack. Just give it the needle."**
* **"Cut token bills by 85%. Increase AI precision by 100%."**
* **"Stop paying LLMs to read irrelevant code."**
* **"Maximum context efficiency. Minimal token spend."**

### 🧠 Intelligence & Accuracy
* **"Turn LLM hallucinations into line-by-line proof."**
* **"Zero guesswork. Zero hallucinations. Exact line citations."**
* **"M5 supplies the context. Your AI produces the truth."**
* **"Give your AI agents AST-level precision."**

### 🛡️ Enterprise Compliance & Air-Gapped Security
* **"Your Code. Your Data. Your Control."**
* **"Zero code leaves your perimeter. 100% intelligence enters your IDE."**
* **"The invisible context layer for regulated codebases."**
* **"Index once in CI/CD. Serve 10,000 developers in milliseconds."**

### ⚡ Short Punchy Trailer Headlines (3-5 Words)
* **"Less Tokens. Zero Hallucinations. Pure Context."**
* **"Smart Context. Zero Leakage."**
* **"The Missing Brain Behind Copilot & Claude."**

