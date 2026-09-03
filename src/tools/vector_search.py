import os
import uuid
import hashlib
import re
import threading
import atexit
from typing import Optional, List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchAny
from fastembed import TextEmbedding

# Suppress interpreter-shutdown deallocator exceptions in QdrantClient / QdrantLocal
try:
    _orig_qdrant_del = getattr(QdrantClient, "__del__", None)
    def _safe_qdrant_del(self: Any) -> None:
        try:
            if _orig_qdrant_del:
                _orig_qdrant_del(self)
        except BaseException:
            pass
    QdrantClient.__del__ = _safe_qdrant_del
except Exception:
    pass

try:
    from qdrant_client.local.qdrant_local import QdrantLocal
    _orig_local_close = getattr(QdrantLocal, "close", None)
    def _safe_local_close(self: Any, **kwargs: Any) -> None:
        try:
            if _orig_local_close:
                _orig_local_close(self, **kwargs)
        except BaseException:
            pass
    QdrantLocal.close = _safe_local_close
except Exception:
    pass

_CLIENT_CACHE: Dict[str, QdrantClient] = {}
_CLIENT_LOCK = threading.Lock()

def close_all_qdrant_clients() -> None:
    """
    Cleanly closes all active Qdrant clients before interpreter shutdown.
    Releases flock handles while sys.meta_path and modules are intact.
    """
    global _IN_MEMORY_CLIENT, _CLIENT_CACHE
    with _CLIENT_LOCK:
        for client in list(_CLIENT_CACHE.values()):
            try:
                client.close()
            except BaseException:
                pass
        _CLIENT_CACHE.clear()
        if _IN_MEMORY_CLIENT is not None:
            try:
                _IN_MEMORY_CLIENT.close()
            except BaseException:
                pass
            _IN_MEMORY_CLIENT = None

atexit.register(close_all_qdrant_clients)

_EMBEDDER_INSTANCE: Optional[TextEmbedding] = None
_EMBEDDER_LOCK = threading.Lock()

def get_shared_embedder() -> TextEmbedding:
    """
    Returns a global singleton TextEmbedding instance.
    Prevents reloading the ONNX model from disk on every query (reduces latency by 95%).
    """
    global _EMBEDDER_INSTANCE
    if _EMBEDDER_INSTANCE is None:
        with _EMBEDDER_LOCK:
            if _EMBEDDER_INSTANCE is None:
                cpu_cores = max(1, (os.cpu_count() or 4))
                _EMBEDDER_INSTANCE = TextEmbedding(
                    model_name="BAAI/bge-small-en-v1.5",
                    threads=cpu_cores
                )
    return _EMBEDDER_INSTANCE

def sanitize_collection_name(name: str) -> str:
    """Sanitizes names into valid Qdrant collection identifiers."""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", name.lower().strip())
    return cleaned if cleaned else "m5_default"

def _default_qdrant_storage() -> str:
    dot_m5 = os.path.join(os.getcwd(), ".m5")
    os.makedirs(dot_m5, exist_ok=True)
    return os.path.join(dot_m5, "qdrant_db")

def _try_local_qdrant(norm_path: str) -> Optional[QdrantClient]:
    """
    Attempts to open a local Qdrant storage folder.
    Falls back to in-memory mode if disk storage is locked or incompatible.
    """
    try:
        os.makedirs(norm_path, exist_ok=True)
        client = QdrantClient(path=norm_path, check_compatibility=False)
        client.get_collections()
        return client
    except Exception:
        return None


_IN_MEMORY_CLIENT: Optional[QdrantClient] = None

