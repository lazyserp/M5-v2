import importlib
from tree_sitter import Language, Parser

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
        "arrow_function"
    ],
    "typescript": [
        "function_declaration", 
        "class_declaration", 
        "method_definition", 
        "arrow_function", 
        "interface_declaration", 
        "type_alias_declaration"
    ],
    "java": [
        "method_declaration", 
        "class_declaration", 
        "interface_declaration", 
        "record_declaration", 
        "constructor_declaration"
    ],
    "cpp": [
        "function_definition", 
        "class_specifier", 
        "struct_specifier", 
        "namespace_definition"
    ]
}

# Helper mapping extensions to language names
EXTENSION_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".h": "cpp",
    ".hpp": "cpp"
}

class ASTParser:
    """
    Multi-language AST Parser using Tree-Sitter.
    Supports Python, JavaScript, TypeScript, Java, and C++.
    """
    def __init__(self, language_name: str = "python"):
        self.language_name = language_name.lower().strip()
        self.language = self._load_language(self.language_name)
        self.parser = Parser(self.language)

    def _load_language(self, lang_name: str) -> Language:
        clean_name = lang_name.replace("c++", "cpp")
        module_name = f"tree_sitter_{clean_name}"
        
        try:
            lang_module = importlib.import_module(module_name)
            return Language(lang_module.language())
        except ImportError:
            raise ImportError(
                f"[ERROR] Tree-sitter grammar '{module_name}' is not installed.\n"
                f"Run 'pip install {module_name}' to enable parsing for '{lang_name}' files."
            )

    def parse_code(self, code_text: str) -> list[dict]:
        """
        Parses source code text and returns structural code blocks (functions, classes, etc.)
        along with line numbers and content.
        """
        code_bytes = bytes(code_text, "utf-8")
        tree = self.parser.parse(code_bytes)
        root_node = tree.root_node

        blocks = []
        target_types = LANGUAGE_BLOCK_TYPES.get(self.language_name, ["function_definition", "class_definition"])

        def traverse(node):
            if node.type in target_types:
                name_node = node.child_by_field_name("name")
                name = code_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8") if name_node else node.type

                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                content = code_bytes[node.start_byte:node.end_byte].decode("utf-8")

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
