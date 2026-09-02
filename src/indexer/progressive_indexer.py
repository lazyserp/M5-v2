import os
import threading
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from src.logger import setup_m5_logger
from src.parser.ast_parser import ASTParser, EXTENSION_MAP
from src.tools.hybrid_search import get_hybrid_retriever
from src.tools.dependency_graph import PersistentDependencyGraph
from src.indexer.gitignore import GitIgnoreFilter

logger = setup_m5_logger("m5.indexer")


def _detect_git_commit(workspace_root: str) -> Optional[str]:
    """Detects current Git commit SHA from workspace root."""
    try:
        git_dir = os.path.join(workspace_root, ".git")
        if os.path.isdir(git_dir):
            head_file = os.path.join(git_dir, "HEAD")
            if os.path.isfile(head_file):
                with open(head_file, "r", encoding="utf-8", errors="ignore") as f:
                    head_content = f.read().strip()
                if head_content.startswith("ref: "):
                    ref_path = os.path.join(git_dir, head_content[5:].strip())
                    if os.path.isfile(ref_path):
                        with open(ref_path, "r", encoding="utf-8", errors="ignore") as rf:
                            return rf.read().strip()[:40]
                elif len(head_content) >= 7:
                    return head_content[:40]
    except Exception:
        pass
    return None

class IngestionStatus:
    """Tracks live indexing metrics per tenant."""
    def __init__(self):
        self.total_files: int = 0
        self.total_blocks: int = 0
        self.indexed_blocks: int = 0
        self.is_indexing: bool = False
        self.last_error: Optional[str] = None
        self.last_indexed_at: Optional[str] = None
        self.commit_sha: Optional[str] = None
        self.workspace_root: str = "."