def get_shared_qdrant_client(
    storage_path: Optional[str] = None,
    url: Optional[str] = None,
    api_key: Optional[str] = None,
    in_memory: bool = False
) -> QdrantClient:
    """
    Returns a shared Qdrant client. Defaults to pure in-process embedded disk mode
    in .m5/qdrant_db with zero Docker overhead, or connects to remote Qdrant if URL is set.
    """
    global _IN_MEMORY_CLIENT

    if in_memory:
        with _CLIENT_LOCK:
            if _IN_MEMORY_CLIENT is None:
                _IN_MEMORY_CLIENT = QdrantClient(location=":memory:", check_compatibility=False)
            return _IN_MEMORY_CLIENT

    target_url = (url or os.getenv("QDRANT_URL", "")).strip()
    target_api_key = (api_key or os.getenv("QDRANT_API_KEY", "")).strip() or None

    # Only connect over network if an explicit remote URL was provided
    if target_url:
        try:
            client_kwargs = {"url": target_url, "timeout": 3, "check_compatibility": False}
            if target_api_key:
                client_kwargs["api_key"] = target_api_key
            client = QdrantClient(**client_kwargs)
            client.get_collections()
            return client
        except Exception:
            pass  # Fall back to local embedded mode if remote is unreachable

    # Local embedded disk storage (0 Docker, 0 network ports, in-process)
    disk_path = storage_path or _default_qdrant_storage()
    with _CLIENT_LOCK:
        norm_path = os.path.abspath(disk_path)
        if norm_path not in _CLIENT_CACHE:
            local_client = _try_local_qdrant(norm_path)
            if local_client is None:
                if _IN_MEMORY_CLIENT is None:
                    _IN_MEMORY_CLIENT = QdrantClient(location=":memory:", check_compatibility=False)
                _CLIENT_CACHE[norm_path] = _IN_MEMORY_CLIENT
            else:
                _CLIENT_CACHE[norm_path] = local_client
        return _CLIENT_CACHE[norm_path]

