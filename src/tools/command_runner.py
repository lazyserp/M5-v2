import os
import subprocess
import shlex
import sys
from typing import Dict, Any, Optional

# Security blacklist for dangerous/destructive commands
BLOCKED_PATTERNS = [
    "rm -rf /",
    "rm -rf *",
    "format c:",
    ":(){ :|:& };:",
    "mkfs",
    "dd if=/dev",
    "shutdown",
    "reboot",
]

def run_command(
    command_line: str,
    cwd: Optional[str] = None,
    timeout_seconds: int = 30
) -> Dict[str, Any]:
    """
    Executes a shell command synchronously with timeout and security guardrails.
    Returns a structured dictionary with stdout, stderr, exit_code, and success status.
    """
    if not command_line or not command_line.strip():
        return {
            "stdout": "",
            "stderr": "[ERROR] Empty command line provided.",
            "exit_code": 1,
            "success": False
        }
        
    cmd_lower = command_line.strip().lower()
    for blocked in BLOCKED_PATTERNS:
        if blocked in cmd_lower:
            return {
                "stdout": "",
                "stderr": f"[SECURITY ERROR] Command execution blocked due to forbidden pattern: '{blocked}'",
                "exit_code": -1,
                "success": False
            }
            
    exec_cwd = os.path.abspath(cwd) if cwd else os.getcwd()
    if not os.path.exists(exec_cwd):
        return {
            "stdout": "",
            "stderr": f"[ERROR] Working directory does not exist: {exec_cwd}",
            "exit_code": 1,
            "success": False
        }
        
    try:
        # Use shell=True for native Windows/Unix command parsing
        process = subprocess.run(
            command_line,
            cwd=exec_cwd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding="utf-8",
            errors="replace"
        )
        
        return {
            "stdout": process.stdout,
            "stderr": process.stderr,
            "exit_code": process.returncode,
            "success": process.returncode == 0
        }
    except subprocess.TimeoutExpired as te:
        return {
            "stdout": te.stdout or "",
            "stderr": f"[TIMEOUT ERROR] Command timed out after {timeout_seconds} seconds.",
            "exit_code": 124,
            "success": False
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": f"[EXECUTION ERROR] {str(e)}",
            "exit_code": 1,
            "success": False
        }
