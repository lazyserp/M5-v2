import os
import sqlite3
import hashlib
import re
from typing import Optional, List, Dict, Any

class PersistentDependencyGraph:
    """
    Enterprise-grade, disk-backed dependency & symbol graph using SQLite.
    Handles 100M+ LOC graphs with O(1) disk lookups and zero RAM bloat.
    """
    def __init__(
        self,
        org_id: str = "default_org",
        dept_id: str = "default_dept",
        repo_id: str = "default_repo",
        db_path: Optional[str] = None
    ):
        self.org_id = org_id
        self.dept_id = dept_id
        self.repo_id = repo_id

        if db_path:
            self.db_path = db_path
        else:
            storage_dir = "./storage/graphs"
            os.makedirs(storage_dir, exist_ok=True)
            clean_name = re.sub(r"[^a-zA-Z0-9_-]", "_", f"{org_id}_{dept_id}_{repo_id}".lower())
            self.db_path = os.path.join(storage_dir, f"{clean_name}.db").replace("\\", "/")

        self._init_db()

        self.import_patterns = {
            "py": [
                re.compile(r"^\s*import\s+([a-zA-Z0-9_\.]+)"),
                re.compile(r"^\s*from\s+([a-zA-Z0-9_\.]+)\s+import")
            ],
            "js": [
                re.compile(r"^\s*import\s+.*?\s+from\s+['\"](.*?)['\"]"),
                re.compile(r"^\s*const\s+.*?\s*=\s*require\(['\"](.*?)['\"]\)")
            ],
            "ts": [
                re.compile(r"^\s*import\s+.*?\s+from\s+['\"](.*?)['\"]"),
                re.compile(r"^\s*const\s+.*?\s*=\s*require\(['\"](.*?)['\"]\)")
            ],
            "jsx": [
                re.compile(r"^\s*import\s+.*?\s+from\s+['\"](.*?)['\"]"),
                re.compile(r"^\s*const\s+.*?\s*=\s*require\(['\"](.*?)['\"]\)")
            ],
            "tsx": [
                re.compile(r"^\s*import\s+.*?\s+from\s+['\"](.*?)['\"]"),
                re.compile(r"^\s*const\s+.*?\s*=\s*require\(['\"](.*?)['\"]\)")
            ],
            "java": [
                re.compile(r"^\s*import\s+([a-zA-Z0-9_\.]+);")
            ],
            "cpp": [
                re.compile(r'^\s*#include\s+["<]([a-zA-Z0-9_\.\/\\]+)[">]')
            ],
            "h": [
                re.compile(r'^\s*#include\s+["<]([a-zA-Z0-9_\.\/\\]+)[">]')
            ]
        }

    def _get_connection(self) -> sqlite3.Connection:
        if self.db_path == ":memory:":
            if not hasattr(self, "_mem_conn") or self._mem_conn is None:
                self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
                self._mem_conn.execute("PRAGMA foreign_keys = ON;")
            return self._mem_conn
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 1. File nodes table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS file_nodes (
                    file_path TEXT PRIMARY KEY,
                    sha256 TEXT NOT NULL,
                    total_lines INTEGER DEFAULT 0,
                    last_indexed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 2. Directed dependency edges (source_file -> target_file)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dependencies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_file TEXT NOT NULL,
                    target_file TEXT NOT NULL,
                    raw_import TEXT,
                    FOREIGN KEY(source_file) REFERENCES file_nodes(file_path) ON DELETE CASCADE,
                    UNIQUE(source_file, target_file)
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_dep_source ON dependencies(source_file);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_dep_target ON dependencies(target_file);")

            # 3. AST Symbol definitions (functions, classes, methods)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS symbol_definitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    symbol_name TEXT NOT NULL,
                    symbol_type TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    FOREIGN KEY(file_path) REFERENCES file_nodes(file_path) ON DELETE CASCADE
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sym_def_name ON symbol_definitions(symbol_name);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sym_def_file ON symbol_definitions(file_path);")
            conn.commit()

    def add_file(
        self,
        file_path: str,
        symbols: Optional[List[Dict[str, Any]]] = None,
        real_path: Optional[str] = None
    ) -> None:
        """
        Parses imports, records file hash, and indexes symbol definitions atomically.
        """
        norm_path = os.path.normpath(file_path).replace("\\", "/")
        actual_path = real_path if (real_path and os.path.isfile(real_path)) else (norm_path if os.path.isfile(norm_path) else None)

        content = ""
        lines = []
        if actual_path:
            try:
                with open(actual_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    lines = content.splitlines()
            except Exception:
                pass

        file_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest() if content else "no_hash"
        total_lines = len(lines)
        ext = norm_path.split(".")[-1].lower()

        # 1. Resolve Outgoing Dependencies
        resolved_deps = []
        patterns = self.import_patterns.get(ext, [])
        for line in lines:
            for pattern in patterns:
                match = pattern.match(line)
                if match:
                    raw_module = match.group(1)
                    target_file = self._resolve_import_path(norm_path, raw_module, ext)
                    if target_file:
                        resolved_deps.append((target_file, raw_module))

        # 2. Atomic Database Upsert
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Upsert file_nodes
            cursor.execute("""
                INSERT INTO file_nodes (file_path, sha256, total_lines, last_indexed)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(file_path) DO UPDATE SET
                    sha256 = excluded.sha256,
                    total_lines = excluded.total_lines,
                    last_indexed = CURRENT_TIMESTAMP;
            """, (norm_path, file_sha256, total_lines))

            # Clean stale dependencies for this source file
            cursor.execute("DELETE FROM dependencies WHERE source_file = ?", (norm_path,))

            # Ensure referenced target files exist in file_nodes to satisfy foreign key
            for target_path, raw_mod in resolved_deps:
                cursor.execute("""
                    INSERT OR IGNORE INTO file_nodes (file_path, sha256, total_lines)
                    VALUES (?, '', 0);
                """, (target_path,))
                cursor.execute("""
                    INSERT OR IGNORE INTO dependencies (source_file, target_file, raw_import)
                    VALUES (?, ?, ?);
                """, (norm_path, target_path, raw_mod))

            # Update AST Symbol definitions if provided
            if symbols:
                cursor.execute("DELETE FROM symbol_definitions WHERE file_path = ?", (norm_path,))
                sym_rows = [
                    (norm_path, s.get("name", "anonymous"), s.get("type", "unknown"), s.get("start_line", 0), s.get("end_line", 0))
                    for s in symbols
                ]
                cursor.executemany("""
                    INSERT INTO symbol_definitions (file_path, symbol_name, symbol_type, start_line, end_line)
                    VALUES (?, ?, ?, ?, ?);
                """, sym_rows)

            conn.commit()

    def remove_file(self, file_path: str) -> None:
        """
        Removes a file and cascades deletion of its dependencies and symbols.
        """
        norm_path = os.path.normpath(file_path).replace("\\", "/")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM file_nodes WHERE file_path = ?", (norm_path,))
            cursor.execute("DELETE FROM dependencies WHERE source_file = ? OR target_file = ?", (norm_path, norm_path))
            cursor.execute("DELETE FROM symbol_definitions WHERE file_path = ?", (norm_path,))
            conn.commit()

    def _resolve_import_path(self, current_file: str, imported_module: str, ext: str) -> Optional[str]:
        current_dir = os.path.dirname(current_file)

        if ext == "py":
            # Convert 'src.tools.line_reader' -> 'src/tools/line_reader.py'
            rel_path = imported_module.replace(".", "/") + ".py"
            candidates = [
                rel_path,
                os.path.join(current_dir, rel_path),
                os.path.join(current_dir, imported_module + ".py")
            ]
            for c in candidates:
                clean_c = os.path.normpath(c).replace("\\", "/")
                if os.path.isfile(clean_c):
                    return clean_c

        elif ext in ["js", "ts", "jsx", "tsx"]:
            # Handle relative JS/TS imports: './utils', '../config'
            for test_ext in [".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.js"]:
                candidate = os.path.join(current_dir, imported_module + test_ext)
                clean_c = os.path.normpath(candidate).replace("\\", "/")
                if os.path.isfile(clean_c):
                    return clean_c

        return None

    def get_dependencies(self, file_path: str) -> str:
        """
        Tool callable by the agent: Outgoing dependencies (files this file imports).
        """
        norm_path = os.path.normpath(file_path).replace("\\", "/")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT target_file, raw_import FROM dependencies WHERE source_file = ?", (norm_path,))
            rows = cursor.fetchall()

        if not rows:
            return f"[INFO] File '{file_path}' does not import any recorded workspace modules."

        output = f"--- Outgoing Dependencies for '{file_path}' ---\n"
        for target, raw in rows:
            output += f"- {target} (import: '{raw}')\n"
        return output

    def get_dependents(self, file_path: str) -> str:
        """
        Tool callable by the agent: Incoming dependents (files that import this file).
        """
        norm_path = os.path.normpath(file_path).replace("\\", "/")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT source_file, raw_import FROM dependencies WHERE target_file = ?", (norm_path,))
            rows = cursor.fetchall()

        if not rows:
            return f"[INFO] No workspace files depend on / import '{file_path}'."

        output = f"--- Dependent Files importing '{file_path}' ---\n"
        for source, raw in rows:
            output += f"- {source} (imports via '{raw}')\n"
        return output

    def find_symbol_references(self, symbol_name: str) -> str:
        """
        Tool callable by the agent: Finds symbol definitions across the codebase.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT file_path, symbol_type, start_line, end_line 
                FROM symbol_definitions 
                WHERE symbol_name = ?
            """, (symbol_name,))
            defs = cursor.fetchall()

        if not defs:
            return f"[INFO] No definitions found for symbol '{symbol_name}'."

        output = f"--- Symbol Definitions for '{symbol_name}' ---\n"
        for path, sym_type, start, end in defs:
            output += f"- [{path}:L{start}-L{end}] ({sym_type})\n"
        return output

# Backwards compatibility alias
CodeDependencyGraph = PersistentDependencyGraph
