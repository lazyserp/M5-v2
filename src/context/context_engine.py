"""
context_engine.py — The flagship bundled context retrieval for M5.

ONE call to get_context() does:
  1. Exact AST symbol boosting → exact function/class names strictly rank #1
  2. Hybrid search (BM25 + dense vectors + RRF) → top-k ranked code chunks
  3. Multi-concern diverse coverage → ensures API, services, events, persistence, frontend
  4. Multi-hop end-to-end call path tracing (entry points -> targets -> terminations)
  5. Completeness check & flow diagram verification
  6. Transparent token savings metrics (retrieved tokens vs whole-file reads)
  7. Non-truncated complete AST bodies + concise structured summaries
  8. Companion test discovery & explicit omission warnings
  9. Auto-healing empty or stale repository indexes
"""

import os
import re
import uuid
import time
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
    score: float,
    is_exact_ast: bool = False
) -> Dict[str, Any]:
    """
    Generates explainable ranking metadata and confidence score.
    """
    q_lower = query.lower()
    sym_lower = symbol_name.lower()
    file_lower = file_path.lower()

    if is_exact_ast or (sym_lower and sym_lower in q_lower):
        match_type = "exact_symbol"
        confidence = "very_high"
        match_reason = f"Exact AST symbol definition match for '{symbol_name}'"
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


