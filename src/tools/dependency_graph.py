import os
import re
from typing import Optional, List, Dict, Any
from src.storage.local_db import LocalCodeGraphDB

class PersistentDependencyGraph:
    """
    Unified Dependency Graph adapter routing directly to the high-performance LocalCodeGraphDB.
    Eliminates database duplication while preserving backward compatibility.
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
        self.db = LocalCodeGraphDB(db_path=db_path)

    def add_file(
        self,
        file_path: str,
        symbols: Optional[List[Dict[str, Any]]] = None,
        real_path: Optional[str] = None
    ) -> None:
        norm_path = os.path.normpath(file_path).replace("\\", "/")
        self.db.insert_file(norm_path, "sha", 0.0, "unknown", repo_id=self.repo_id)
        if symbols:
            self.db.insert_symbols_batch(norm_path, symbols, repo_id=self.repo_id)

    def remove_file(self, file_path: str) -> None:
        norm_path = os.path.normpath(file_path).replace("\\", "/")
        self.db.clear_file_data(norm_path)

    def get_outgoing_edges(self, file_path: str) -> List[Dict[str, str]]:
        norm_path = os.path.normpath(file_path).replace("\\", "/")
        deps = self.db.get_outgoing_dependencies(norm_path, repo_filter=[self.repo_id] if self.repo_id != "default_repo" else None)
        return [{"target_file": d["target_file"] or d["target_symbol"], "raw_import": d["target_symbol"]} for d in deps]

    def get_incoming_edges(self, file_path: str) -> List[Dict[str, str]]:
        norm_path = os.path.normpath(file_path).replace("\\", "/")
        deps = self.db.get_incoming_dependents(norm_path, repo_filter=[self.repo_id] if self.repo_id != "default_repo" else None)
        return [{"source_file": d["source_file"], "raw_import": d["source_symbol"]} for d in deps]

    def get_edges_between_files(self, file_paths: List[str]) -> List[Dict[str, str]]:
        return self.db.get_edges_between_files(file_paths, repo_filter=[self.repo_id] if self.repo_id != "default_repo" else None)

    def find_companion_tests(self, file_path: str) -> List[str]:
        return self.db.find_companion_tests(file_path, repo_filter=[self.repo_id] if self.repo_id != "default_repo" else None)

    def get_dependencies(self, file_path: str) -> str:
        norm_path = os.path.normpath(file_path).replace("\\", "/")
        edges = self.get_outgoing_edges(norm_path)
        if not edges:
            return f"[INFO] File '{file_path}' does not import any recorded workspace modules."
        output = f"--- Outgoing Dependencies for '{file_path}' ---\n"
        for e in edges:
            output += f"- {e['target_file']} (import: '{e['raw_import']}')\n"
        return output

    def get_dependents(self, file_path: str) -> str:
        norm_path = os.path.normpath(file_path).replace("\\", "/")
        edges = self.get_incoming_edges(norm_path)
        if not edges:
            return f"[INFO] No workspace files depend on / import '{file_path}'."
        output = f"--- Dependent Files importing '{file_path}' ---\n"
        for e in edges:
            output += f"- {e['source_file']} (imports via '{e['raw_import']}')\n"
        return output

    def find_symbol_references(self, symbol_name: str) -> str:
        repo_filter = [self.repo_id] if self.repo_id != "default_repo" else None
        defs = self.db.find_symbol(symbol_name, exact=True, repo_filter=repo_filter)
        refs = self.db.find_symbol_references(symbol_name, repo_filter=repo_filter)
        if not defs and not refs:
            return f"[INFO] No definitions found for symbol '{symbol_name}'."
        output = f"--- Symbol Definitions for '{symbol_name}' ---\n"
        for d in defs:
            output += f"- [{d['file_path']}:{d.get('start_line', 0)}-{d.get('end_line', 0)}] ({d.get('kind', 'symbol')})\n"
        if refs:
            output += f"--- Symbol References & Callers for '{symbol_name}' ---\n"
            for r in refs:
                output += f"- [{r['source_file']}] (called by: {r['source_symbol']})\n"
        return output

# Backwards compatibility alias
CodeDependencyGraph = PersistentDependencyGraph
