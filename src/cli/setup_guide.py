"""
setup_guide.py — Dynamic Setup & Configuration Wizard for M5.
Provides transparent, copy-pasteable MCP configuration snippets and setup instructions
for all major AI coding agents, IDEs, and CLIs without hardcoded paths or silent background edits.
"""

import os
import sys
import json
import shutil
import platform
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List


def resolve_m5_command() -> Tuple[str, List[str], Dict[str, str]]:
    """
    Dynamically discovers the best command, args, and environment to launch the M5 MCP server.
    - If `m5` or `m5.exe` is installed on PATH or in Python's Scripts/bin, uses direct executable.
    - If running directly from git source repo without pip install, uses python module execution with PYTHONPATH.
    """
    # 1. Check if `m5` executable is in system PATH
    which_m5 = shutil.which("m5") or shutil.which("m5.exe")
    if which_m5:
        return (str(Path(which_m5).resolve()), ["serve"], {"M5_LOCAL_MODE": "true"})

    # 2. Check active Python environment's Scripts or bin directories
    py_parent = Path(sys.executable).parent
    candidate_paths = [
        py_parent / "Scripts" / "m5.exe",
        py_parent / "Scripts" / "m5",
        py_parent / "bin" / "m5",
        py_parent / "m5.exe",
        py_parent / "m5",
    ]
    for cand in candidate_paths:
        if cand.exists():
            return (str(cand.resolve()), ["serve"], {"M5_LOCAL_MODE": "true"})

    # 3. Fallback: Source repo execution with dynamic PYTHONPATH
    m5_root = str(Path(os.getcwd()).resolve())
    return (
        sys.executable,
        ["-m", "src.cli.main", "serve"],
        {"M5_LOCAL_MODE": "true", "PYTHONPATH": m5_root},
    )


