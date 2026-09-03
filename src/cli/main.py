"""
main.py — Unified Global CLI Entrypoint for M5 Context Engine.
Powers the 'm5' command when installed via pip (`pip install m5-context`).

Commands:
  m5 setup            Interactive manual setup guide with copy-pasteable MCP configs
  m5 build            Scan and index the workspace into local SQLite AST graph (<1s)
  m5 purge            Remove local .m5/ index from workspace
  m5 scan             Force a full re-index of the workspace
  m5 live             Start real-time incremental file watcher (<50ms on save)
  m5 stats            Display AST symbols, call edges, and DB size statistics
  m5 trace <query>    1-shot surgical context: verbatim code + call flow + blast radius
  m5 peek <sym|file>  View symbol implementation & callers or line-numbered file
  m5 find <query>     Search AST symbols by name or type
  m5 callers <sym>    Find all functions/files calling a symbol
  m5 callees <sym>    Find all dependencies/symbols called by a function
  m5 blast <sym>      Multi-hop blast radius & affected files analysis
  m5 diff-tests       Find test files affected by changed source files
  m5 serve            Run MCP server in stdio mode for AI agents
  m5 view             Open local browser graph visualizer (http://127.0.0.1:5555)
  m5 pull [url]       Sync pre-computed team index from CI cache
  m5 dump             Export index bundle for team or CI upload
"""

import sys
import os
import json
import shutil
from pathlib import Path
from typing import List, cast

