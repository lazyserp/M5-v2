import os

def read_file_lines(file_path:str,start_line:int,end_line:int,context_padding:int = 5) -> str:
    """
    Scalable range-based line reader for enterprise codebases.
    Reads only the requested line range from disk with padding.
    """
    
    if not os.path.exists(file_path):
        return f"[ERROR] File not found: {file_path}"

   
    padded_start = max(1,start_line-context_padding)
    padded_end = end_line + context_padding

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines_to_format = []
        for current_line_num , line_content in enumerate(f,start=1):
            if current_line_num >= padded_start and current_line_num <= padded_end:
                lines_to_format.append(f"{current_line_num:4d} | {line_content}")
            elif current_line_num > padded_end:
                break

    
    header = f"--- {file_path} (Lines {padded_start}-{padded_end}) ---\n"
    return header + "".join(lines_to_format)
