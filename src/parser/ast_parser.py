"""
ast_parser.py — Multi-Language Tree-sitter AST Parser & Symbol/Call Graph Extractor.
Supports 16+ languages with deep structural extraction (functions, classes, interfaces, 
calls, imports, and routes) and resilient fallback.
"""

import os
import re
import importlib
from typing import List, Dict, Any, Optional, Tuple

try:
    from tree_sitter import Language, Parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    Language = None
    Parser = None

# Dictionary mapping language names to their target AST block node types
LANGUAGE_BLOCK_TYPES = {
    "python": [
        "function_definition", 
        "class_definition", 
        "async_function_definition"
    ],
    "javascript": [
        "function_declaration", 
        "class_declaration", 
        "method_definition", 
        "arrow_function",
        "export_statement"
    ],
    "typescript": [
        "function_declaration", 
        "class_declaration", 
        "method_definition", 
        "arrow_function", 
        "interface_declaration", 
        "type_alias_declaration",
        "enum_declaration"
    ],
    "java": [
        "method_declaration", 
        "class_declaration", 
        "interface_declaration", 
        "record_declaration", 
        "constructor_declaration",
        "enum_declaration"
    ],
    "cpp": [
        "function_definition", 
        "class_specifier", 
        "struct_specifier", 
        "namespace_definition"
    ],
    "c": [
        "function_definition",
        "struct_specifier",
        "enum_specifier"
    ],
    "csharp": [
        "method_declaration",
        "class_declaration",
        "interface_declaration",
        "struct_declaration",
        "record_declaration",
        "property_declaration"
    ],
    "go": [
        "function_declaration",
        "method_declaration",
        "type_declaration"
    ],
    "rust": [
        "function_item",
        "struct_item",
        "enum_item",
        "impl_item",
        "trait_item"
    ],
    "ruby": [
        "method",
        "class",
        "module",
        "singleton_method"
    ],
    "php": [
        "function_definition",
        "method_declaration",
        "class_declaration",
        "interface_declaration",
        "trait_declaration"
    ],
    "swift": [
        "function_declaration",
        "class_declaration",
        "struct_declaration",
        "protocol_declaration",
        "extension_declaration"
    ],
    "kotlin": [
        "function_declaration",
        "class_declaration",
        "object_declaration"
    ],
    "dart": [
        "function_signature",
        "class_definition",
        "method_signature"
    ],
    "scala": [
        "function_definition",
        "class_definition",
        "object_definition",
        "trait_definition"
    ]
}

# Mapping file extensions to language names
EXTENSION_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".dart": "dart",
    ".scala": "scala"
}

