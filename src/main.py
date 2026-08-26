import os
import sys
from src.indexer.progressive_indexer import progressive_indexer
from src.context.context_engine import get_context

def index_workspace(workspace_root: str = "."):
    """
    Crawls the workspace, parses AST blocks, indexes vectors in Qdrant & BM25,
    and builds the Code Dependency Graph.
    """
    print(f"\n[+] Indexing Workspace: '{workspace_root}'...")
    file_count, blocks = progressive_indexer.tier0_instant_boot(
        workspace_root=workspace_root,
        org_id="default_org",
        dept_id="default_dept",
        repo_id="default_repo"
    )
    progressive_indexer.start_background_embedding(
        blocks=blocks,
        org_id="default_org",
        dept_id="default_dept",
        repo_id="default_repo"
    )
    print(f"[SUCCESS] Indexed {file_count} files ({len(blocks)} AST blocks) into Qdrant & SQLite graph!")

def main():
    index_workspace(os.getenv("WORKSPACE_ROOT", "."))

    print("\n==================================================")
    print("  M5 v2 Context Engine (Interactive CLI)         ")
    print("  Grounded Retrieval: Qdrant + BM25 + DepGraph   ")
    print("  (Type 'exit' or 'quit' to stop)                ")
    print("==================================================")

    while True:
        try:
            user_query = input("\nQuery Context Engine > ").strip()
            if not user_query:
                continue
            if user_query.lower() in ["exit", "quit"]:
                print("Goodbye!")
                break

            bundle = get_context(
                query=user_query,
                top_k=4,
                expand_dependencies=True,
                org_id="default_org",
                dept_id="default_dept",
                repo_id="default_repo"
            )

            chunks = bundle.get("chunks", [])
            print(f"\n[+] Retrieved {len(chunks)} precise code chunks from Qdrant/BM25:")
            for i, c in enumerate(chunks, 1):
                print(f"\n[{i}] {c.get('file_path')} (L{c.get('start_line')}-L{c.get('end_line')}) | {c.get('symbol_name')} ({c.get('symbol_type')})")
                print("    " + c.get("content", "").replace("\n", "\n    "))

            dep_edges = bundle.get("dependency_edges", [])
            if dep_edges:
                print("\n[+] Dependency Relationships:")
                for edge in dep_edges:
                    print(f"    - {edge.get('from')} -> {edge.get('to')}")

            print(f"\n[+] Estimated tokens for this context: {bundle.get('estimated_tokens', 0)} tokens")

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