class VectorStore:
    """
    Universal Vector Store for Qdrant.
    Supports in-process embedded storage for solo developers and remote cluster storage
    with repo-level ACL filtering for enterprises.
    """
    def __init__(
        self,
        org_id: str = "default_org",
        dept_id: str = "default_dept",
        repo_id: str = "default_repo",
        storage_path: Optional[str] = None,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        in_memory: bool = False,
        collection_name: Optional[str] = None
    ) -> None:
        self.org_id = org_id
        self.dept_id = dept_id
        self.repo_id = repo_id
        
        raw_name = collection_name or f"m5_{org_id}_{dept_id}_{repo_id}"
        self.collection_name = sanitize_collection_name(raw_name)
        
        self.vector_size = 384
        self.embedder = get_shared_embedder()

        self.client = get_shared_qdrant_client(
            storage_path=storage_path,
            url=url,
            api_key=api_key,
            in_memory=in_memory
        )
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        try:
            if not self.client.collection_exists(self.collection_name):
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE)
                )
        except Exception:
            pass

    def generate_point_id(self, block: dict) -> str:
        file_path = block.get("file_path", "unknown")
        start_line = block.get("start_line", 0)
        end_line = block.get("end_line", 0)
        name = block.get("name", "anonymous")
        content = block.get("content", "")

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        signature = f"{self.org_id}:{self.dept_id}:{self.repo_id}:{file_path}:{start_line}:{end_line}:{name}:{content_hash}"
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, signature))

    def get_existing_point_ids(self, point_ids: list[str]) -> set[str]:
        """Checks which point IDs already exist in the Qdrant collection."""
        if not point_ids:
            return set()
        existing = set()
        for i in range(0, len(point_ids), 500):
            batch_ids = point_ids[i : i + 500]
            try:
                records = self.client.retrieve(
                    collection_name=self.collection_name,
                    ids=batch_ids,
                    with_payload=False,
                    with_vectors=False
                )
                for r in records:
                    existing.add(str(r.id))
            except Exception:
                pass
        return existing

    def index_blocks(self, blocks: list[dict], batch_size: int = 64) -> int:
        if not blocks:
            return 0

        # 0. Ensure collection exists in Qdrant (in case Qdrant was wiped/restarted)
        self._ensure_collection()

        # 1. Check for exact existing vectors by content hash in Qdrant
        block_id_map = {self.generate_point_id(b): b for b in blocks}
        existing_ids = self.get_existing_point_ids(list(block_id_map.keys()))

        blocks_to_index = [b for pid, b in block_id_map.items() if pid not in existing_ids]

        if not blocks_to_index:
            import sys
            sys.stderr.write(f"[+] Qdrant Cache Hit: All {len(blocks)} AST blocks already vectorized. 0ms re-indexing required.\n")
            return len(blocks)

        import sys
        sys.stderr.write(f"[+] Qdrant Incremental Indexing: {len(existing_ids)} cached, {len(blocks_to_index)} new/modified blocks to vectorize...\n")

        total_indexed = 0
        total_to_index = len(blocks_to_index)

        for i in range(0, total_to_index, batch_size):
            batch = blocks_to_index[i : i + batch_size]
            texts = [b.get("content", "") for b in batch]
            embeddings = list(self.embedder.embed(texts))

            points = []
            for b, emb in zip(batch, embeddings):
                points.append(
                    PointStruct(
                        id=self.generate_point_id(b),
                        vector=emb.tolist(),
                        payload={
                            "org_id": self.org_id,
                            "dept_id": self.dept_id,
                            "repo_id": self.repo_id,
                            "file_path": b.get("file_path", "unknown"),
                            "name": b.get("name", "anonymous"),
                            "type": b.get("type", "unknown"),
                            "start_line": b.get("start_line", 0),
                            "end_line": b.get("end_line", 0),
                            "content": b.get("content", "")
                        }
                    )
                )

            self.client.upsert(collection_name=self.collection_name, points=points)
            total_indexed += len(batch)
            sys.stderr.write(f"[+] Qdrant Vectorizing: {total_indexed}/{total_to_index} new blocks indexed ({int(total_indexed / total_to_index * 100)}%)...\n")

        return len(existing_ids) + total_indexed

    def search_code(
        self,
        query: str,
        top_k: int = 3,
        score_threshold: float = 0.35,
        federated_collections: Optional[List[str]] = None
    ) -> str:
        """
        Searches target collection and optional federated shared platform collections.
        """
        query_vector = list(self.embedder.embed([query]))[0].tolist()
        collections_to_search = [self.collection_name]
        
        if federated_collections:
            for fc in federated_collections:
                clean_fc = sanitize_collection_name(fc)
                if self.client.collection_exists(clean_fc) and clean_fc not in collections_to_search:
                    collections_to_search.append(clean_fc)

        all_matches = []
        for col in collections_to_search:
            try:
                results = self.client.query_points(
                    collection_name=col,
                    query=query_vector,
                    limit=top_k,
                    score_threshold=score_threshold
                ).points
                all_matches.extend(results)
            except Exception:
                continue

        # Sort combined matches by descending similarity score
        all_matches.sort(key=lambda x: x.score, reverse=True)
        top_matches = all_matches[:top_k]

        if not top_matches:
            return f"[INFO] No relevant code found for query: '{query}' in {self.dept_id}/{self.repo_id}"

        output = f"--- Vector Search Results for '{query}' [{self.dept_id}/{self.repo_id}] ---\n"
        for r in top_matches:
            p = r.payload or {}
            file_path = p.get("file_path", "unknown")
            start_line = p.get("start_line", 0)
            end_line = p.get("end_line", 0)
            name = p.get("name", "anonymous")
            block_type = p.get("type", "unknown")
            content = p.get("content", "")
            match_repo = p.get("repo_id", self.repo_id)

            output += (
                f"\n[Candidate Match (Score: {r.score:.2f}) | Repo: {match_repo}]\n"
                f"File: {file_path} (Lines {start_line}-{end_line})\n"
                f"Block Name: '{name}' ({block_type})\n"
                f"Content:\n{content}\n"
            )

        return output

    def search_raw_points(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.25,
        repo_filter: Optional[List[str]] = None,
        federated_collections: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Returns structured block dicts with similarity scores, supporting repo_filter for ACL.
        """
        query_vector = list(self.embedder.embed([query]))[0].tolist()
        collections_to_search = [self.collection_name]

        if federated_collections:
            for fc in federated_collections:
                clean_fc = sanitize_collection_name(fc)
                if self.client.collection_exists(clean_fc) and clean_fc not in collections_to_search:
                    collections_to_search.append(clean_fc)

        qdrant_filter = None
        if repo_filter:
            qdrant_filter = Filter(
                must=[
                    FieldCondition(
                        key="repo_id",
                        match=MatchAny(any=repo_filter)
                    )
                ]
            )

        all_matches = []
        for col in collections_to_search:
            try:
                results = self.client.query_points(
                    collection_name=col,
                    query=query_vector,
                    query_filter=qdrant_filter,
                    limit=top_k,
                    score_threshold=score_threshold
                ).points
                all_matches.extend(results)
            except Exception:
                continue

        all_matches.sort(key=lambda x: x.score, reverse=True)
        top_matches = all_matches[:top_k]

        structured = []
        for r in top_matches:
            p = r.payload or {}
            structured.append({
                "name": p.get("name", "anonymous"),
                "file_path": p.get("file_path", "unknown"),
                "start_line": p.get("start_line", 0),
                "end_line": p.get("end_line", 0),
                "type": p.get("type", "unknown"),
                "content": p.get("content", ""),
                "score": float(r.score),
                "repo_id": p.get("repo_id", self.repo_id),
                "retrieval_method": "dense_vector"
            })
        return structured
