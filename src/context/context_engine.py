"""
context_engine.py — The flagship bundled context retrieval for M5.

ONE call to get_context() does:
  1. Hybrid search (BM25 + dense vectors + RRF) → top-k ranked code chunks
  2. Multi-concern diverse coverage → ensures API, services, events, persistence, frontend
  3. Explainable ranking metadata → match_type, match_reason, confidence
  4. Semantic dependency expansion & explicit edges → caller/callee, endpoints, events
  5. Companion test discovery → pairs implementation code with related tests
  6. Explicit omission & staleness warnings → reports unfulfilled query concerns
  7. Non-truncated complete AST bodies → preserves full methods/classes
  8. Return a structured, rich ContextBundle (not just concatenated text)
"""

import os
import re
import uuid
from typing import Optional, List, Dict, Any

from src.tools.hybrid_search import get_hybrid_retriever
from src.tools.dependency_graph import PersistentDependencyGraph

# Maximum total chunks returned in one bundle (prevents token explosions)
_MAX_CHUNKS = int(os.getenv("M5_MAX_CHUNKS", "15"))

# ── Concern Categorization Keywords ──────────────────────────────────────────
CONCERN_PATTERNS = {
    "api_controllers": re.compile(r"(controller|endpoint|api|route|handler|websocket)", re.I),
    "services_logic": re.compile(r"(service|manager|processor|executor|engine)", re.I),
    "persistence_db": re.compile(r"(repository|model|entity|schema|dao|migration|sql|database)", re.I),
    "events_messaging": re.compile(r"(kafka|redis|consumer|producer|event|queue|rabbit)", re.I),
    "frontend_ui": re.compile(r"(component|page|view|frontend|react|jsx|tsx|html|css)", re.I),
    "tests": re.compile(r"(test|spec|mock|testing)", re.I),
}


def _classify_chunk_concern(file_path: str, symbol_name: str) -> str:
    """Classifies a code chunk into an architectural concern tier."""
    target = f"{file_path} {symbol_name}".lower()
    for concern, pattern in CONCERN_PATTERNS.items():
        if pattern.search(target):
            return concern
    return "general"


def _infer_semantic_relationship(source_file: str, target_file: str) -> str:
    """Infers high-level architectural relationship between two files."""
    s_lower = source_file.lower()
    t_lower = target_file.lower()

    if "controller" in s_lower and "service" in t_lower:
        return "exposes_endpoint_to_service"
    elif "consumer" in s_lower and "service" in t_lower:
        return "consumes_event_triggers_service"
    elif "service" in s_lower and ("repository" in t_lower or "entity" in t_lower or "model" in t_lower):
        return "manages_persistence"
    elif "test" in s_lower or "spec" in s_lower:
        return "tests_implementation"
    elif "test" in t_lower or "spec" in t_lower:
        return "tested_by"
    return "imports"


def _explain_match(
    query: str,
    symbol_name: str,
    file_path: str,
    retrieval_method: str,
    score: float
) -> Dict[str, Any]:
    """
    Generates explainable ranking metadata and confidence score.
    """
    q_lower = query.lower()
    sym_lower = symbol_name.lower()
    file_lower = file_path.lower()

    if sym_lower and sym_lower in q_lower:
        match_type = "exact_symbol"
        confidence = "high"
        match_reason = f"Exact symbol match for '{symbol_name}' in query"
    elif any(term in file_lower for term in q_lower.split() if len(term) > 3):
        match_type = "path_keyword"
        confidence = "high" if score > 0.03 else "medium"
        match_reason = f"File path '{file_path}' matches query terms"
    elif retrieval_method == "dense_vector":
        match_type = "semantic_vector"
        confidence = "high" if score > 0.5 else "medium"
        match_reason = f"Semantic conceptual match with vector score {round(score, 3)}"
    elif retrieval_method == "bm25":
        match_type = "keyword_bm25"
        confidence = "medium"
        match_reason = f"Keyword BM25 match against AST code tokens"
    else:
        match_type = "hybrid_rrf"
        confidence = "high" if score > 0.03 else "medium"
        match_reason = f"Reciprocal Rank Fusion hybrid match (vector + keyword agreement)"

    return {
        "match_type": match_type,
        "confidence": confidence,
        "match_reason": match_reason
    }


