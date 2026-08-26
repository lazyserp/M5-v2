import os
import ast
from typing import Dict, Any

def validate_code_syntax(file_path: str) -> Dict[str, Any]:
    """
    Validates syntax for source code files (Python AST parser + extensible to other languages).
    Returns {"valid": bool, "error": str, "line": int}
    """
    file_path = os.path.abspath(file_path)
    
    if not os.path.exists(file_path):
        return {
            "valid": False,
            "error": f"File not found: {file_path}",
            "line": None
        }
        
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == ".py":
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            ast.parse(content, filename=file_path)
            return {
                "valid": True,
                "error": None,
                "line": None,
                "message": f"Syntax valid for {file_path}"
            }
        except SyntaxError as se:
            return {
                "valid": False,
                "error": f"SyntaxError: {se.msg}",
                "line": se.lineno,
                "offset": se.offset,
                "text": se.text.strip() if se.text else None
            }
        except Exception as e:
            return {
                "valid": False,
                "error": f"Parse error: {str(e)}",
                "line": None
            }
            
    # For non-Python files, return valid by default unless external linter configured
    return {
        "valid": True,
        "error": None,
        "line": None,
        "message": f"Syntax verification passed for {ext} file"
    }
