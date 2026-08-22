import os
import uuid
import hashlib
import re
import threading
from typing import Optional, List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from fastembed import TextEmbedding
from src.config import QDRANT_URL, QDRANT_API_KEY

_CLIENT_CACHE: Dict[str, QdrantClient] = {}
_CLIENT_LOCK = threading.Lock()

def sanitize_collection_name(name: str) -> str:
    """Sanitizes names into valid Qdrant collection identifiers."""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", name.lower().strip())
    return cleaned if cleaned else "m5_default"

def get_shared_qdrant_client(
    storage_path: str = "./qdrant_storage",
    url: Optional[str] = None,
    api_key: Optional[str] = None,
    in_memory: bool = False
) -> QdrantClient:
    """
    Returns a shared Qdrant client, managing singletons for embedded local disk storage
    to prevent file lock contention across threads and workers.
    """
    if in_memory:
        return QdrantClient(location=":memory:")

    target_url = url or QDRANT_URL
    target_api_key = api_key or QDRANT_API_KEY

    if target_url:
        try:
            client = QdrantClient(url=target_url, api_key=target_api_key, timeout=1)
            client.get_collections() # Active health probe
            return client
        except Exception:
            pass

    # Thread-safe client reuse for local disk storage
    with _CLIENT_LOCK:
        norm_path = os.path.abspath(storage_path)
        if norm_path not in _CLIENT_CACHE:
            _CLIENT_CACHE[norm_path] = QdrantClient(path=norm_path)
        return _CLIENT_CACHE[norm_path]

class VectorStore:
    """
    Enterprise Multi-Tenant Vector Store for Qdrant.
    Provides strict departmental and repository isolation with zero cross-tenant leakage.
    """
    def __init__(
        self,
        org_id: str = "default_org",
        dept_id: str = "default_dept",
        repo_id: str = "default_repo",
        storage_path: str = "./qdrant_storage",
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
        self.embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

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

    def index_blocks(self, blocks: list[dict], batch_size: int = 64) -> int:
        if not blocks:
            return 0

        total_indexed = 0

        for i in range(0, len(blocks), batch_size):
            batch = blocks[i : i + batch_size]
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

        return total_indexed

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
