"""
multi_repo_graph.py — Multi-Repository Context Federation & Cross-Service Graph.
Allows AI coding agents to trace API routes, RPC definitions, and shared contracts
across multiple repositories in an enterprise organization.
"""

import os
import sqlite3
from typing import List, Dict, Any, Optional

class MultiRepoGraph:
    """
    Federates multiple individual repository SQLite graphs into a unified organizational context.
    """
    def __init__(self, storage_dir: str = "./storage/graphs"):
        self.storage_dir = os.path.abspath(storage_dir)
        os.makedirs(self.storage_dir, exist_ok=True)

    def list_registered_repos(self) -> List[str]:
        """Lists all registered repository databases."""
        if not os.path.exists(self.storage_dir):
            return []
        return [
            f.replace(".db", "") for f in os.listdir(self.storage_dir) 
            if f.endswith(".db")
        ]

    def cross_repo_symbol_search(self, symbol_name: str, limit_per_repo: int = 5) -> List[Dict[str, Any]]:
        """Searches across all company repositories for matching symbol definitions."""
        results = []
        for repo_file in os.listdir(self.storage_dir):
            if not repo_file.endswith(".db"):
                continue
            db_path = os.path.join(self.storage_dir, repo_file)
            try:
                conn = sqlite3.connect(db_path, timeout=3.0)
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT name, kind, file_path, start_line, end_line, content
                    FROM symbols
                    WHERE name LIKE ?
                    LIMIT ?
                """, (f"%{symbol_name}%", limit_per_repo)).fetchall()
                for r in rows:
                    d = dict(r)
                    d["repository"] = repo_file.replace(".db", "")
                    results.append(d)
                conn.close()
            except Exception:
                pass
        return results

    def find_cross_repo_api_contracts(self, route_or_schema: str) -> List[Dict[str, Any]]:
        """Finds API definitions in backend services matching frontend fetch/axios calls."""
        results = []
        for repo_file in os.listdir(self.storage_dir):
            if not repo_file.endswith(".db"):
                continue
            db_path = os.path.join(self.storage_dir, repo_file)
            try:
                conn = sqlite3.connect(db_path, timeout=3.0)
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT name, kind, file_path, start_line, end_line, content
                    FROM symbols
                    WHERE content LIKE ?
                    LIMIT 5
                """, (f"%{route_or_schema}%",)).fetchall()
                for r in rows:
                    d = dict(r)
                    d["repository"] = repo_file.replace(".db", "")
                    results.append(d)
                conn.close()
            except Exception:
                pass
        return results

multi_repo_graph = MultiRepoGraph()