def get_configs_dict() -> Dict[str, Dict[str, Any]]:
    system = platform.system()
    cmd, args, env = resolve_m5_command()

    # Standard MCP server definition
    base_server_spec: Dict[str, Any] = {
        "command": cmd,
        "args": args,
    }
    if env:
        base_server_spec["env"] = env

    # VS Code standard format (includes "type": "stdio")
    vscode_server_spec: Dict[str, Any] = {
        "type": "stdio",
        "command": cmd,
        "args": args,
    }
    if env:
        vscode_server_spec["env"] = env

    # 1. Antigravity IDE / Gemini CLI paths
    if system == "Windows":
        gemini_global_path = str(Path(os.getenv("USERPROFILE", str(Path.home()))) / ".gemini" / "config" / "mcp_config.json")
    else:
        gemini_global_path = str(Path.home() / ".gemini" / "config" / "mcp_config.json")
    gemini_workspace_path = ".agents/mcp_config.json"

    # 2. Claude Desktop path
    if system == "Windows":
        claude_desktop_path = str(Path(os.getenv("APPDATA", "")) / "Claude" / "claude_desktop_config.json")
    elif system == "Darwin":
        claude_desktop_path = str(Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json")
    else:
        claude_desktop_path = str(Path.home() / ".config" / "Claude" / "claude_desktop_config.json")

    # 3. Claude Code CLI path
    claude_code_path = str(Path.home() / ".claude.json")
    claude_permissions = {
        "permissions": {
            "allow": ["mcp__m5__*"]
        }
    }

    # 4. Cursor IDE paths
    cursor_global_path = str(Path.home() / ".cursor" / "mcp.json")
    cursor_workspace_path = ".cursor/mcp.json"

    # 5. VS Code path
    vscode_path = ".vscode/mcp.json"

    # 6. Windsurf (Codeium) path
    windsurf_path = str(Path.home() / ".codeium" / "windsurf" / "mcp_config.json")

    # 7. Codex CLI path
    codex_path = str(Path.home() / ".codex" / "config.json")

    return {
        "1": {
            "name": "Cursor IDE",
            "target_file": f"{cursor_workspace_path} (Workspace) or {cursor_global_path} (Global)",
            "config": {
                "mcpServers": {
                    "m5": base_server_spec
                }
            },
            "where_to_paste": (
                "Option A (Project level): Create `.cursor/mcp.json` in your workspace root and paste the snippet.\n"
                "Option B (Global level): Go to Cursor Settings -> Features -> MCP -> Add New MCP Server,\n"
                f"or edit: {cursor_global_path}"
            )
        },
        "2": {
            "name": "Antigravity IDE / Gemini CLI",
            "target_file": f"{gemini_workspace_path} (Workspace) or {gemini_global_path} (Global)",
            "config": {
                "mcpServers": {
                    "m5": base_server_spec
                }
            },
            "where_to_paste": (
                "Option A (Workspace level): Create `.agents/mcp_config.json` in your project root and paste the snippet.\n"
                f"Option B (Global level): Edit your global configuration at:\n  {gemini_global_path}\n"
                "(Note: Antigravity infers stdio transport implicitly; 'type' field is omitted)."
            )
        },
        "3": {
            "name": "VS Code / GitHub Copilot",
            "target_file": vscode_path,
            "config": {
                "servers": {
                    "m5": vscode_server_spec
                }
            },
            "where_to_paste": (
                "Create `.vscode/mcp.json` in your project root and paste the JSON block.\n"
                "VS Code will automatically detect and start the M5 MCP server."
            )
        },
        "4": {
            "name": "Claude Desktop",
            "target_file": claude_desktop_path,
            "config": {
                "mcpServers": {
                    "m5": base_server_spec
                }
            },
            "where_to_paste": (
                f"1. Open Claude Desktop.\n"
                f"2. Go to Settings -> Developer -> Edit Config.\n"
                f"3. Paste the snippet into: {claude_desktop_path}\n"
                f"4. Restart Claude Desktop."
            )
        },
        "5": {
            "name": "Claude Code CLI",
            "target_file": claude_code_path,
            "config": {
                "mcpServers": {
                    "m5": base_server_spec
                }
            },
            "where_to_paste": (
                f"1. Paste the snippet into: {claude_code_path}\n"
                f"2. (Optional) To auto-approve M5 tool calls without prompts, add to ~/.claude/settings.json:\n"
                f"{json.dumps(claude_permissions, indent=2)}"
            )
        },
        "6": {
            "name": "Windsurf IDE (Codeium)",
            "target_file": windsurf_path,
            "config": {
                "mcpServers": {
                    "m5": base_server_spec
                }
            },
            "where_to_paste": (
                f"1. Open Windsurf Settings -> Cascade -> MCP Servers, or edit: {windsurf_path}\n"
                "2. Paste the JSON block and restart Cascade."
            )
        },
        "7": {
            "name": "Codex CLI & opencode",
            "target_file": codex_path,
            "config": {
                "mcpServers": {
                    "m5": base_server_spec
                }
            },
            "where_to_paste": (
                f"Add the snippet to {codex_path} or `.mcp.json` in your workspace root."
            )
        }
    }


AGENT_INSTRUCTION_MARKER = """<!-- M5 CONTEXT ENGINE START -->
# M5 Code Intelligence & AST Context Rules (MANDATORY)

This project is indexed by the **M5 Context Engine** (`.m5/local_graph.db`).
When analyzing, refactoring, or navigating code in this repository:

1. **NEVER run blind grep / ripgrep** or read entire files into context to understand call flows.
2. **ALWAYS use M5 tools FIRST**:
   - **Via MCP**:
     - `m5_get_context`: Call this FIRST for deep context (exact symbol bodies, upstream callers, downstream dependencies, and token estimates in 1 step).
     - `m5_search_code`: High-speed AST symbol & semantic code search instead of grep.
     - `m5_get_dependents` / `m5_get_dependencies`: Check blast radius before modifying any function, class, or module.
     - `m5_find_symbol_references`: Exact AST symbol definitions and usages without false positives.
     - `m5_read_lines`: Stream precise line ranges with context padding instead of reading whole files.
     - `m5_get_test_impact`: Find test files impacted by changes.
   - **Via Terminal / CLI** (if MCP is unavailable):
     - `m5 trace "<query>"`: 1-shot deep context + call graph.
     - `m5 peek <symbol>`: View function body & callers.
     - `m5 callers <sym>` / `m5 callees <sym>`: Explore the call graph.
     - `m5 blast <sym> --depth 2`: Check blast radius.
     - `m5 diff-tests`: Tests affected by git changes.
<!-- M5 CONTEXT ENGINE END -->"""


def inject_agent_rules(target_dir: str = ".", quiet: bool = False) -> List[str]:
    """
    Injects or updates the M5 agent navigation rules in repository instruction files:
    - AGENTS.md (Universal: Antigravity, Copilot, Gemini CLI, Claude)
    - CLAUDE.md (Claude Code CLI)
    - .cursorrules / .cursor/rules/m5.mdc (Cursor IDE)
    - GEMINI.md

    Preserves all existing user instructions and only replaces or adds the M5 block.
    """
    root = Path(target_dir).resolve()
    target_files = [
        root / "AGENTS.md",
        root / "CLAUDE.md",
        root / ".cursorrules",
        root / "GEMINI.md",
    ]

    # Check which instruction files already exist
    existing_files = [f for f in target_files if f.exists()]

    # If none exist, create AGENTS.md by default (universal standard)
    if not existing_files:
        existing_files = [root / "AGENTS.md"]

    updated = []
    start_tag = "<!-- M5 CONTEXT ENGINE START -->"
    end_tag = "<!-- M5 CONTEXT ENGINE END -->"

    for file_path in existing_files:
        try:
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8", errors="replace")
                if start_tag in content and end_tag in content:
                    # Replace existing M5 section cleanly
                    pre = content.split(start_tag)[0]
                    post = content.split(end_tag)[1]
                    new_content = f"{pre.rstrip()}\n\n{AGENT_INSTRUCTION_MARKER}\n{post.lstrip()}"
                else:
                    # Append M5 section cleanly
                    new_content = f"{content.rstrip()}\n\n{AGENT_INSTRUCTION_MARKER}\n"
            else:
                new_content = f"{AGENT_INSTRUCTION_MARKER}\n"

            file_path.write_text(new_content, encoding="utf-8")
            updated.append(file_path.name)
        except Exception as e:
            if not quiet:
                print(f"[!] Could not update {file_path.name}: {e}")

    # Also support Cursor's modern .cursor/rules/ directory if .cursor exists
    cursor_dir = root / ".cursor" / "rules"
    if (root / ".cursor").exists():
        try:
            cursor_dir.mkdir(parents=True, exist_ok=True)
            cursor_rule_file = cursor_dir / "m5.mdc"
            cursor_rule_file.write_text(
                "---\ndescription: M5 AST Code Intelligence Rules\nglobs: *\n---\n\n" + AGENT_INSTRUCTION_MARKER + "\n",
                encoding="utf-8"
            )
            updated.append(".cursor/rules/m5.mdc")
        except Exception:
            pass

    if not quiet and updated:
        print(f"[+] Injected M5 agent rules into: {', '.join(updated)}")
        print(f"    AI agents will now automatically prefer M5 over grep/reading files.")

    return updated


def print_banner():
    print("""
========================================================================
   M5 CONTEXT ENGINE — Agent Connection & Setup Guide
========================================================================
 Connect M5 to your favorite AI coding agents & IDEs with zero hassle.
 No silent file modifications — transparent, copy-pasteable configs!
========================================================================
""")


def print_agent_config(agent_key: str):
    configs = get_configs_dict()
    if agent_key not in configs:
        print(f"[!] Unknown agent choice: '{agent_key}'.")
        return

    item = configs[agent_key]
    print(f"\n────────────────────────────────────────────────────────────────────────")
    print(f"  Configuration for: {item['name']}")
    print(f"  Target File:       {item['target_file']}")
    print(f"────────────────────────────────────────────────────────────────────────\n")
    print("Add this JSON block to your configuration file:\n")
    print(json.dumps(item["config"], indent=2))
    print(f"\n[Where to Paste / Instructions]:\n{item['where_to_paste']}\n")


def print_instructions_marker():
    print("\n────────────────────────────────────────────────────────────────────────")
    print("  Optional: Agent Instructions Marker (CLAUDE.md / AGENTS.md / GEMINI.md)")
    print("────────────────────────────────────────────────────────────────────────\n")
    print("Paste this block into your CLAUDE.md, AGENTS.md, or GEMINI.md so agents")
    print("know how to use M5 CLI commands directly:\n")
    print(AGENT_INSTRUCTION_MARKER)
    print()


def run_setup_wizard(target: Optional[str] = None):
    print_banner()
    configs = get_configs_dict()

    if target:
        target_lower = target.lower().strip().replace("-", "").replace(" ", "").replace("_", "")
        if target_lower in ["8", "all", "full"]:
            for k in configs.keys():
                print_agent_config(k)
            print_instructions_marker()
            return
        if target_lower in ["9", "marker", "agent", "agents", "instructions"]:
            print_instructions_marker()
            return

        matched = False
        for k, v in configs.items():
            name_clean = v["name"].lower().replace("-", "").replace(" ", "").replace("_", "")
            if target_lower == k or target_lower in name_clean or target_lower in v["name"].lower():
                print_agent_config(k)
                matched = True
        if not matched:
            print(f"[!] No match found for '{target}'. Available targets:")
            for k, v in configs.items():
                print(f"  [{k}] {v['name']}")
            print("  [8] All Configurations")
            print("  [9] Agent Instructions Marker")
        return

    print("Choose your AI Editor / Agent to view manual setup instructions:\n")
    for k, v in configs.items():
        print(f"  [{k}] {v['name']}")
    print("  [8] All Configurations (Full Output)")
    print("  [9] Agent Instructions Marker (CLAUDE.md / AGENTS.md / GEMINI.md)")
    print("  [q] Exit\n")

    try:
        choice = input("Select an option (1-9 or q) [default: 8]: ").strip()
    except (EOFError, KeyboardInterrupt):
        choice = "8"

    if not choice:
        choice = "8"

    if choice.lower() in ["q", "exit"]:
        print("\nSetup exited. Run 'm5 help' to explore all commands.\n")
        return

    if choice == "8":
        for k in configs.keys():
            print_agent_config(k)
        print_instructions_marker()
    elif choice == "9":
        print_instructions_marker()
    elif choice in configs:
        print_agent_config(choice)
    else:
        print(f"[!] Invalid choice '{choice}'. Showing all configs:\n")
        for k in configs.keys():
            print_agent_config(k)

    print("========================================================================")
    print("  [NEXT STEPS]")
    print("  1. Build your project graph: run 'm5 build'")
    print("  2. Start real-time file watcher: run 'm5 live'")
    print("  3. Ask your AI agent any question, or run 'm5 trace \"<query>\"'")
    print("========================================================================\n")


if __name__ == "__main__":
    run_setup_wizard()

