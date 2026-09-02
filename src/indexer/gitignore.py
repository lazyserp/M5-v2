"""
gitignore.py — High-performance .gitignore & .m5ignore Parser for M5.
Ensures confidential files (.env, keys, tokens, secrets, logs, binaries) and user-ignored
patterns are strictly excluded from both SQLite AST graphs and Vector Embeddings.
"""

import os
import re
import fnmatch
from pathlib import Path
from typing import List, Tuple, Optional


# Default safety blacklist always enforced (confidential / secret / cache patterns)
DEFAULT_ALWAYS_IGNORE = [
    # Git & package managers
    ".git", ".git/**", "node_modules", "node_modules/**",
    ".venv", ".venv/**", "venv", "venv/**", "__pycache__", "__pycache__/**",
    "dist", "dist/**", "build", "build/**", ".pytest_cache", ".pytest_cache/**",
    # M5 internals & vector db
    ".m5", ".m5/**", "qdrant_storage", "qdrant_storage/**", "storage", "storage/**",
    ".agents", ".agents/**", ".vscode", ".vscode/**", ".cursor", ".cursor/**",
    # Sensitive credentials & environment variables
    ".env", ".env.*", ".env.local", ".env.production", ".env.development",
    "*.pem", "*.key", "*.crt", "*.cert", "*.pfx", "*.p12",
    "id_rsa", "id_rsa.pub", "id_ed25519", "id_ed25519.pub",
    "credentials.json", "service_account*.json", "client_secrets*.json",
    "*.secret", "*.secrets", "*.token", "*.token.*", "*.password",
    # Database files & large binaries
    "*.sqlite", "*.sqlite3", "*.db", "*.db3", "*.tar.gz", "*.zip", "*.bin"
]


class GitIgnoreRule:
    """Represents a single parsed .gitignore or .m5ignore rule."""
    def __init__(self, pattern: str, base_dir: str):
        self.raw_pattern = pattern
        self.base_dir = base_dir.replace("\\", "/").rstrip("/")
        self.is_negation = pattern.startswith("!")
        
        rule_body = pattern[1:] if self.is_negation else pattern
        self.dir_only = rule_body.endswith("/")
        rule_body = rule_body.rstrip("/")

        # If pattern starts with '/', it is relative to base_dir
        if rule_body.startswith("/"):
            self.anchored = True
            rule_body = rule_body[1:]
        elif "/" in rule_body:
            self.anchored = True
        else:
            self.anchored = False

        self.regex = self._compile_glob(rule_body)

    def _compile_glob(self, pattern: str) -> re.Pattern:
        """Translates gitignore glob pattern into compiled regular expression."""
        i, n = 0, len(pattern)
        res = []
        while i < n:
            c = pattern[i]
            i += 1
            if c == "*":
                if i < n and pattern[i] == "*":
                    i += 1
                    if i < n and pattern[i] == "/":
                        i += 1
                        res.append("(?:.+/)?")
                    else:
                        res.append(".*")
                else:
                    res.append("[^/]*")
            elif c == "?":
                res.append("[^/]")
            elif c == "[":
                j = i
                if j < n and pattern[j] == "!":
                    j += 1
                if j < n and pattern[j] == "]":
                    j += 1
                while j < n and pattern[j] != "]":
                    j += 1
                if j >= n:
                    res.append("\\[")
                else:
                    stuff = pattern[i:j].replace("\\", "\\\\")
                    i = j + 1
                    if stuff[0] == "!":
                        stuff = "^" + stuff[1:]
                    elif stuff[0] == "^":
                        stuff = "\\" + stuff
                    res.append(f"[{stuff}]")
            else:
                res.append(re.escape(c))
        return re.compile("^" + "".join(res) + "$")

    def matches(self, rel_path: str, is_dir: bool = False) -> bool:
        """
        Checks if relative path matches this rule.
        rel_path must use forward slashes '/'.
        """
        if self.dir_only and not is_dir:
            return False

        # If rule belongs to a subfolder's .gitignore, it ONLY applies inside that subfolder
        if self.base_dir:
            if rel_path == self.base_dir:
                check_path = ""
            elif rel_path.startswith(self.base_dir + "/"):
                check_path = rel_path[len(self.base_dir) + 1:]
            else:
                return False
        else:
            check_path = rel_path

        # If anchored or contains slash, match full check_path
        if self.anchored:
            return bool(self.regex.match(check_path))
        else:
            # Match check_path or any subdirectory segment or file basename
            if self.regex.match(check_path):
                return True
            parts = check_path.split("/")
            for part in parts:
                if self.regex.match(part):
                    return True
            return False


class GitIgnoreFilter:
    """
    Hierarchical GitIgnore & M5Ignore Filter.
    Loads and compiles .gitignore and .m5ignore from workspace root and subdirectories.
    """
    def __init__(self, workspace_root: str = "."):
        self.workspace_root = os.path.abspath(workspace_root).replace("\\", "/")
        self.rules: List[GitIgnoreRule] = []
        self._load_default_rules()
        self.reload()

    def _load_default_rules(self):
        """Loads built-in baseline confidential file patterns."""
        for pat in DEFAULT_ALWAYS_IGNORE:
            self.rules.append(GitIgnoreRule(pat, ""))

    def reload(self):
        """Discovers and reloads all .gitignore and .m5ignore files across workspace."""
        self.rules = []
        self._load_default_rules()

        # Find .gitignore and .m5ignore in workspace_root and subdirectories
        for root, dirs, files in os.walk(self.workspace_root):
            # Do not traverse into .git or node_modules
            dirs[:] = [d for d in dirs if d not in {".git", "node_modules", ".venv", "venv", ".m5"}]
            rel_dir = os.path.relpath(root, self.workspace_root).replace("\\", "/")
            if rel_dir == ".":
                rel_dir = ""

            for ignore_file in [".gitignore", ".m5ignore"]:
                file_path = os.path.join(root, ignore_file)
                if os.path.isfile(file_path):
                    self._parse_ignore_file(file_path, rel_dir)

    def _parse_ignore_file(self, file_path: str, base_dir: str):
        """Parses lines from an ignore file into GitIgnoreRules."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    self.rules.append(GitIgnoreRule(line, base_dir))
        except Exception:
            pass

    def is_ignored(self, path: str, is_dir: bool = False) -> bool:
        """
        Determines whether a file or directory path should be ignored.
        Accepts absolute or relative path.
        """
        norm_path = os.path.abspath(path).replace("\\", "/") if os.path.isabs(path) else path.replace("\\", "/")
        
        # Calculate relative path from workspace root
        if norm_path.startswith(self.workspace_root + "/"):
            rel_path = norm_path[len(self.workspace_root) + 1:]
        elif norm_path == self.workspace_root:
            rel_path = ""
        else:
            rel_path = os.path.relpath(norm_path, self.workspace_root).replace("\\", "/")
            if rel_path == ".":
                rel_path = ""

        # Test against rules in order
        ignored = False
        for rule in self.rules:
            if rule.matches(rel_path, is_dir=is_dir):
                if rule.is_negation:
                    ignored = False
                else:
                    ignored = True

        return ignored