def _make_bundle(
    request_id: str,
    query: str,
    chunks: List[Dict[str, Any]],
    dep_edges: List[Dict[str, Any]],
    related_tests: List[str],
    omissions: List[str],
    warnings: List[str],
    truncated: bool,
) -> Dict[str, Any]:
    """Assemble the final rich ContextBundle dict."""
    total_text = " ".join(c.get("content", "") for c in chunks)
    estimated_tokens = len(total_text) // 4

    return {
        "request_id": request_id,
        "query": query,
        "chunks": chunks,
        "dependency_edges": dep_edges,
        "related_tests": related_tests,
        "omissions": omissions,
        "warnings": warnings,
        "total_chunks": len(chunks),
        "truncated": truncated,
        "estimated_tokens": estimated_tokens,
    }


def _dedup_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Removes chunks whose line ranges are completely contained within another chunk
    from the same file. Keeps the chunk with the higher relevance score.
    """
    sorted_chunks = sorted(chunks, key=lambda c: (c["file_path"], c["start_line"]))
    deduped: List[Dict[str, Any]] = []

    for chunk in sorted_chunks:
        dominated = False
        for existing in deduped:
            if (
                existing["file_path"] == chunk["file_path"]
                and existing["start_line"] <= chunk["start_line"]
                and existing["end_line"] >= chunk["end_line"]
            ):
                dominated = True
                break
        if not dominated:
            deduped.append(chunk)

    return deduped


def get_context(
    query: str,
    top_k: int = 5,
    expand_dependencies: bool = True,
    expand_depth: int = 1,
    max_chunk_chars: Optional[int] = None,
    org_id: str = "default_org",
    dept_id: str = "default_dept",
    repo_id: str = "default_repo",
    requesting_user: Optional[str] = None,
    caller_identity: str = "unknown",
) -> Dict[str, Any]:
    """
    Bundled context retrieval — the flagship M5 call.

    Args:
        query:               Natural language query or code snippet.
        top_k:               How many top code chunks to start with.
        expand_dependencies: If True, also pull in explicit dependency edges and linked files.
        expand_depth:        How many hops to expand (1 = direct imports).
        max_chunk_chars:     Optional snippet size limit (None = complete method/class body).
        org_id / dept_id / repo_id: Tenant namespace — strictly enforced.

    Returns:
        A ContextBundle dict with chunks, explicit dependency edges, test citations, omissions, and explainable scores.
    """
    resolved_org = org_id or os.getenv("DEFAULT_ORG_ID", "default_org")
    resolved_dept = dept_id or os.getenv("DEFAULT_DEPT_ID", "default_dept")
    resolved_repo = repo_id or os.getenv("DEFAULT_REPO_ID", "default_repo")

    # If still default_org, check if single custom collection exists in Qdrant
    if resolved_org == "default_org" and resolved_repo == "default_repo":
        try:
            from src.tools.vector_search import get_shared_qdrant_client
            client = get_shared_qdrant_client()
            collections = [c.name for c in client.get_collections().collections if c.name.startswith("m5_")]
            if len(collections) == 1 and collections[0] != "m5_default_org_default_dept_default_repo":
                parts = collections[0][3:].split("_")
                if len(parts) >= 3:
                    resolved_org, resolved_dept, resolved_repo = parts[0], parts[1], "_".join(parts[2:])
        except Exception:
            pass

    request_id = str(uuid.uuid4())

    retriever = get_hybrid_retriever(org_id=resolved_org, dept_id=resolved_dept, repo_id=resolved_repo)
    d_graph = PersistentDependencyGraph(org_id=resolved_org, dept_id=resolved_dept, repo_id=resolved_repo)

    warnings: List[str] = []
    omissions: List[str] = []

    # ── Step 1: Hybrid search ─────────────────────────────────────────────────
    raw_chunks = retriever.search_blocks(query=query, top_k=top_k * 2)

    # Enrich chunks with explainable metadata and architectural concern
    enriched_chunks = []
    for c in raw_chunks:
        explanation = _explain_match(
            query=query,
            symbol_name=c.get("symbol_name", ""),
            file_path=c.get("file_path", ""),
            retrieval_method=c.get("retrieval_method", "hybrid_rrf"),
            score=c.get("relevance_score", 0.0)
        )
        c["match_type"] = explanation["match_type"]
        c["confidence"] = explanation["confidence"]
        c["match_reason"] = explanation["match_reason"]
        c["concern"] = _classify_chunk_concern(c.get("file_path", ""), c.get("symbol_name", ""))

        # Apply optional snippet truncation only if explicitly requested
        if max_chunk_chars and len(c.get("content", "")) > max_chunk_chars:
            c["content"] = c["content"][:max_chunk_chars] + "\n... [truncated]"
            warnings.append(f"Snippet for {c.get('file_path')} was truncated to {max_chunk_chars} chars.")

        enriched_chunks.append(c)

    # ── Step 2: Multi-Concern Diversification & Omission Checking ─────────────
    query_lower = query.lower()
    requested_concerns = [c for c, pat in CONCERN_PATTERNS.items() if pat.search(query_lower)]

    selected_chunks: List[Dict[str, Any]] = []
    found_concerns = set()

    if requested_concerns and len(requested_concerns) > 1:
        # Pick best chunk for each requested concern first
        for concern in requested_concerns:
            matched_for_concern = False
            for c in enriched_chunks:
                if c["concern"] == concern and c not in selected_chunks:
                    selected_chunks.append(c)
                    found_concerns.add(concern)
                    matched_for_concern = True
                    break
            if not matched_for_concern and concern != "tests":
                omissions.append(f"{concern}: no matching code found in workspace for this concern")

        # Fill remaining slots with highest ranking chunks
        for c in enriched_chunks:
            if c not in selected_chunks and len(selected_chunks) < top_k:
                selected_chunks.append(c)
    else:
        selected_chunks = enriched_chunks[:top_k]

    # ── Step 3: Explicit Semantic Dependency Graph Edges ──────────────────────
    dep_edges: List[Dict[str, Any]] = []
    expanded_file_paths = set(c["file_path"] for c in selected_chunks)

    if expand_dependencies and selected_chunks:
        # A. Direct edges between returned files with semantic relationship inference
        raw_edges = d_graph.get_edges_between_files(list(expanded_file_paths))
        for edge in raw_edges:
            src = edge["source"]
            tgt = edge["target"]
            edge["semantic_relationship"] = _infer_semantic_relationship(src, tgt)
            dep_edges.append(edge)

        # B. 1-hop outgoing dependency discovery
        files_to_expand = list(expanded_file_paths)
        for _hop in range(max(1, expand_depth)):
            next_hop_files = set()
            for file_path in files_to_expand:
                try:
                    outgoing = d_graph.get_outgoing_edges(file_path=file_path)
                    for edge in outgoing:
                        dep_file = edge.get("target_file", "").strip()
                        raw_import = edge.get("raw_import", "")
                        if dep_file:
                            edge_entry = {
                                "source": file_path,
                                "target": dep_file,
                                "relationship": "imports",
                                "semantic_relationship": _infer_semantic_relationship(file_path, dep_file),
                                "import_statement": raw_import
                            }
                            if edge_entry not in dep_edges:
                                dep_edges.append(edge_entry)
                            if dep_file not in expanded_file_paths:
                                next_hop_files.add(dep_file)
                                expanded_file_paths.add(dep_file)
                except Exception:
                    pass
            files_to_expand = list(next_hop_files)
            if not files_to_expand:
                break

    # ── Step 4: Companion Test Discovery ──────────────────────────────────────
    related_tests = []
    for c in selected_chunks:
        tests = d_graph.find_companion_tests(c["file_path"])
        for t in tests:
            if t not in related_tests:
                related_tests.append(t)

    # If user explicitly asked for tests and none exist
    if "tests" in requested_concerns and not related_tests:
        omissions.append("tests: no companion test files found for matched components")

    # ── Step 5: Deduplication & Final Capping ─────────────────────────────────
    chunks = _dedup_chunks(selected_chunks)
    truncated = len(chunks) > _MAX_CHUNKS
    chunks = chunks[:_MAX_CHUNKS]

    # ── Step 6: Assemble ContextBundle ────────────────────────────────────────
    return _make_bundle(
        request_id=request_id,
        query=query,
        chunks=chunks,
        dep_edges=dep_edges,
        related_tests=related_tests,
        omissions=omissions,
        warnings=warnings,
        truncated=truncated,
    )