def _trace_execution_path(
    d_graph: PersistentDependencyGraph,
    primary_symbols: List[Dict[str, Any]],
    repo_filter: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Traces multi-hop call graph: upstream callers (up to root entry points)
    and downstream callees (down to leaf functions/storage).
    Returns structured call path, ASCII flow diagram, and completeness check.
    """
    if not primary_symbols:
        return {
            "execution_flow": [],
            "flow_diagram": "Direct / No AST symbol match",
            "completeness_check": {
                "fully_traced": False,
                "entry_points": [],
                "target_symbols": [],
                "terminations": [],
                "unresolved_calls": ["No primary symbol detected to trace"]
            }
        }

    entry_points = []
    target_names = [s.get("symbol_name") for s in primary_symbols if s.get("symbol_name")]
    terminations = []
    unresolved_calls = []
    call_steps = []

    entry_pattern = re.compile(r"(route|endpoint|controller|handler|main|cli|job|task|listener|event|run)", re.I)

    for sym_data in primary_symbols[:3]:
        name = sym_data.get("symbol_name", "")
        f_path = sym_data.get("file_path", "")
        if not name or name == "anonymous":
            continue

        # 1. Upstream Trace (Callers)
        upstream_chain = []
        curr_callers = d_graph.db.find_callers(name, limit=5, repo_filter=repo_filter)
        for caller in curr_callers:
            c_name = caller.get("source_symbol")
            c_file = caller.get("source_file", "")
            if c_name:
                upstream_chain.append(f"{c_file}:{c_name}")
                if entry_pattern.search(f"{c_file} {c_name}"):
                    entry_points.append(f"{c_file} ({c_name})")
                else:
                    # Check if caller is top-level (no upstream callers)
                    next_callers = d_graph.db.find_callers(c_name, limit=1, repo_filter=repo_filter)
                    if not next_callers:
                        entry_points.append(f"{c_file} ({c_name})")

        # 2. Downstream Trace (Callees)
        downstream_chain = []
        curr_callees = d_graph.db.find_callees(f_path, name, repo_filter=repo_filter)
        for callee in curr_callees:
            t_name = callee.get("target_symbol")
            t_file = callee.get("target_file", "")
            if t_name:
                downstream_chain.append(f"{t_file or 'external'}:{t_name}")
                t_defs = d_graph.db.find_symbol(t_name, exact=True, limit=1, repo_filter=repo_filter)
                if t_defs:
                    next_callees = d_graph.db.find_callees(t_defs[0].get("file_path", ""), t_name, repo_filter=repo_filter)
                    if not next_callees:
                        terminations.append(f"{t_defs[0].get('file_path')} ({t_name})")
                else:
                    unresolved_calls.append(t_name)
                    terminations.append(f"external/stdlib ({t_name})")

        call_steps.append({
            "target": f"{f_path}:{sym_data.get('start_line')}-{sym_data.get('end_line')} ({name})",
            "upstream_callers": upstream_chain,
            "downstream_callees": downstream_chain
        })

    entry_points = list(dict.fromkeys(entry_points))
    terminations = list(dict.fromkeys(terminations))
    unresolved_calls = list(dict.fromkeys(unresolved_calls))

    diagram_parts = []
    if entry_points:
        diagram_parts.append(f"Entry: [{', '.join(str(ep) for ep in entry_points[:2] if ep)}]")
    else:
        diagram_parts.append("Entry: [Direct / API / Test]")
    valid_targets = [str(t) for t in target_names if t]
    diagram_parts.append(f"Target: [{', '.join(valid_targets[:2])}]")
    if terminations:
        diagram_parts.append(f"Leaves: [{', '.join(str(tm) for tm in terminations[:3] if tm)}]")
    else:
        diagram_parts.append("Leaves: [Local Return]")

    flow_diagram = " --> ".join(diagram_parts)
    is_complete = len(valid_targets) > 0 and len(unresolved_calls) == 0

    return {
        "execution_flow": call_steps,
        "flow_diagram": flow_diagram,
        "completeness_check": {
            "fully_traced": is_complete,
            "entry_points": entry_points,
            "target_symbols": valid_targets,
            "terminations": terminations,
            "unresolved_calls": unresolved_calls
        }
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
    elapsed_ms: float = 0.0,
    trace_info: Optional[Dict[str, Any]] = None,
    auto_reindexed: bool = False,
) -> Dict[str, Any]:
    """Assemble the final rich ContextBundle dict with token savings metrics and completeness checks."""
    trace = trace_info or {}

    # Calculate token metrics
    total_chars = sum(len(c.get("content", "")) for c in chunks)
    retrieved_tokens = max(1, total_chars // 4)

    total_file_chars = 0
    unique_files: List[str] = [str(c.get("file_path")) for c in chunks if c.get("file_path")]
    for fpath in set(unique_files):
        if not fpath:
            continue
        try:
            norm_p = os.path.abspath(fpath)
            if os.path.exists(norm_p):
                total_file_chars += os.path.getsize(norm_p)
            elif os.path.exists(fpath):
                total_file_chars += os.path.getsize(fpath)
        except Exception:
            pass

    whole_files_tokens = max(retrieved_tokens, total_file_chars // 4)
    tokens_saved = max(0, whole_files_tokens - retrieved_tokens)
    savings_pct = round((tokens_saved / whole_files_tokens) * 100, 1) if whole_files_tokens > 0 else 0.0

    has_exact = any(c.get("match_type") == "exact_symbol" for c in chunks)
    has_high_rel = any(c.get("relevance_score", 0.0) >= 0.8 for c in chunks)
    if has_exact:
        conf_score = 0.96
        conf_rating = "VERY_HIGH"
        precision = "exact_ast_symbol"
    elif has_high_rel:
        conf_score = 0.88
        conf_rating = "HIGH"
        precision = "hybrid_rrf_high"
    else:
        conf_score = 0.75
        conf_rating = "MEDIUM"
        precision = "semantic_vector"

    metrics = {
        "retrieved_tokens": retrieved_tokens,
        "whole_files_tokens": whole_files_tokens,
        "tokens_saved": tokens_saved,
        "token_savings_percent": savings_pct,
        "confidence_score": conf_score,
        "confidence_rating": conf_rating,
        "search_precision": precision,
        "omissions_count": len(omissions)
    }

    return {
        "request_id": request_id,
        "query": query,
        "elapsed_ms": elapsed_ms,
        "flow_diagram": trace.get("flow_diagram", ""),
        "completeness_check": trace.get("completeness_check", {
            "fully_traced": True if chunks else False,
            "entry_points": [],
            "target_symbols": [c.get("symbol_name") for c in chunks if c.get("symbol_name")],
            "terminations": [],
            "unresolved_calls": []
        }),
        "execution_flow": trace.get("execution_flow", []),
        "metrics": metrics,
        "chunks": chunks,
        "dependency_edges": dep_edges,
        "related_tests": related_tests,
        "omissions": omissions,
        "warnings": warnings,
        "total_chunks": len(chunks),
        "truncated": truncated,
        "auto_reindexed": auto_reindexed,
        "estimated_tokens": retrieved_tokens,
    }


def _dedup_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Removes chunks whose line ranges are completely contained within another chunk
    from the same file. Keeps the chunk with the higher relevance score and ranks
    exact symbol matches at the very top.
    """
    score_sorted = sorted(chunks, key=lambda c: (
        1 if c.get("match_type") == "exact_symbol" else 0,
        c.get("relevance_score", 0.0)
    ), reverse=True)

    deduped: List[Dict[str, Any]] = []
    for chunk in score_sorted:
        dominated = False
        for existing in deduped:
            if (
                existing.get("file_path") == chunk.get("file_path")
                and existing.get("start_line", 0) <= chunk.get("start_line", 0)
                and existing.get("end_line", 0) >= chunk.get("end_line", 0)
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
    repo_filter: Optional[List[str]] = None,
    requesting_user: Optional[str] = None,
    caller_identity: str = "unknown",
) -> Dict[str, Any]:
    """
    Bundled context retrieval — the flagship M5 call.
    Combines FastEmbed vectors + BM25 keyword matching + Tree-sitter AST syntax
    via Reciprocal Rank Fusion (RRF), with optional enterprise repo-level ACL filtering.
    """
    start_time = time.perf_counter()
    resolved_org = org_id or os.getenv("DEFAULT_ORG_ID", "default_org")
    resolved_dept = dept_id or os.getenv("DEFAULT_DEPT_ID", "default_dept")
    resolved_repo = repo_id or os.getenv("DEFAULT_REPO_ID", "default_repo")

    request_id = str(uuid.uuid4())

    # ── Step -1: Empty Index Auto-Healing ─────────────────────────────────────
    auto_reindexed = False
    try:
        from src.storage.local_db import LocalCodeGraphDB
        local_db = LocalCodeGraphDB()
        stats = local_db.get_stats()
        if stats.get("total_files", 0) == 0:
            workspace_root = os.getenv("WORKSPACE_ROOT", ".")
            from src.indexer.file_watcher import LocalFileWatcher
            watcher = LocalFileWatcher(workspace_root)
            watcher.initial_scan()
            auto_reindexed = True
    except Exception:
        pass

    retriever = get_hybrid_retriever(org_id=resolved_org, dept_id=resolved_dept, repo_id=resolved_repo)
    d_graph = PersistentDependencyGraph(org_id=resolved_org, dept_id=resolved_dept, repo_id=resolved_repo)

    warnings: List[str] = []
    omissions: List[str] = []

    # ── Step 0: Exact AST Symbol Matching (Rank 1 Priority) ───────────────────
    exact_ast_chunks: List[Dict[str, Any]] = []
    try:
        from src.storage.local_db import LocalCodeGraphDB
        local_db = LocalCodeGraphDB()
        tokens_to_check = [query.strip()]
        query_words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", query)
        stop_words = {"the", "and", "for", "how", "where", "what", "function", "class", "method", "def", "code", "file", "all"}
        for w in query_words:
            if len(w) >= 3 and w.lower() not in stop_words and w not in tokens_to_check:
                tokens_to_check.append(w)

        for token in tokens_to_check:
            exact_matches = local_db.find_symbol(token, exact=True, limit=5, repo_filter=repo_filter)
            for em in exact_matches:
                sig = f"{em.get('file_path')}:{em.get('start_line')}"
                if not any(f"{c.get('file_path')}:{c.get('start_line')}" == sig for c in exact_ast_chunks):
                    exact_ast_chunks.append({
                        "file_path": em.get("file_path", ""),
                        "symbol_name": em.get("name", ""),
                        "symbol_type": em.get("kind", "symbol"),
                        "start_line": em.get("start_line", 1),
                        "end_line": em.get("end_line", 1),
                        "content": em.get("content", ""),
                        "relevance_score": 1.0,
                        "repo_id": em.get("repo_id", "local"),
                        "retrieval_method": "exact_ast_symbol",
                        "is_exact_ast": True
                    })
    except Exception:
        pass

    # ── Step 1: Hybrid Search (BM25 + Dense Vectors) ──────────────────────────
    raw_chunks: List[Dict[str, Any]] = []
    try:
        raw_chunks = retriever.search_blocks(query=query, top_k=top_k * 2, repo_filter=repo_filter)
    except Exception:
        raw_chunks = []

    # Local SQLite Fallback or complement
    if len(raw_chunks) < top_k:
        try:
            from src.storage.local_db import LocalCodeGraphDB
            local_db = LocalCodeGraphDB()
            local_symbols = local_db.find_symbol(query, exact=False, limit=top_k, repo_filter=repo_filter)
            if len(local_symbols) < top_k:
                fts_symbols = local_db.search_fts(query, limit=top_k, repo_filter=repo_filter)
                for fs in fts_symbols:
                    if not any(s.get("name") == fs.get("name") and s.get("file_path") == fs.get("file_path") for s in local_symbols):
                        local_symbols.append(fs)

            for sym in local_symbols:
                sig = f"{sym.get('file_path')}:{sym.get('start_line')}"
                if not any(f"{c.get('file_path')}:{c.get('start_line')}" == sig for c in raw_chunks):
                    raw_chunks.append({
                        "file_path": sym.get("file_path", ""),
                        "symbol_name": sym.get("name", ""),
                        "symbol_type": sym.get("kind", "code_block"),
                        "start_line": sym.get("start_line", 1),
                        "end_line": sym.get("end_line", 1),
                        "content": sym.get("content", ""),
                        "relevance_score": 0.85,
                        "repo_id": sym.get("repo_id", "local"),
                        "retrieval_method": "local_sqlite_ast_graph"
                    })
        except Exception:
            pass

    # Merge: Exact AST matches appear FIRST, followed by hybrid search results
    all_candidate_chunks = []
    seen_sigs = set()

    for ec in exact_ast_chunks:
        sig = f"{ec['file_path']}:{ec['start_line']}"
        seen_sigs.add(sig)
        all_candidate_chunks.append(ec)

    for rc in raw_chunks:
        sig = f"{rc.get('file_path')}:{rc.get('start_line')}"
        if sig not in seen_sigs:
            seen_sigs.add(sig)
            all_candidate_chunks.append(rc)

    # Enrich chunks with explainable metadata and architectural concern
    enriched_chunks = []
    for c in all_candidate_chunks:
        explanation = _explain_match(
            query=query,
            symbol_name=c.get("symbol_name", ""),
            file_path=c.get("file_path", ""),
            retrieval_method=c.get("retrieval_method", "hybrid_rrf"),
            score=c.get("relevance_score", 0.0),
            is_exact_ast=c.get("is_exact_ast", False)
        )
        c["match_type"] = explanation["match_type"]
        c["confidence"] = explanation["confidence"]
        c["match_reason"] = explanation["match_reason"]
        c["concern"] = _classify_chunk_concern(c.get("file_path", ""), c.get("symbol_name", ""))

        # Apply optional snippet truncation only if explicitly requested by caller
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

        for c in enriched_chunks:
            if c not in selected_chunks and len(selected_chunks) < top_k:
                selected_chunks.append(c)
    else:
        selected_chunks = enriched_chunks[:top_k]

    # Attach AST Callers, Callees, and High-Density Summary
    for c in selected_chunks:
        sym_name = c.get("symbol_name")
        f_path = c.get("file_path", "")
        c["callers"] = []
        c["callees"] = []
        if sym_name and sym_name != "anonymous":
            try:
                callers = d_graph.db.find_callers(sym_name, limit=5, repo_filter=repo_filter)
                c["callers"] = [
                    f"{r['source_symbol']} ({os.path.basename(r['source_file'])})"
                    for r in callers if r.get("source_symbol")
                ]
                callees = d_graph.db.find_callees(f_path, sym_name, repo_filter=repo_filter)
                c["callees"] = [r["target_symbol"] for r in callees if r.get("target_symbol")]
            except Exception:
                pass

        # High-density summary for LLM context compression
        content = c.get("content", "")
        first_lines = [line.strip() for line in content.splitlines() if line.strip()][:3]
        sig_str = first_lines[0] if first_lines else ""
        docstring_str = ""
        if '"""' in content:
            parts = content.split('"""')
            if len(parts) >= 3:
                docstring_str = parts[1].strip()[:200]
        elif "'''" in content:
            parts = content.split("'''")
            if len(parts) >= 3:
                docstring_str = parts[1].strip()[:200]

        c["summary"] = {
            "signature": sig_str,
            "line_range": f"{c.get('file_path')}:{c.get('start_line')}-{c.get('end_line')}",
            "docstring": docstring_str if docstring_str else None,
            "callers_count": len(c.get("callers", [])),
            "callees_count": len(c.get("callees", []))
        }

    # ── Step 3: Multi-Hop End-to-End Call Graph Tracing ───────────────────────
    trace_info = _trace_execution_path(
        d_graph=d_graph,
        primary_symbols=selected_chunks,
        repo_filter=repo_filter
    )

    # ── Step 4: Explicit Semantic Dependency Graph Edges ──────────────────────
    dep_edges: List[Dict[str, Any]] = []
    expanded_file_paths = set(c["file_path"] for c in selected_chunks)

    if expand_dependencies and selected_chunks:
        raw_edges = d_graph.get_edges_between_files(list(expanded_file_paths))
        for edge in raw_edges:
            src = edge["source"]
            tgt = edge["target"]
            edge["semantic_relationship"] = _infer_semantic_relationship(src, tgt)
            dep_edges.append(edge)

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

    # ── Step 5: Companion Test Discovery ──────────────────────────────────────
    related_tests = []
    for c in selected_chunks:
        tests = d_graph.find_companion_tests(c["file_path"])
        for t in tests:
            if t not in related_tests:
                related_tests.append(t)

    if "tests" in requested_concerns and not related_tests:
        omissions.append("tests: no companion test files found for matched components")

    # ── Step 6: Deduplication & Final Capping ─────────────────────────────────
    chunks = _dedup_chunks(selected_chunks)
    truncated = len(chunks) > _MAX_CHUNKS
    chunks = chunks[:_MAX_CHUNKS]

    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

    # ── Step 7: Assemble ContextBundle ────────────────────────────────────────
    bundle = _make_bundle(
        request_id=request_id,
        query=query,
        chunks=chunks,
        dep_edges=dep_edges,
        related_tests=related_tests,
        omissions=omissions,
        warnings=warnings,
        truncated=truncated,
        elapsed_ms=elapsed_ms,
        trace_info=trace_info,
        auto_reindexed=auto_reindexed,
    )

    try:
        from src.audit.telemetry import log_retrieval_trace
        transport = "mcp" if ("mcp" in caller_identity.lower() or caller_identity == "mcp/client") else "rest_api"
        log_retrieval_trace(
            query=query,
            org_id=resolved_org,
            dept_id=resolved_dept,
            repo_id=resolved_repo,
            requesting_user=requesting_user,
            caller_identity=caller_identity,
            top_k=top_k,
            expand_dependencies=expand_dependencies,
            duration_ms=elapsed_ms,
            result_bundle=bundle,
            transport=transport,
        )
    except Exception:
        pass

    return bundle
