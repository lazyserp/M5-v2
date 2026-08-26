import os
import tempfile
from typing import List, Dict, Any, Optional

def write_to_file(target_file: str, code_content: str, overwrite: bool = False) -> str:
    """
    Creates a new file at target_file with code_content.
    Ensures parent directories exist.
    Guards against accidental overwrite if overwrite is False.
    """
    target_file = os.path.abspath(target_file)
    
    if os.path.exists(target_file) and not overwrite:
        return f"[ERROR] File already exists: {target_file}. Set overwrite=True to replace."
    
    try:
        parent_dir = os.path.dirname(target_file)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
            
        with open(target_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(code_content)
            
        return f"[SUCCESS] File written successfully: {target_file}"
    except Exception as e:
        return f"[ERROR] Failed to write file {target_file}: {str(e)}"


def replace_file_content(
    target_file: str,
    start_line: int,
    end_line: int,
    target_content: str,
    replacement_content: str,
    allow_multiple: bool = False
) -> str:
    """
    Replaces a contiguous block of text within [start_line, end_line] in target_file.
    1-indexed, inclusive range.
    Performs safety verification to ensure target_content matches the existing lines.
    """
    target_file = os.path.abspath(target_file)
    
    if not os.path.exists(target_file):
        return f"[ERROR] File not found: {target_file}"
        
    try:
        with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            
        total_lines = len(lines)
        if start_line < 1 or end_line > total_lines or start_line > end_line:
            return (
                f"[ERROR] Invalid line range [{start_line}, {end_line}]. "
                f"File has {total_lines} lines."
            )
            
        # Extract the target slice (1-indexed to 0-indexed)
        target_slice = "".join(lines[start_line - 1 : end_line])
        
        # Check if target_content is present in the specified slice
        # Normalize line endings for reliable comparison
        norm_slice = target_slice.replace("\r\n", "\n")
        norm_target = target_content.replace("\r\n", "\n")
        
        if norm_target not in norm_slice:
            return (
                f"[ERROR] Target content mismatch in lines [{start_line}, {end_line}].\n"
                f"Expected content:\n{target_content}\n"
                f"Found content in file:\n{target_slice}"
            )
            
        # Perform replacement within the slice
        if not allow_multiple and norm_slice.count(norm_target) > 1:
            return (
                f"[ERROR] Target content found multiple ({norm_slice.count(norm_target)}) times "
                f"in range [{start_line}, {end_line}]. Specify allow_multiple=True or narrow the range."
            )
            
        new_slice = norm_slice.replace(norm_target, replacement_content.replace("\r\n", "\n"))
        
        # Reconstruct the file lines
        prefix = lines[: start_line - 1]
        suffix = lines[end_line:]
        
        updated_content = "".join(prefix) + new_slice + "".join(suffix)
        
        with open(target_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(updated_content)
            
        line_delta = len(replacement_content.splitlines()) - len(target_content.splitlines())
        return (
            f"[SUCCESS] Replaced content in {target_file} (lines {start_line}-{end_line}). "
            f"Line delta: {line_delta:+d} lines."
        )
    except Exception as e:
        return f"[ERROR] Failed to replace content in {target_file}: {str(e)}"


def multi_replace_file_content(target_file: str, replacement_chunks: List[Dict[str, Any]]) -> str:
    """
    Applies multiple non-contiguous edits across target_file.
    Chunks are sorted descending by start_line (bottom-to-top) to prevent line offset drift.
    Each chunk must contain:
      - start_line (int)
      - end_line (int)
      - target_content (str)
      - replacement_content (str)
      - allow_multiple (bool, optional)
    """
    target_file = os.path.abspath(target_file)
    
    if not os.path.exists(target_file):
        return f"[ERROR] File not found: {target_file}"
        
    if not replacement_chunks:
        return "[ERROR] No replacement chunks provided."
        
    try:
        # Validate and sort chunks bottom-to-top
        sorted_chunks = sorted(
            replacement_chunks,
            key=lambda c: (c.get("start_line", 0), c.get("end_line", 0)),
            reverse=True
        )
        
        # Check for overlapping chunks
        for i in range(len(sorted_chunks) - 1):
            curr_chunk = sorted_chunks[i]
            prev_chunk = sorted_chunks[i + 1] # lower line numbers
            if curr_chunk["start_line"] <= prev_chunk["end_line"]:
                return (
                    f"[ERROR] Overlapping replacement chunks detected between "
                    f"[{prev_chunk['start_line']}, {prev_chunk['end_line']}] and "
                    f"[{curr_chunk['start_line']}, {curr_chunk['end_line']}]."
                )
                
        # Read initial file
        with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            
        applied_count = 0
        for chunk in sorted_chunks:
            start_line = chunk["start_line"]
            end_line = chunk["end_line"]
            target_content = chunk["target_content"]
            replacement_content = chunk["replacement_content"]
            allow_multiple = chunk.get("allow_multiple", False)
            
            total_lines = len(lines)
            if start_line < 1 or end_line > total_lines or start_line > end_line:
                return (
                    f"[ERROR] Chunk [{start_line}, {end_line}] is out of bounds (file has {total_lines} lines)."
                )
                
            target_slice = "".join(lines[start_line - 1 : end_line])
            norm_slice = target_slice.replace("\r\n", "\n")
            norm_target = target_content.replace("\r\n", "\n")
            
            if norm_target not in norm_slice:
                return (
                    f"[ERROR] Target content mismatch in chunk [{start_line}, {end_line}].\n"
                    f"Expected:\n{target_content}\n"
                    f"Found:\n{target_slice}"
                )
                
            if not allow_multiple and norm_slice.count(norm_target) > 1:
                return (
                    f"[ERROR] Target content in chunk [{start_line}, {end_line}] occurs multiple times."
                )
                
            new_slice = norm_slice.replace(norm_target, replacement_content.replace("\r\n", "\n"))
            
            prefix = lines[: start_line - 1]
            suffix = lines[end_line:]
            
            lines = (
                prefix
                + ([new_slice] if isinstance(new_slice, str) else new_slice)
                + suffix
            )
            # Re-split into clean lines list
            lines = "".join(lines).splitlines(keepends=True)
            applied_count += 1
            
        with open(target_file, "w", encoding="utf-8", newline="\n") as f:
            f.writelines(lines)
            
        return f"[SUCCESS] Applied {applied_count} non-contiguous edits successfully to {target_file}."
    except Exception as e:
        return f"[ERROR] Failed to execute multi-replace on {target_file}: {str(e)}"
