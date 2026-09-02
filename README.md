# M5 — AST Code Knowledge Graph for AI Coding Agents

When AI agents work on your codebase, they spend most of their time (and your tokens) doing clumsy discovery: grepping files one by one, wandering through directory listings, and trying to reconstruct call hierarchies in their head.

**M5 fixes that.** It parses your codebase with Tree-sitter into an embedded, zero-overhead SQLite knowledge graph (`.m5/local_graph.db`). When your agent asks a question, M5 returns the exact code, upstream callers, downstream dependencies, and blast radius in **one single call**.

- **100% Local**: No Docker, no heavy background daemons, no cloud dependency.
- **Sub-50ms Incremental Sync**: Watches your files and updates only what changed when you save.
- **Zero-Friction MCP Integration**: Works with Claude Code, Cursor, VS Code / Copilot, Gemini CLI, Antigravity, and Codex.
- **Interactive Browser UI**: Visualize your architecture and dependency chains at `http://127.0.0.1:5555`.

---

## 🚀 Quickstart

### 1. Install M5
Install globally using `pip` or `pipx`:

```bash
pip install m5-engine
# or with pipx:
pipx install m5-engine
```

### 2. Connect Your AI Agent
Run the interactive setup wizard to get clean, copy-pasteable MCP config snippets for your editor:

```bash
m5 setup
```
*(Or specify your tool directly: `m5 setup claude`, `m5 setup cursor`, `m5 setup vscode`)*

Paste the provided JSON block into your editor's MCP configuration. We don't silently rewrite your system files behind your back — you stay in full control.

### 3. Build Your Project Index
Navigate to any project repository and build the graph:

```bash
cd your-project
m5 build
```

This scans your workspace and indexes all AST symbols and call edges into `.m5/local_graph.db` in under a second.

### 4. Keep It Fresh While You Code
Start the background watcher:

```bash
m5 live
```

Whenever you or your AI agent edits a file, M5 catches the change and updates the graph in $<50\text{ms}$.

---

## 🔍 CLI Commands

| Command | What it does | Example |
|---|---|---|
| `m5 setup` | Interactive manual setup wizard with exact MCP configs for your IDE | `m5 setup` or `m5 setup cursor` |
| `m5 build` | Scans workspace and builds AST knowledge graph into `.m5/` | `m5 build` |
| `m5 live` | Starts real-time file watcher (<50ms incremental sync on save) | `m5 live` |
| `m5 stats` | Shows index summary (files, AST symbols, call edges, DB size) | `m5 stats` |
| `m5 trace` | 1-shot surgical context: verbatim code + call flow + blast radius | `m5 trace "auth middleware token validation"` |
| `m5 peek` | View symbol definition & callers, or view line-numbered file | `m5 peek UserService` or `m5 peek src/auth.py` |
| `m5 find` | Search AST symbols by name, type, or pattern (FTS5 + B-tree) | `m5 find parse_jwt` |
| `m5 callers` | Find all functions and files calling a symbol | `m5 callers handle_request` |
| `m5 callees` | Find all functions called by a symbol | `m5 callees handle_request` |
| `m5 blast` | Multi-hop blast radius & affected files analysis before refactoring | `m5 blast DatabasePool --depth 2` |
| `m5 diff-tests` | Find test suites affected by modified files | `git diff --name-only \| m5 diff-tests --stdin` |
| `m5 view` | Open local browser visualizer at `http://127.0.0.1:5555` | `m5 view` |
| `m5 serve` | Start the MCP server over stdio (invoked by IDEs) | `m5 serve` |
| `m5 purge` | Cleanly remove `.m5/` index from project | `m5 purge` |
| `m5 scan` | Force full re-index of the repository | `m5 scan` |
| `m5 dump` | Export index bundle for CI / team sharing | `m5 dump` |
| `m5 pull` | Pull pre-computed team index from CI cache | `m5 pull https://ci.company.com/index.tar.gz` |

---

## 🖥️ Visual Graph Browser (`m5 view`)

Want to see what your AI agent sees? Run:

```bash
m5 view
```

Opens a fast, dark-mode browser interface at `http://127.0.0.1:5555`:
- **Search & Filter**: Find any function, method, or class across your repo with instant fuzzy search.
- **Live Code Inspection**: Read exact symbol bodies with line numbers and AST metadata.
- **Dependency Panels**: See direct callers, outgoing calls, and affected files on the side.
- **Zero External Server**: Powered by Python's built-in HTTP server, so it starts instantly without npm or heavy node packages.

---

## 🤖 Agent Instructions (CLAUDE.md / AGENTS.md / GEMINI.md)

To help subagents and command-line agents make the most of M5, paste this snippet into your project's `CLAUDE.md`, `AGENTS.md`, or `GEMINI.md`:

```markdown
<!-- M5 CONTEXT ENGINE START -->
## M5 Code Context & AST Knowledge Graph
This project uses M5 for instant AST code intelligence and dependency navigation.
Instead of repeatedly reading entire files or running multiple grep commands:
- Run `m5 trace "<query>"` to retrieve relevant symbol definitions, call hierarchies, and blast radius in 1 step.
- Run `m5 peek <symbol>` to view the exact implementation and callers of any function or class.
- Run `m5 callers <symbol>` or `m5 callees <symbol>` to navigate the call graph.
- Run `m5 diff-tests` to see tests affected by modified files.
<!-- M5 CONTEXT ENGINE END -->
```

---

## 🌐 Supported Languages

M5 extracts full AST symbol trees and resolves cross-file call edges across:

- **Web & Backend**: Python, TypeScript, JavaScript, Go, Rust, Java, C++, C, C#, Ruby, PHP
- **Mobile & Modern**: Swift, Kotlin, Dart, Scala

---

## 📄 License

MIT License. Free and open source for developers and teams.
