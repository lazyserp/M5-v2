import os
import sys
from src.parser.ast_parser import ASTParser, EXTENSION_MAP
from src.agents.react_loop import run_agent_loop, vector_store, dep_graph

def index_workspace(workspace_root: str = "."):
    """
    Crawls the workspace, parses AST blocks, indexes vectors in Qdrant,
    and builds the Code Dependency Graph.
    """
    print(f"\n[+] Crawling & Indexing Workspace: '{workspace_root}'...")
    all_blocks = []
    ignore_dirs = {".git", "__pycache__", "venv", ".venv", "node_modules"}

    for root, dirs, files in os.walk(workspace_root):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]

        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in EXTENSION_MAP:
                rel_path = os.path.relpath(os.path.join(root, f), workspace_root).replace("\\", "/")
                
                # 1. Build Dependency Graph
                dep_graph.add_file(rel_path)

                # 2. Parse AST Blocks
                try:
                    with open(rel_path, "r", encoding="utf-8", errors="ignore") as code_file:
                        code_content = code_file.read()

                    lang = EXTENSION_MAP[ext]
                    parser = ASTParser(language_name=lang)
                    blocks = parser.parse_code(code_content)

                    for b in blocks:
                        b["file_path"] = rel_path
                    all_blocks.extend(blocks)
                except Exception as e:
                    continue

    # 3. Index all AST blocks into Qdrant Vector Store
    if all_blocks:
        vector_store.index_blocks(all_blocks)
        print(f"[SUCCESS] Indexed {len(all_blocks)} AST blocks across workspace into Qdrant!")

def main():
    # 1. Auto-Index current workspace on startup
    index_workspace(".")

    print("\n==================================================")
    print("  M5 v2 Enterprise Engine ")
    print("  Tools Loaded: LineReader | VectorSearch | DepGraph")
    print("  (Type 'exit' or 'quit' to stop)                 ")
    print("==================================================")

    while True:
        try:
            user_query = input("\nAsk M5 v2 > ").strip()
            if not user_query:
                continue
            if user_query.lower() in ["exit", "quit"]:
                print("Goodbye!")
                break

            answer = run_agent_loop(user_query)
            print("\n" + answer)

        except KeyboardInterrupt:
            print("\nExiting...")
            break

if __name__ == "__main__":
    main()
