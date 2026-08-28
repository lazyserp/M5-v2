import gzip
import json
import math
import os
import re
import threading
from typing import List, Dict, Any, Optional, Tuple
from src.tools.vector_search import VectorStore


def _bm25_cache_dir() -> str:
    """
    Returns the directory where BM25 block snapshots are saved.
    Uses the OS app-data folder so blocks never end up inside the Git working tree.
    """
    override = os.getenv("M5_BM25_CACHE_DIR", "")
    if override:
        path = override
    else:
        # Windows: %LOCALAPPDATA%\M5\bm25
        # macOS/Linux: ~/.local/share/m5/bm25
        if os.name == "nt":
            base = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
        else:
            base = os.path.join(os.path.expanduser("~"), ".local", "share")
        path = os.path.join(base, "M5", "bm25")
    os.makedirs(path, exist_ok=True)
    return path


def _bm25_cache_path(org_id: str, dept_id: str, repo_id: str) -> str:
    """Returns the full path for a tenant's BM25 block snapshot file."""
    safe = f"{org_id}__{dept_id}__{repo_id}".replace("/", "_").replace("\\", "_")
    return os.path.join(_bm25_cache_dir(), f"{safe}.blocks.json.gz")


def _save_bm25_blocks(org_id: str, dept_id: str, repo_id: str, blocks: List[Dict[str, Any]]) -> None:
    """
    Saves the indexed code blocks to a gzip JSON file so BM25 can be restored after restarts.
    Only stores the fields BM25 actually needs (name, file_path, content) to keep the file small.
    Source code content is already on the user's disk — we're just saving the extracted text.
    """
    slim_blocks = [
        {
            "name": b.get("name", ""),
            "file_path": b.get("file_path", ""),
            "content": b.get("content", ""),
            "start_line": b.get("start_line", 0),
            "end_line": b.get("end_line", 0),
            "type": b.get("type", ""),
            "org_id": b.get("org_id", org_id),
            "dept_id": b.get("dept_id", dept_id),
            "repo_id": b.get("repo_id", repo_id),
        }
        for b in blocks
    ]
    cache_path = _bm25_cache_path(org_id, dept_id, repo_id)
    tmp = cache_path + ".tmp"
    try:
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(slim_blocks, f)
        os.replace(tmp, cache_path)
    except Exception:
        pass  # Never crash the indexer over a cache write failure


def _load_bm25_blocks(org_id: str, dept_id: str, repo_id: str) -> List[Dict[str, Any]]:
    """Loads previously saved BM25 blocks from disk. Returns [] if none exist."""
    cache_path = _bm25_cache_path(org_id, dept_id, repo_id)
    if not os.path.exists(cache_path):
        return []
    try:
        with gzip.open(cache_path, "rt", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

class CodeTokenizer:
    """
    Code-aware sub-tokenizer that splits identifiers on camelCase, snake_case,
    periods, and punctuation to match both exact tokens and component keywords.
    """
    @staticmethod
    def tokenize(text: str) -> List[str]:
        if not text:
            return []
        
        # 1. Split on non-alphanumeric characters (keep alphanumeric tokens)
        raw_tokens = re.findall(r"[a-zA-Z0-9_]+", text)
        final_tokens = []

        for token in raw_tokens:
            lower_token = token.lower()
            final_tokens.append(lower_token)

            # 2. Split snake_case: 'process_shopping_cart' -> ['process', 'shopping', 'cart']
            if "_" in token:
                subparts = [p.lower() for p in token.split("_") if p]
                final_tokens.extend(subparts)

            # 3. Split camelCase / PascalCase: 'PaymentIntentValidator' -> ['Payment', 'Intent', 'Validator']
            camel_parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\W|$)|\d+", token)
            if len(camel_parts) > 1:
                final_tokens.extend([p.lower() for p in camel_parts if p])

        return final_tokens

