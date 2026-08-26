import os
from typing import Optional

def resolve_workspace_path(file_path: str, workspace_root: Optional[str] = None) -> Optional[str]:
    """
    Robustly resolves a relative, absolute, or workspace-prefixed file path
    against the configured WORKSPACE_ROOT.
    """
    if not file_path:
        return None

    root = workspace_root or os.getenv("WORKSPACE_ROOT", ".")
    clean_p = file_path.strip().replace("\\", "/")

    # 1. Direct file check
    if os.path.exists(clean_p) and os.path.isfile(clean_p):
        return os.path.abspath(clean_p)

    # 2. Check inside workspace_root
    joined = os.path.join(root, clean_p.lstrip("/"))
    if os.path.exists(joined) and os.path.isfile(joined):
        return os.path.abspath(joined)

    # 3. Handle possible leading workspace prefixes (e.g. 'workspace/src/...')
    parts = clean_p.lstrip("/").split("/", 1)
    if len(parts) > 1:
        joined_sub = os.path.join(root, parts[1])
        if os.path.exists(joined_sub) and os.path.isfile(joined_sub):
            return os.path.abspath(joined_sub)

    # 4. Walk workspace to match matching relative suffix
    norm_suffix = clean_p.lstrip("/")
    target_name = os.path.basename(clean_p)
    if target_name and os.path.exists(root):
        for r, _, files in os.walk(root):
            if target_name in files:
                candidate = os.path.join(r, target_name)
                cand_norm = candidate.replace("\\", "/")
                if cand_norm.endswith(norm_suffix):
                    return os.path.abspath(candidate)

    return None

def read_file_lines(
    file_path: str,
    start_line: int = 1,
    end_line: int = 50,
    context_padding: int = 5,
    workspace_root: Optional[str] = None
) -> str:
    """
    Scalable range-based line reader for enterprise codebases.
    Resolves paths against WORKSPACE_ROOT and reads requested line range with context padding.
    """
    actual_path = resolve_workspace_path(file_path, workspace_root=workspace_root)
    if not actual_path:
        return f"[ERROR] File not found: '{file_path}' in workspace '{workspace_root or os.getenv('WORKSPACE_ROOT', '.')}'"

    padded_start = max(1, start_line - context_padding)
    padded_end = end_line + context_padding

    try:
        with open(actual_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines_to_format = []
            for current_line_num, line_content in enumerate(f, start=1):
                if current_line_num >= padded_start and current_line_num <= padded_end:
                    lines_to_format.append(f"{current_line_num:4d} | {line_content}")
                elif current_line_num > padded_end:
                    break

        header = f"--- {file_path} (Lines {padded_start}-{padded_end}) ---\n"
        return header + "".join(lines_to_format)
    except Exception as e:
        return f"[ERROR] Failed to read '{actual_path}': {e}"
