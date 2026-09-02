"""
test_impact.py — Automated Test Blast-Radius & Companion Test Pairing Engine.
Identifies exactly which unit and integration tests are affected when a function or file is modified.
"""

import os
import re
from typing import List, Dict, Any, Optional
from src.storage.local_db import LocalCodeGraphDB

class TestImpactEngine:
    """
    Analyzes code changes, traverses AST call graphs, and identifies affected test suites.
    """
    def __init__(self, db: Optional[LocalCodeGraphDB] = None):
        self.db = db or LocalCodeGraphDB()

    def find_companion_tests(self, file_path: str) -> List[str]:
        """Finds direct companion test files for a source file."""
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        ext = os.path.splitext(file_path)[1]

        test_candidates = [
            f"test_{base_name}{ext}",
            f"{base_name}_test{ext}",
            f"{base_name}.test{ext}",
            f"{base_name}.spec{ext}",
            f"{base_name}Test{ext}",
            f"Test{base_name}{ext}"
        ]

        found_tests = []
        with self.db._get_conn() as conn:
            for candidate in test_candidates:
                rows = conn.execute("""
                    SELECT file_path FROM files 
                    WHERE file_path LIKE ? OR file_path LIKE ?
                """, (f"%/{candidate}", f"%\\{candidate}")).fetchall()
                for r in rows:
                    p = r["file_path"]
                    if p not in found_tests:
                        found_tests.append(p)
        return found_tests

    def calculate_blast_radius(self, symbol_name: str, file_path: Optional[str] = None, max_depth: int = 2) -> Dict[str, Any]:
        """
        Traverses the upstream call graph to find all callers and test files impacted by a change.
        """
        impacted_symbols = set()
        impacted_files = set()
        impacted_tests = set()

        if file_path:
            impacted_files.add(file_path)
            for t in self.find_companion_tests(file_path):
                impacted_tests.add(t)

        # 1-2 hop caller traversal
        current_symbols = [symbol_name]
        for depth in range(max_depth):
            next_symbols = []
            for sym in current_symbols:
                callers = self.db.find_callers(sym, limit=50)
                for caller in callers:
                    src_sym = caller.get("source_symbol", "")
                    src_file = caller.get("source_file", "")
                    if src_sym and src_sym not in impacted_symbols:
                        impacted_symbols.add(src_sym)
                        next_symbols.append(src_sym)
                    if src_file and src_file not in impacted_files:
                        impacted_files.add(src_file)
                        if any(term in src_file.lower() for term in ["test", "spec", "mock"]):
                            impacted_tests.add(src_file)
            current_symbols = next_symbols
            if not current_symbols:
                break

        return {
            "target_symbol": symbol_name,
            "impacted_callers_count": len(impacted_symbols),
            "impacted_callers": list(impacted_symbols)[:20],
            "impacted_files_count": len(impacted_files),
            "impacted_files": list(impacted_files)[:20],
            "recommended_tests": list(impacted_tests)
        }

test_impact_engine = TestImpactEngine()