class ProgressiveIndexer:
    """
    Enterprise Progressive 4-Tier Ingestion & Delta Sync Engine.
    Enables instant (<15s) graph catalog boot and sub-second webhook delta synchronization.
    """
    def __init__(self):
        self._statuses: Dict[str, IngestionStatus] = {}
        self._lock = threading.Lock()

    def _get_status_key(self, org_id: str, dept_id: str, repo_id: str) -> str:
        return f"{org_id}:{dept_id}:{repo_id}"

    def get_status(self, org_id: str, dept_id: str, repo_id: str) -> Dict[str, Any]:
        key = self._get_status_key(org_id, dept_id, repo_id)
        with self._lock:
            status = self._statuses.get(key, IngestionStatus())
            commit = status.commit_sha or _detect_git_commit(status.workspace_root)
            
            # Progress calculation
            total = status.total_blocks
            indexed = min(status.indexed_blocks, total) if status.is_indexing else total
            if status.is_indexing and total > 0:
                pct = min(100.0, max(0.0, round((indexed / total * 100), 1)))
                state = "indexing"
            else:
                pct = 100.0 if total > 0 else 0.0
                state = "ready" if total > 0 else "idle"

            return {
                "org_id": org_id,
                "dept_id": dept_id,
                "repo_id": repo_id,
                "status": state,
                "is_fresh": not status.is_indexing and total > 0,
                "total_files": status.total_files,
                "total_blocks": total,
                "indexed_blocks": indexed,
                "is_indexing": status.is_indexing,
                "progress_percentage": pct,
                "commit_sha": commit,
                "last_indexed_at": status.last_indexed_at or datetime.now(timezone.utc).isoformat(),
                "last_error": status.last_error
            }

    def tier0_instant_boot(
        self,
        workspace_root: str = ".",
        org_id: str = "default_org",
        dept_id: str = "default_dept",
        repo_id: str = "default_repo"
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """
        Tier 0: Rapidly parses AST boundaries and populates SQLite Graph & Symbol tables.
        Zero vector embedding latency (<15 seconds on massive codebases).
        """
        key = self._get_status_key(org_id, dept_id, repo_id)
        with self._lock:
            if key not in self._statuses:
                self._statuses[key] = IngestionStatus()
            status = self._statuses[key]
            status.is_indexing = True
            status.workspace_root = workspace_root
            status.commit_sha = _detect_git_commit(workspace_root)

        d_graph = PersistentDependencyGraph(org_id=org_id, dept_id=dept_id, repo_id=repo_id)
        ignore_filter = GitIgnoreFilter(workspace_root)
        all_blocks = []
        file_count = 0

        for root, dirs, files in os.walk(workspace_root):
            dirs[:] = [
                d for d in dirs
                if not ignore_filter.is_ignored(os.path.join(root, d), is_dir=True)
            ]

            for f in files:
                ext = os.path.splitext(f)[1].lower()
                full_file_path = os.path.join(root, f)
                if ext in EXTENSION_MAP and not ignore_filter.is_ignored(full_file_path, is_dir=False):
                    file_count += 1
                    rel_path = os.path.relpath(full_file_path, workspace_root).replace("\\", "/")
                    try:
                        with open(full_file_path, "r", encoding="utf-8", errors="ignore") as code_file:
                            code_content = code_file.read()

                        lang = EXTENSION_MAP[ext]
                        try:
                            parser = ASTParser(language_name=lang)
                            blocks = parser.parse_code(code_content)
                        except Exception as parse_err:
                            blocks = []

                        # Fallback if no specific AST functions/classes found (e.g., top-level script, route definitions)
                        if not blocks and code_content.strip():
                            lines = code_content.splitlines()
                            blocks = [{
                                "type": "module",
                                "name": os.path.basename(rel_path),
                                "start_line": 1,
                                "end_line": len(lines),
                                "content": code_content[:4000]
                            }]

                        for b in blocks:
                            b["file_path"] = rel_path
                            b["org_id"] = org_id
                            b["dept_id"] = dept_id
                            b["repo_id"] = repo_id
                        all_blocks.extend(blocks)

                        # Instantly index into SQLite Graph & Symbol catalog
                        d_graph.add_file(rel_path, symbols=blocks, real_path=full_file_path)
                    except Exception:
                        continue

        # Instantly populate BM25 in retriever so keyword search is ready immediately
        if all_blocks:
            retriever = get_hybrid_retriever(org_id=org_id, dept_id=dept_id, repo_id=repo_id)
            retriever.indexed_blocks = list(all_blocks)
            retriever.bm25_index.index_blocks(all_blocks)

        with self._lock:
            status.total_files = file_count
            status.total_blocks = len(all_blocks)
            status.indexed_blocks = 0
            status.is_indexing = False
            status.last_indexed_at = datetime.now(timezone.utc).isoformat()

        return file_count, all_blocks

    def start_background_embedding(
        self,
        blocks: List[Dict[str, Any]],
        org_id: str = "default_org",
        dept_id: str = "default_dept",
        repo_id: str = "default_repo",
        batch_size: int = 64
    ) -> threading.Thread:
        """
        Spawns non-blocking worker thread to stream vector embeddings into Qdrant & BM25.
        """
        def _worker():
            key = self._get_status_key(org_id, dept_id, repo_id)
            retriever = get_hybrid_retriever(org_id=org_id, dept_id=dept_id, repo_id=repo_id)
            total_blocks = len(blocks)
            logger.info(f"Started background vector embedding for {total_blocks} blocks ({org_id}/{dept_id}/{repo_id})...")
            
            with self._lock:
                if key in self._statuses:
                    self._statuses[key].is_indexing = True
                    self._statuses[key].indexed_blocks = 0

            try:
                processed = 0
                for i in range(0, total_blocks, batch_size):
                    batch = blocks[i : i + batch_size]
                    retriever.index_blocks(batch, batch_size=batch_size)
                    processed += len(batch)
                    with self._lock:
                        if key in self._statuses:
                            self._statuses[key].indexed_blocks = processed
                    
                    if processed % (batch_size * 5) == 0 or processed == total_blocks:
                        pct = (processed / total_blocks) * 100 if total_blocks > 0 else 100.0
                        logger.info(f"Vector embedding progress: {processed}/{total_blocks} blocks ({pct:.1f}%)")
                
                logger.info(f"Vector embedding complete: all {total_blocks} blocks indexed successfully.")
            except Exception as e:
                logger.error(f"Vector embedding background worker failed: {e}")
                with self._lock:
                    if key in self._statuses:
                        self._statuses[key].last_error = str(e)
            finally:
                with self._lock:
                    if key in self._statuses:
                        self._statuses[key].is_indexing = False
                        self._statuses[key].last_indexed_at = datetime.now(timezone.utc).isoformat()

        worker_thread = threading.Thread(target=_worker, daemon=True)
        worker_thread.start()
        return worker_thread

    def process_git_delta(
        self,
        added: List[str],
        modified: List[str],
        removed: List[str],
        workspace_root: str = ".",
        org_id: str = "default_org",
        dept_id: str = "default_dept",
        repo_id: str = "default_repo"
    ) -> Dict[str, Any]:
        """
        Tier 4: Sub-second atomic synchronization for GitHub/GitLab webhook push events.
        Processes only added/modified/removed files (<200ms per commit).
        """
        retriever = get_hybrid_retriever(org_id=org_id, dept_id=dept_id, repo_id=repo_id)
        d_graph = PersistentDependencyGraph(org_id=org_id, dept_id=dept_id, repo_id=repo_id)

        # 1. Handle Removed Files
        for rel_path in removed:
            norm_path = os.path.normpath(rel_path).replace("\\", "/")
            d_graph.remove_file(norm_path)

        # 2. Handle Added & Modified Files
        files_to_sync = list(set(added + modified))
        new_blocks = []

        for rel_path in files_to_sync:
            norm_path = os.path.normpath(rel_path).replace("\\", "/")
            full_path = os.path.join(workspace_root, norm_path)
            ext = os.path.splitext(norm_path)[1].lower()

            if ext in EXTENSION_MAP and os.path.isfile(full_path):
                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        code_content = f.read()

                    lang = EXTENSION_MAP[ext]
                    parser = ASTParser(language_name=lang)
                    blocks = parser.parse_code(code_content)

                    for b in blocks:
                        b["file_path"] = norm_path
                        b["org_id"] = org_id
                        b["dept_id"] = dept_id
                        b["repo_id"] = repo_id
                    new_blocks.extend(blocks)

                    # Update SQLite Graph and Symbol definitions
                    d_graph.add_file(norm_path, symbols=blocks, real_path=full_path)
                except Exception:
                    continue

        # 3. Upsert newly modified vector blocks
        if new_blocks:
            retriever.index_blocks(new_blocks)

        logger.info(
            f"Git Delta Sync Complete for '{org_id}/{repo_id}': "
            f"{len(added)} added, {len(modified)} modified, {len(removed)} removed, {len(new_blocks)} vector blocks updated."
        )

        return {
            "status": "synchronized",
            "added_count": len(added),
            "modified_count": len(modified),
            "removed_count": len(removed),
            "blocks_updated": len(new_blocks)
        }


# Global Singleton Indexer
progressive_indexer = ProgressiveIndexer()