# Ensure safe UTF-8 output across Windows, Linux, and macOS shells
if hasattr(sys.stdout, "reconfigure"):
    try:
        getattr(sys.stdout, "reconfigure")(encoding="utf-8", errors="replace")
        getattr(sys.stderr, "reconfigure")(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from importlib.metadata import version as _get_version
    VERSION = _get_version("m5-engine")
except Exception:
    try:
        from importlib.metadata import version as _get_version
        VERSION = _get_version("m5-engine")
    except Exception:
        VERSION = "1.1.1"

def print_help():
    print(f"""
========================================================================
   M5 CONTEXT ENGINE — AST Code Intelligence CLI (v{VERSION})
========================================================================

Usage: m5 <command> [arguments] [options]

Core Setup & Lifecycle:
  setup / connect     Interactive manual setup guide with exact MCP configs for your IDE
  rules / instruct    Inject agent navigation rules into AGENTS.md, CLAUDE.md, .cursorrules
  build / init        Scan and build local SQLite AST graph in <1s (into .m5/)
  purge / uninit      Remove .m5/ index from current project
  scan / reindex      Force full workspace re-index
  live / watch        Start real-time file watcher (<50ms incremental sync on save)
  stats / status      Display graph statistics (total files, symbols, edges, db size)

Surgical Code Intelligence:
  trace <query>       1-shot deep context: verbatim code + call flow + blast radius
  peek <sym|file>     Inspect symbol source & callers, or view line-numbered file
  find <pattern>      Search AST symbols by name, type, or query (--kind, --limit)
  callers <sym>       Find all functions and files calling a symbol
  callees <sym>       Find all dependencies and symbols called by a function
  blast <sym>         Multi-hop blast radius & affected files analysis (--depth)
  diff-tests [files]  Find test files affected by changes (supports --stdin from git diff)

Agent Integration & Visual Browser:
  serve / stdio       Launch Model Context Protocol (MCP) server over stdio
  view / ui           Launch local browser visualizer web app (http://127.0.0.1:5555)
  pull [url]          Pull pre-computed index bundle from CI cache
  dump / export       Export index bundle for team sharing or CI artifact
  version             Print installed M5 version
  help                Show this help guide
""")

def cli_entrypoint():
    args = sys.argv[1:]
    if not args:
        # Launch setup guide if no arguments provided
        from src.cli.setup_guide import run_setup_wizard
        run_setup_wizard()
        return

    cmd = args[0].lower()

    if cmd in ["help", "--help", "-h"]:
        print_help()
        return

    if cmd in ["version", "-v", "--version"]:
        print(f"M5 Context Engine v{VERSION}")
        return

    # ── Setup & Connection Guide ──────────────────────────────────────────────
    if cmd in ["setup", "connect", "install"]:
        from src.cli.setup_guide import run_setup_wizard
        target = args[1] if len(args) > 1 and not args[1].startswith("-") else None
        run_setup_wizard(target=target)

    # ── Agent Rules & Directives Injection ───────────────────────────────────
    elif cmd in ["rules", "instruct", "prompt"]:
        from src.cli.setup_guide import inject_agent_rules
        target_dir = args[1] if len(args) > 1 and not args[1].startswith("-") else "."
        inject_agent_rules(target_dir=target_dir)

    # ── Build / Init Graph ───────────────────────────────────────────────────
    elif cmd in ["build", "init", "scan", "reindex"]:
        from src.indexer.file_watcher import LocalFileWatcher
        from src.storage.local_db import LocalCodeGraphDB
        target_dir = args[1] if len(args) > 1 and not args[1].startswith("-") else "."
        print(f"[+] Scanning and indexing '{target_dir}' with Tree-sitter AST...")
        watcher = LocalFileWatcher(target_dir)
        count = watcher.initial_scan()
        db = LocalCodeGraphDB()
        stats = db.get_stats()
        print(f"\n[SUCCESS] M5 indexed {count} files in milliseconds!")
        print(f"  - AST Symbols:   {stats.get('total_symbols', 0)}")
        print(f"  - Call Edges:    {stats.get('total_edges', 0)}")
        print(f"  - SQLite DB:     {stats.get('db_size_kb', 0)} KB ({db.db_path})\n")

        # Auto-inject agent navigation rules so AI agents use M5 automatically
        from src.cli.setup_guide import inject_agent_rules
        inject_agent_rules(target_dir=target_dir)

    # ── Purge / Uninit ───────────────────────────────────────────────────────
    elif cmd in ["purge", "uninit"]:
        target_dir = args[1] if len(args) > 1 and not args[1].startswith("-") else "."
        dot_m5 = Path(target_dir) / ".m5"
        if dot_m5.exists():
            shutil.rmtree(dot_m5)
            print(f"[SUCCESS] Cleanly removed M5 index from {dot_m5.resolve()}")
        else:
            print(f"[-] No .m5/ directory found in {Path(target_dir).resolve()}")

    # ── Complete System Uninstall Guide ──────────────────────────────────────
    elif cmd in ["uninstall", "remove", "clean-all"]:
        print("\n========================================================================")
        print("   M5 CONTEXT ENGINE — Complete System Removal")
        print("========================================================================")
        
        # Step 1: Clean local workspace index
        dot_m5 = Path(".") / ".m5"
        if dot_m5.exists():
            shutil.rmtree(dot_m5)
            print(f"[+] Removed local workspace index: {dot_m5.resolve()}")
        else:
            print("[+] No local .m5/ directory in current folder.")

        # Step 2: Print package uninstall command
        print("\n[Step 1] To completely remove the M5 package and CLI from your system:")
        print("  pip uninstall -y m5-engine")
        print("  # or if installed with pipx:")
        print("  pipx uninstall m5-engine")

        # Step 3: MCP config cleanup reminders
        print("\n[Step 2] (Optional) Remove the 'm5' server entry from your IDE configs:")
        print("  - Cursor:     .cursor/mcp.json or ~/.cursor/mcp.json")
        print("  - VS Code:    .vscode/mcp.json")
        print("  - Antigravity: .agents/mcp_config.json or ~/.gemini/config/mcp_config.json")
        print("  - Claude:     ~/.claude.json or claude_desktop_config.json")
        print("========================================================================\n")

    # ── Live Watcher ─────────────────────────────────────────────────────────
    elif cmd in ["live", "watch"]:
        from src.indexer.file_watcher import LocalFileWatcher
        target_dir = args[1] if len(args) > 1 and not args[1].startswith("-") else "."
        watcher = LocalFileWatcher(target_dir)
        watcher.start()
        print(f"\n=======================================================")
        print(f"  [M5] Real-Time File Watcher Active for '{Path(target_dir).resolve()}'")
        print(f"  Saving any source file updates the AST graph (<50ms).")
        print(f"  Press Ctrl+C to exit.")
        print(f"=======================================================\n")
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            watcher.stop()
            print("\n[+] Watcher stopped.")

    # ── Stats / Status ───────────────────────────────────────────────────────
    elif cmd in ["stats", "status"]:
        from src.storage.local_db import LocalCodeGraphDB
        db = LocalCodeGraphDB()
        stats = db.get_stats()
        print(f"\n[M5 Local AST Knowledge Graph Status]")
        print(f"  - Database Path:     {db.db_path}")
        print(f"  - Total Files:       {stats.get('total_files', 0)}")
        print(f"  - Total AST Symbols: {stats.get('total_symbols', 0)}")
        print(f"  - Total Call Edges:  {stats.get('total_edges', 0)}")
        print(f"  - Database Size:     {stats.get('db_size_kb', 0)} KB\n")

    # ── Trace (1-Shot Surgical GraphRAG Context) ─────────────────────────────
    elif cmd in ["trace", "explore", "context"]:
        if len(args) < 2:
            print("[!] Usage: m5 trace \"<query or symbol name>\"")
            return
        query = " ".join(args[1:])
        from src.context.context_engine import get_context

        print(f"\n=======================================================")
        print(f"  [M5 GraphRAG Context Trace] Query: \"{query}\"")
        print(f"=======================================================\n")

        bundle = get_context(query=query, top_k=6, expand_dependencies=True)
        chunks = bundle.get("chunks", [])

        if not chunks:
            print("[-] No matching code or AST symbols found. Run 'm5 build' to index your workspace.")
            return

        for idx, c in enumerate(chunks, 1):
            name = str(c.get("symbol_name", "anonymous"))
            fpath = str(c.get("file_path", ""))
            s_line = c.get("start_line", 1)
            e_line = c.get("end_line", 1)
            kind = str(c.get("symbol_type", "symbol")).upper()
            concern = str(c.get("concern", "general")).upper()
            match_type = str(c.get("match_type", "match")).upper()
            confidence = str(c.get("confidence", "high")).upper()
            content = str(c.get("content", ""))
            callers = c.get("callers", [])
            callees = c.get("callees", [])

            print(f"[{idx}] [{concern}] {kind}: {name} ({fpath}:{s_line}-{e_line})")
            print(f"    ⭐ Relevance: {c.get('relevance_score', 0.0)} | Type: {match_type} ({confidence})")
            if callers:
                print(f"    ◀ Callers: {', '.join(callers[:4])}")
            if callees:
                print(f"    ▶ Calls:   {', '.join(callees[:4])}")
            print("    ───────────────────────────────────────────────────")
            lines = content.splitlines()
            print("    " + "\n    ".join(lines[:25]))
            if len(lines) > 25:
                print(f"    ... ({len(lines) - 25} more lines)")
            print("\n")

        dep_edges = bundle.get("dependency_edges", [])
        if dep_edges:
            print("🔗 Connected Architecture Edges:")
            for e in dep_edges[:6]:
                src = os.path.basename(e.get("source", ""))
                tgt = os.path.basename(e.get("target", ""))
                rel = e.get("semantic_relationship") or e.get("relationship", "relates_to")
                print(f"  • {src} ──[{rel}]──▶ {tgt}")
            print()

        tests = bundle.get("related_tests", [])
        if tests:
            print(f"🧪 Companion Tests ({len(tests)}): {', '.join([os.path.basename(t) for t in tests[:5]])}\n")


    # ── Peek / Inspect ───────────────────────────────────────────────────────
    elif cmd in ["peek", "inspect", "node"]:
        if len(args) < 2:
            print("[!] Usage: m5 peek <symbol_name | file_path>")
            return
        target = args[1]
        from src.storage.local_db import LocalCodeGraphDB
        db = LocalCodeGraphDB()

        # Check if it's a file path
        if os.path.isfile(target):
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            print(f"\n[File: {target}] ({len(lines)} lines)")
            for i, line in enumerate(lines, 1):
                print(f"{i:4d} | {line.rstrip()}")
            print()
            return

        # Otherwise look up symbol
        matches = db.find_symbol(target, exact=False, limit=5)
        if not matches:
            print(f"[-] No symbol found matching '{target}'.")
            return

        for sym in matches:
            callers = db.find_callers(sym["name"], limit=10)
            print(f"\n[Symbol: {sym['name']}] ({sym['kind']})")
            print(f"Location: {sym['file_path']} : Lines {sym['start_line']}-{sym['end_line']}")
            if callers:
                print(f"Callers ({len(callers)}):")
                for c in callers:
                    print(f"  - {c['source_symbol']} in {c['source_file']}")
            print("\n--- Source Code ---")
            for idx, line in enumerate(sym["content"].splitlines(), sym["start_line"]):
                print(f"{idx:4d} | {line}")
            print()

    # ── Find / Lookup ────────────────────────────────────────────────────────
    elif cmd in ["find", "lookup", "query", "search"]:
        if len(args) < 2:
            print("[!] Usage: m5 find <pattern>")
            return
        query = args[1]
        from src.storage.local_db import LocalCodeGraphDB
        db = LocalCodeGraphDB()
        results = db.search_fts(query, limit=20)
        if not results:
            results = db.find_symbol(query, exact=False, limit=20)

        print(f"\n[M5 Symbol Search Results for '{query}'] ({len(results)} matches)")
        print(f"{'SYMBOL':<30} {'KIND':<12} {'FILE & LINE'}")
        print("-" * 75)
        for r in results:
            loc = f"{r.get('file_path', '')}:{r.get('start_line', 1)}"
            print(f"{r.get('name', '')[:28]:<30} {r.get('kind', 'symbol')[:10]:<12} {loc}")
        print()

    # ── Callers ──────────────────────────────────────────────────────────────
    elif cmd in ["callers"]:
        if len(args) < 2:
            print("[!] Usage: m5 callers <symbol_name>")
            return
        sym_name = args[1]
        from src.storage.local_db import LocalCodeGraphDB
        db = LocalCodeGraphDB()
        callers = db.find_callers(sym_name, limit=30)
        print(f"\n[Callers of '{sym_name}'] ({len(callers)} found)")
        if not callers:
            print("  No callers found in the current AST graph.")
        for c in callers:
            print(f"  - {c['source_symbol']}  -->  {c['source_file']}")
        print()

    # ── Callees ──────────────────────────────────────────────────────────────
    elif cmd in ["callees"]:
        if len(args) < 2:
            print("[!] Usage: m5 callees <symbol_name>")
            return
        sym_name = args[1]
        from src.storage.local_db import LocalCodeGraphDB
        db = LocalCodeGraphDB()
        syms = db.find_symbol(sym_name, exact=True, limit=1)
        if not syms:
            print(f"[-] Symbol '{sym_name}' not found.")
            return
        sym = syms[0]
        callees = db.find_callees(sym["file_path"], sym["name"])
        print(f"\n[Callees of '{sym_name}'] ({len(callees)} found)")
        if not callees:
            print("  No outgoing function calls found.")
        for c in callees:
            target_file = f" ({c['target_file']})" if c.get("target_file") else ""
            print(f"  - {c['target_symbol']}{target_file}")
        print()

    # ── Blast / Radius (Impact Analysis) ─────────────────────────────────────
    elif cmd in ["blast", "radius", "impact"]:
        if len(args) < 2:
            print("[!] Usage: m5 blast <symbol_name> [--depth N]")
            return
        sym_name = args[1]
        depth = 2
        if "--depth" in args:
            try:
                depth = int(args[args.index("--depth") + 1])
            except Exception:
                depth = 2

        from src.storage.local_db import LocalCodeGraphDB
        db = LocalCodeGraphDB()
        blast = db.get_impact_radius(sym_name, depth=depth)
        print(f"\n[Blast Radius for '{sym_name}'] (Depth: {depth})")
        print(f"  - Total Affected Symbols: {blast['total_affected_symbols']}")
        print(f"  - Total Affected Files:   {blast['total_affected_files']}")
        if blast["affected_files"]:
            print("\n  Affected Files:")
            for f in blast["affected_files"]:
                print(f"    📄 {f}")
        print()

    # ── Diff Tests (Affected Tests) ──────────────────────────────────────────
    elif cmd in ["diff-tests", "affected", "changed"]:
        changed_files = []
        if "--stdin" in args:
            for line in sys.stdin:
                f = line.strip()
                if f:
                    changed_files.append(f)
        else:
            changed_files = [a for a in args[1:] if not a.startswith("-")]

        from src.storage.local_db import LocalCodeGraphDB
        db = LocalCodeGraphDB()
        affected = db.get_affected_tests(changed_files)
        print(f"\n[Affected Tests for {len(changed_files)} Changed Files]")
        if not affected:
            print("  No dependent test files detected.")
        else:
            for t in affected:
                print(f"  🧪 {t}")
        print()

    # ── Visual UI Browser ────────────────────────────────────────────────────
    elif cmd in ["view", "visual", "ui", "web"]:
        from src.cli.visual_server import start_visual_server
        port = 5555
        if "--port" in args:
            try:
                port = int(args[args.index("--port") + 1])
            except Exception:
                port = 5555
        no_open = "--no-open" in args
        start_visual_server(port=port, open_browser=not no_open)

    # ── MCP Server ───────────────────────────────────────────────────────────
    elif cmd in ["serve", "stdio"]:
        from src.mcp_server import run_stdio
        os.environ["M5_LOCAL_MODE"] = "true"
        run_stdio()

    # ── CI Team Index Pull / Dump ────────────────────────────────────────────
    elif cmd in ["pull", "sync"]:
        from src.cli.sync import run_sync
        run_sync()

    elif cmd in ["dump", "export"]:
        from src.cli.sync import export_index_bundle
        export_index_bundle()

    else:
        print(f"[!] Unknown command '{cmd}'. Run 'm5 help' for available commands.")

if __name__ == "__main__":
    cli_entrypoint()
