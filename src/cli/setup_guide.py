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

    # Antigravity format (supports "type": "stdio")
    antigravity_server_spec: Dict[str, Any] = {
        "type": "stdio",
        "command": cmd,
        "args": args,
    }
    if env:
        antigravity_server_spec["env"] = env

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

    # 6. Codex CLI path
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
                    "m5": antigravity_server_spec
                }
            },
            "where_to_paste": (
                "Option A (Workspace level): Create `.agents/mcp_config.json` in your project root and paste the snippet.\n"
                f"Option B (Global level): Edit your global configuration at:\n  {gemini_global_path}"
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
## M5 Code Context & AST Knowledge Graph
This project uses M5 for instant AST code intelligence and dependency navigation.
Instead of repeatedly reading entire files or running multiple grep commands:
- Run `m5 trace "<query>"` to retrieve relevant symbol definitions, call hierarchies, and blast radius in 1 step.
- Run `m5 peek <symbol>` to view the exact implementation and callers of any function or class.
- Run `m5 callers <symbol>` or `m5 callees <symbol>` to navigate the call graph.
- Run `m5 diff-tests` to see tests affected by modified files.
<!-- M5 CONTEXT ENGINE END -->"""


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
        if target_lower in ["7", "all", "full"]:
            for k in configs.keys():
                print_agent_config(k)
            print_instructions_marker()
            return
        if target_lower in ["8", "marker", "agent", "agents", "instructions"]:
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
            print("  [7] All Configurations")
            print("  [8] Agent Instructions Marker")
        return

    print("Choose your AI Editor / Agent to view manual setup instructions:\n")
    for k, v in configs.items():
        print(f"  [{k}] {v['name']}")
    print("  [7] All Configurations (Full Output)")
    print("  [8] Agent Instructions Marker (CLAUDE.md / AGENTS.md / GEMINI.md)")
    print("  [q] Exit\n")

    try:
        choice = input("Select an option (1-8 or q) [default: 7]: ").strip()
    except (EOFError, KeyboardInterrupt):
        choice = "7"

    if not choice:
        choice = "7"

    if choice.lower() in ["q", "exit"]:
        print("\nSetup exited. Run 'm5 help' to explore all commands.\n")
        return

    if choice == "7":
        for k in configs.keys():
            print_agent_config(k)
        print_instructions_marker()
    elif choice == "8":
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

