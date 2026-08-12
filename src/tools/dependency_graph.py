import os
import networkx as nx
import re

class CodeDependencyGraph:
    """
    Codebase import dependency extractor using NetworkX directed graphs.
    """
    def __init__(self):
        self.graph = nx.DiGraph()
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


    def add_file(self,file_path:str):
        """
        Parses a file's import statements and adds dependency edges to the graph.
        """
        norm_path = os.path.normpath(file_path).replace("\\", "/")
        self.graph.add_node(norm_path)

        ext = norm_path.split(".")[-1].lower()

        patterns = self.import_patterns.get(ext,[])
        if not patterns:
            return
        try:
            with open(norm_path,"r",encoding="utf-8",errors="ignore") as f:
                lines = f.readlines()
        except Exception:
            return
        
        for line in lines:
            for pattern in patterns:
                match = pattern.match(line)
                if match:
                    imported_module = match.group(1)
                    resolved_path = self._resolve_import_path(norm_path, imported_module, ext)
                    
                    if resolved_path:
                        self.graph.add_node(resolved_path)
                        self.graph.add_edge(norm_path, resolved_path)

    
    def _resolve_import_path(self, current_file: str, imported_module: str, ext: str) -> str | None:
        """
        Resolves an import string (e.g. 'src.tools.line_reader') to a local file path.
        """
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
        return None

    def get_dependencies(self, file_path: str) -> str:
        """
        Tool callable by the agent to see what files a given file imports.
        """
        norm_path = os.path.normpath(file_path).replace("\\", "/")
        if norm_path not in self.graph:
            return f"[INFO] File '{file_path}' has no recorded dependencies in graph."
        deps = list(self.graph.successors(norm_path))
        if not deps:
            return f"[INFO] File '{file_path}' does not import any local workspace modules."
        output = f"--- Import Dependencies for '{file_path}' ---\n"
        for d in deps:
            output += f"- {d}\n"
        return output