class BM25Index:
    """
    In-memory BM25Okapi sparse retrieval engine for code blocks.
    Zero external dependencies, deterministic, sub-millisecond keyword lookup.
    """
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus: List[Dict[str, Any]] = []
        self.doc_lengths: List[int] = []
        self.avg_doc_length: float = 0.0
        self.doc_freqs: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.term_freqs: List[Dict[str, int]] = []

    def index_blocks(self, blocks: List[Dict[str, Any]]) -> None:
        self.corpus = blocks
        self.doc_lengths = []
        self.term_freqs = []
        self.doc_freqs = {}

        total_length = 0
        for block in blocks:
            text = f"{block.get('name', '')} {block.get('file_path', '')} {block.get('content', '')}"
            tokens = CodeTokenizer.tokenize(text)
            doc_len = len(tokens)
            self.doc_lengths.append(doc_len)
            total_length += doc_len

            freqs: Dict[str, int] = {}
            for t in tokens:
                freqs[t] = freqs.get(t, 0) + 1
            self.term_freqs.append(freqs)

            for t in freqs.keys():
                self.doc_freqs[t] = self.doc_freqs.get(t, 0) + 1

        n_docs = len(blocks)
        self.avg_doc_length = total_length / n_docs if n_docs > 0 else 0.0

        # Calculate IDF with smoothing
        self.idf = {}
        for term, df in self.doc_freqs.items():
            self.idf[term] = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))

    def query(self, query_text: str, top_k: int = 10) -> List[Tuple[Dict[str, Any], float]]:
        if not self.corpus:
            return []

        query_tokens = CodeTokenizer.tokenize(query_text)
        if not query_tokens:
            return []

        scores = []
        for i, (doc, doc_len, freqs) in enumerate(zip(self.corpus, self.doc_lengths, self.term_freqs)):
            score = 0.0
            for term in query_tokens:
                if term not in freqs:
                    continue
                tf = freqs[term]
                idf = self.idf.get(term, 0.0)
                denom = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / (self.avg_doc_length or 1.0)))
                score += idf * (tf * (self.k1 + 1.0)) / (denom or 1.0)
            
            if score > 0.0:
                scores.append((doc, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

_RETRIEVER_CACHE: Dict[str, "HybridRetriever"] = {}
_RETRIEVER_LOCK = threading.Lock()

def get_hybrid_retriever(
    org_id: str = "default_org",
    dept_id: str = "default_dept",
    repo_id: str = "default_repo",
    storage_path: str = "./qdrant_storage",
    in_memory: bool = False
) -> "HybridRetriever":
    """
    Returns a cached HybridRetriever singleton for the tenant namespace.
    Reuses in-memory BM25 indexes and vector connections across queries.
    """
    key = f"{org_id}:{dept_id}:{repo_id}:{storage_path}:{in_memory}"
    with _RETRIEVER_LOCK:
        if key not in _RETRIEVER_CACHE:
            _RETRIEVER_CACHE[key] = HybridRetriever(
                org_id=org_id,
                dept_id=dept_id,
                repo_id=repo_id,
                storage_path=storage_path,
                in_memory=in_memory
            )
        return _RETRIEVER_CACHE[key]

class HybridRetriever:
    """
    Combines dense semantic vector retrieval (Qdrant) and sparse keyword retrieval (BM25)
    using Reciprocal Rank Fusion (RRF).

    BM25 persistence:
    On __init__, if a saved block snapshot exists for this tenant namespace, it is loaded
    and the BM25 index is rebuilt from it (~200ms). This means keyword search works
    immediately after a server restart without needing to re-parse the whole codebase.
    """
    def __init__(
        self,
        org_id: str = "default_org",
        dept_id: str = "default_dept",
        repo_id: str = "default_repo",
        storage_path: str = "./qdrant_storage",
        in_memory: bool = False
    ):
        self.org_id = org_id
        self.dept_id = dept_id
        self.repo_id = repo_id
        self.vector_store = VectorStore(
            org_id=org_id,
            dept_id=dept_id,
            repo_id=repo_id,
            storage_path=storage_path,
            in_memory=in_memory
        )
        self.bm25_index = BM25Index()
        self.indexed_blocks: List[Dict[str, Any]] = []

        # Restore BM25 from disk if a snapshot exists (survives restarts)
        saved_blocks = _load_bm25_blocks(org_id, dept_id, repo_id)
        if saved_blocks:
            self.indexed_blocks = saved_blocks
            self.bm25_index.index_blocks(saved_blocks)

    def index_blocks(self, blocks: List[Dict[str, Any]], batch_size: int = 64) -> int:
        """
        Indexes blocks into both Dense Vector Store (Qdrant) and BM25 Sparse Index.
        Saves the updated block list to disk so BM25 survives the next restart.
        """
        self.indexed_blocks.extend(blocks)
        self.bm25_index.index_blocks(self.indexed_blocks)
        # Persist to disk — makes BM25 restart-proof
        _save_bm25_blocks(self.org_id, self.dept_id, self.repo_id, self.indexed_blocks)
        return self.vector_store.index_blocks(blocks, batch_size=batch_size)

    def search_blocks(
        self,
        query: str,
        top_k: int = 5,
        rrf_k: int = 60,
        score_threshold: float = 0.20,
        federated_collections: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Returns structured list of top-k code chunks ranked via Reciprocal Rank Fusion (RRF).
        """
        # 1. Retrieve Dense Candidates from Qdrant
        query_vector = list(self.vector_store.embedder.embed([query]))[0].tolist()
        try:
            dense_results = self.vector_store.client.query_points(
                collection_name=self.vector_store.collection_name,
                query=query_vector,
                limit=top_k * 3,
                score_threshold=score_threshold
            ).points
        except Exception:
            dense_results = []

        # 2. Retrieve Sparse Candidates from BM25
        bm25_results = self.bm25_index.query(query, top_k=top_k * 3)

        # 3. Reciprocal Rank Fusion (RRF)
        fusion_map: Dict[str, Dict[str, Any]] = {}

        for rank, r in enumerate(dense_results, start=1):
            p = r.payload or {}
            sig = f"{p.get('file_path')}:{p.get('start_line')}:{p.get('end_line')}:{p.get('name')}"
            if sig not in fusion_map:
                fusion_map[sig] = {
                    "data": p,
                    "rrf_score": 0.0,
                    "dense_rank": rank,
                    "bm25_rank": None,
                    "dense_score": r.score
                }
            fusion_map[sig]["rrf_score"] += 1.0 / (rrf_k + rank)

        for rank, (doc, bm25_score) in enumerate(bm25_results, start=1):
            sig = f"{doc.get('file_path')}:{doc.get('start_line')}:{doc.get('end_line')}:{doc.get('name')}"
            if sig not in fusion_map:
                fusion_map[sig] = {
                    "data": doc,
                    "rrf_score": 0.0,
                    "dense_rank": None,
                    "bm25_rank": rank,
                    "dense_score": 0.0
                }
            fusion_map[sig]["bm25_rank"] = rank
            fusion_map[sig]["rrf_score"] += 1.0 / (rrf_k + rank)

        # 4. Sort candidates by RRF Score
        ranked_candidates = list(fusion_map.values())
        ranked_candidates.sort(key=lambda x: x["rrf_score"], reverse=True)
        top_candidates = ranked_candidates[:top_k]

        chunks = []
        for item in top_candidates:
            p = item["data"]
            chunks.append({
                "file_path": p.get("file_path", "unknown"),
                "start_line": p.get("start_line", 0),
                "end_line": p.get("end_line", 0),
                "symbol_name": p.get("name", "anonymous"),
                "symbol_type": p.get("type", "unknown"),
                "relevance_score": round(item["rrf_score"], 4),
                "retrieval_method": "hybrid_rrf",
                "content": p.get("content", "")
            })

        return chunks

    def search_code(
        self,
        query: str,
        top_k: int = 3,
        rrf_k: int = 60,
        score_threshold: float = 0.25,
        federated_collections: Optional[List[str]] = None
    ) -> str:
        """
        Executes dense and sparse queries, computes Reciprocal Rank Fusion (RRF),
        and formats the highest-confidence grounded observations as formatted text.
        """
        chunks = self.search_blocks(
            query=query,
            top_k=top_k,
            rrf_k=rrf_k,
            score_threshold=score_threshold,
            federated_collections=federated_collections
        )

        if not chunks:
            return f"[INFO] No relevant code found for query: '{query}' in {self.dept_id}/{self.repo_id}"

        output = f"--- Hybrid Search Results for '{query}' [{self.dept_id}/{self.repo_id}] ---\n"
        for c in chunks:
            output += (
                f"\n[Match (RRF Score: {c['relevance_score']})]\n"
                f"File: {c['file_path']} (Lines {c['start_line']}-{c['end_line']})\n"
                f"Block Name: '{c['symbol_name']}' ({c['symbol_type']})\n"
                f"Content:\n{c['content']}\n"
            )

        return output