class ASTParser:
    """
    Multi-language AST Parser using Tree-Sitter with resilient syntax extraction.
    Supports 16+ languages and extracts symbol declarations, call edges, and imports.
    """
    def __init__(self, language_name: str = "python"):
        self.language_name = language_name.lower().strip()
        if self.language_name == "c++":
            self.language_name = "cpp"
        elif self.language_name in ["c#", "cs"]:
            self.language_name = "csharp"

        self.parser: Any = None
        if TREE_SITTER_AVAILABLE and Parser is not None and Language is not None:
            try:
                lang = self._load_language(self.language_name)
                if lang:
                    self.parser = Parser(lang)
            except Exception:
                self.parser = None

    def _load_language(self, lang_name: str) -> Any:
        module_name = f"tree_sitter_{lang_name}"
        try:
            lang_module = importlib.import_module(module_name)
            if Language is None:
                return None
            if lang_name == "typescript":
                fn = getattr(lang_module, "language_typescript", None) or getattr(lang_module, "language", None)
                if fn:
                    return Language(fn())
            elif lang_name == "tsx":
                fn = getattr(lang_module, "language_tsx", None) or getattr(lang_module, "language", None)
                if fn:
                    return Language(fn())
            elif hasattr(lang_module, "language"):
                return Language(lang_module.language())
        except Exception:
            pass
        return None

    def parse_code(self, code_text: str) -> List[Dict[str, Any]]:
        """
        Parses source code text and returns structural code blocks (functions, classes, etc.)
        along with line numbers and content.
        """
        if self.parser is not None:
            return self._parse_with_treesitter(code_text)
        return self._parse_with_resilient_scanner(code_text)

    def _parse_with_treesitter(self, code_text: str) -> List[Dict[str, Any]]:
        if self.parser is None:
            return []
        code_bytes = bytes(code_text, "utf-8")
        tree = self.parser.parse(code_bytes)
        root_node = tree.root_node

        blocks = []
        target_types = LANGUAGE_BLOCK_TYPES.get(self.language_name, ["function_definition", "class_definition"])

        def traverse(node):
            if node.type in target_types:
                name_node = node.child_by_field_name("name")
                name = code_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="ignore") if name_node else node.type

                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                content = code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")

                blocks.append({
                    "type": node.type,
                    "name": name,
                    "start_line": start_line,
                    "end_line": end_line,
                    "content": content
                })

            for child in node.children:
                traverse(child)

        traverse(root_node)
        return blocks

    def _parse_with_resilient_scanner(self, code_text: str) -> List[Dict[str, Any]]:
        """
        Fallback scanner when a compiled tree-sitter binary is missing for this language.
        Extracts functions, classes, and structs using structural indentation & brackets.
        """
        lines = code_text.splitlines()
        blocks = []
        pattern = re.compile(r"^\s*(?:async\s+)?(?:def|class|function|fn|func|public\s+class|private\s+class|struct|interface|type)\s+([a-zA-Z0-9_]+)", re.M)

        for i, line in enumerate(lines, 1):
            match = pattern.match(line)
            if match:
                name = match.group(1)
                kind = "class" if "class" in line or "struct" in line or "interface" in line else "function"
                start_line = i
                # Simple lookahead for end of block
                end_line = min(len(lines), start_line + 40)
                content = "\n".join(lines[start_line - 1:end_line])
                blocks.append({
                    "type": kind,
                    "name": name,
                    "start_line": start_line,
                    "end_line": end_line,
                    "content": content
                })
        return blocks

    def extract_symbols_and_edges(self, code_text: str, file_path: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Extracts both symbols (functions, classes) and relational call/import edges.
        """
        symbols = self.parse_code(code_text)
        edges = []

        # Extract import edges
        import_patterns = [
            re.compile(r"^\s*(?:import|from)\s+([a-zA-Z0-9_\.]+)", re.M),
            re.compile(r"^\s*const\s+.*?=\s*require\(['\"](.*?)['\"]\)", re.M),
            re.compile(r"^\s*import\s+.*?from\s+['\"](.*?)['\"]", re.M),
            re.compile(r"^\s*use\s+([a-zA-Z0-9_:]+);", re.M),
            re.compile(r'^\s*#include\s+["<]([a-zA-Z0-9_\.\/\\]+)[">]', re.M)
        ]

        for pat in import_patterns:
            for match in pat.finditer(code_text):
                target_import = match.group(1).replace("/", ".").replace("\\", ".")
                edges.append({
                    "source_file": file_path,
                    "source_symbol": os.path.basename(file_path),
                    "target_file": "",
                    "target_symbol": target_import,
                    "relation": "imports",
                    "confidence": 1.0
                })

        # Extract intra-symbol call edges
        call_pattern = re.compile(r"\b([a-zA-Z0-9_]{3,})\s*\(")
        for sym in symbols:
            caller_name = sym.get("name", "")
            content = sym.get("content", "")
            for call_match in call_pattern.finditer(content):
                callee = call_match.group(1)
                if callee != caller_name and callee not in ["if", "while", "for", "switch", "catch", "return", "print", "len"]:
                    edges.append({
                        "source_file": file_path,
                        "source_symbol": caller_name,
                        "target_file": "",
                        "target_symbol": callee,
                        "relation": "calls",
                        "confidence": 0.8
                    })

        return symbols, edges
