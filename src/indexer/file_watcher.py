"""
file_watcher.py — Real-time Sub-300ms File Watcher & Incremental Sync for M5.
Listens for file system changes and updates the local SQLite graph immediately on file save.
"""

import os
import time
import hashlib
import threading
from typing import Dict, Optional, Callable
from src.storage.local_db import LocalCodeGraphDB
from src.parser.ast_parser import ASTParser, EXTENSION_MAP
from src.indexer.gitignore import GitIgnoreFilter

class LocalFileWatcher:
    """
    Monitors workspace directory for file changes and updates SQLite AST graph in <300ms.
    Strictly adheres to .gitignore, .m5ignore, and sensitive credential blacklists.
    """
    def __init__(self, workspace_root: str = ".", db: Optional[LocalCodeGraphDB] = None):
        self.workspace_root = os.path.abspath(workspace_root)
        self.db = db or LocalCodeGraphDB()
        self.ignore_filter = GitIgnoreFilter(self.workspace_root)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._file_mtimes: Dict[str, float] = {}
        self.poll_interval = 0.3  # 300ms check loop

    def _should_index(self, file_path: str) -> bool:
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in EXTENSION_MAP:
            return False
        return not self.ignore_filter.is_ignored(file_path, is_dir=False)

    def sync_file(self, file_path: str):
        """Re-parses and syncs a single modified file into SQLite in <50ms."""
        try:
            if not os.path.exists(file_path) or self.ignore_filter.is_ignored(file_path, is_dir=False):
                self.db.clear_file_data(file_path)
                return

            ext = os.path.splitext(file_path)[1].lower()
            lang = EXTENSION_MAP.get(ext, "python")
            mtime = os.path.getmtime(file_path)

            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                code_text = f.read()

            file_hash = hashlib.md5(code_text.encode("utf-8")).hexdigest()

            parser = ASTParser(lang)
            symbols, edges = parser.extract_symbols_and_edges(code_text, file_path)

            # Clear old records & insert fresh AST blocks
            self.db.clear_file_data(file_path)
            self.db.insert_file(file_path, file_hash, mtime, lang)
            self.db.insert_symbols_batch(file_path, symbols)
            self.db.insert_edges_batch(edges)

            self._file_mtimes[file_path] = mtime
        except Exception as e:
            pass

    def initial_scan(self) -> int:
        """Performs initial walk and indexes all project files adhering to .gitignore."""
        self.ignore_filter.reload()
        count = 0
        for root, dirs, files in os.walk(self.workspace_root):
            # Prune ignored directories before recursing
            dirs[:] = [
                d for d in dirs
                if not self.ignore_filter.is_ignored(os.path.join(root, d), is_dir=True)
            ]
            for file in files:
                full_path = os.path.join(root, file).replace("\\", "/")
                if self._should_index(full_path):
                    self.sync_file(full_path)
                    count += 1
        return count

    def _watch_loop(self):
        loop_counter = 0
        while self._running:
            try:
                loop_counter += 1
                # Periodically reload ignore filter in case .gitignore was modified (every ~5s)
                if loop_counter % 15 == 0:
                    self.ignore_filter.reload()

                for root, dirs, files in os.walk(self.workspace_root):
                    dirs[:] = [
                        d for d in dirs
                        if not self.ignore_filter.is_ignored(os.path.join(root, d), is_dir=True)
                    ]
                    for file in files:
                        full_path = os.path.join(root, file).replace("\\", "/")
                        if self._should_index(full_path):
                            current_mtime = os.path.getmtime(full_path)
                            prev_mtime = self._file_mtimes.get(full_path, 0)
                            if current_mtime > prev_mtime:
                                self.sync_file(full_path)
            except Exception:
                pass
            time.sleep(self.poll_interval)

    def start(self):
        """Starts background file watcher."""
        if not self._running:
            self._running = True
            self.initial_scan()
            self._thread = threading.Thread(target=self._watch_loop, daemon=True)
            self._thread.start()

    def stop(self):
        """Stops background file watcher."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
