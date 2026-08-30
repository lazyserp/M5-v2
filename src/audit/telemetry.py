"""
telemetry.py — Langfuse AI Observability & Tracing for M5 v2

Provides fail-safe, non-blocking telemetry for M5 context requests and MCP tool executions.
Adheres to Langfuse best practices:
- Observation Types (retriever, tool, generation, span)
- User Attribution (identifies developer/client name)
- Usage & Token Details (input, output, total tokens tracked via generation observations)
- Attribute Propagation (user_id, session_id, tags, metadata)
- Automated Flushing
- Fail-Safe: Graceful no-op when credentials are absent or network is unreachable.
"""

import os
import time
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger("m5.telemetry")

_LANGFUSE_CLIENT = None
_INITIALIZED = False


def _clean_env_val(val: Optional[str]) -> str:
    if not val:
        return ""
    return val.strip().strip("\"'")


def get_telemetry_client():
    """Initializes and returns the singleton Langfuse client if configured."""
    global _LANGFUSE_CLIENT, _INITIALIZED

    if _INITIALIZED:
        return _LANGFUSE_CLIENT

    _INITIALIZED = True

    try:
        from dotenv import load_dotenv
        load_dotenv(override=False)
    except Exception:
        pass

    public_key = _clean_env_val(os.getenv("LANGFUSE_PUBLIC_KEY"))
    secret_key = _clean_env_val(os.getenv("LANGFUSE_SECRET_KEY"))
    host = _clean_env_val(os.getenv("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST") or "https://cloud.langfuse.com")

    if not public_key or not secret_key:
        logger.debug("Langfuse telemetry credentials not set. Tracing is disabled.")
        return None

    # Set host environment variable for consistency
    os.environ["LANGFUSE_HOST"] = host
    os.environ["LANGFUSE_BASE_URL"] = host

    try:
        from langfuse import Langfuse
        _LANGFUSE_CLIENT = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host
        )
        logger.info(f"Langfuse telemetry connected (Host: {host})")
    except Exception as e:
        logger.warning(f"Langfuse telemetry disabled: {e}")
        _LANGFUSE_CLIENT = None

    return _LANGFUSE_CLIENT


def flush_telemetry() -> None:
    """Flushes any buffered events to Langfuse."""
    client = get_telemetry_client()
    if client is not None:
        try:
            client.flush()
        except Exception as e:
            logger.debug(f"Telemetry flush error: {e}")


def _resolve_user_id(requesting_user: Optional[str], caller_identity: Optional[str]) -> str:
    """Resolves human/system user identifier for Langfuse attribution."""
    if requesting_user and requesting_user.strip() and requesting_user.strip() not in ("unknown", "mcp/client"):
        return requesting_user.strip()
    if caller_identity and caller_identity.strip() and caller_identity.strip() not in ("unknown", "mcp/client"):
        return caller_identity.strip()
    system_user = os.getenv("USERNAME") or os.getenv("USER") or "developer"
    return system_user


def log_retrieval_trace(
    query: str,
    org_id: str,
    dept_id: str,
    repo_id: str,
    requesting_user: Optional[str],
    caller_identity: Optional[str],
    top_k: int,
    expand_dependencies: bool,
    duration_ms: float,
    result_bundle: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    transport: str = "mcp"
) -> None:
    """
    Logs a flagship context retrieval event to Langfuse with user attribution and token usage.
    Fail-safe: never raises exceptions or blocks execution.
    """
    client = get_telemetry_client()
    if client is None:
        return

    try:
        from langfuse import propagate_attributes

        user_identifier = _resolve_user_id(requesting_user, caller_identity)
        session_identifier = f"{org_id}:{dept_id}:{repo_id}"
        chunks: List[Dict[str, Any]] = (result_bundle or {}).get("chunks", [])
        dep_edges: List[Dict[str, Any]] = (result_bundle or {}).get("dependency_edges", [])
        related_tests: List[str] = (result_bundle or {}).get("related_tests", [])
        citations = [
            f"{c.get('file_path')}:{c.get('start_line')}-{c.get('end_line')} ({c.get('symbol_name')})"
            for c in chunks
        ]
        estimated_tokens = (result_bundle or {}).get("estimated_tokens", 0)
        request_id = (result_bundle or {}).get("request_id")

        # Estimate input, output, and total token usage for dashboard analytics
        input_tokens = max(1, len(str(query)) // 4)
        output_tokens = max(1, estimated_tokens or (sum(len(c.get("content", "")) for c in chunks) // 4))
        total_tokens = input_tokens + output_tokens
        usage_details = {
            "input": input_tokens,
            "output": output_tokens,
            "total": total_tokens
        }

        tags = [
            f"org:{org_id}",
            f"repo:{repo_id}",
            f"transport:{transport}",
            f"user:{user_identifier}",
            "tool:m5_get_context"
        ]

        metadata = {
            "org_id": org_id,
            "dept_id": dept_id,
            "repo_id": repo_id,
            "user_id": user_identifier,
            "caller_identity": caller_identity or "unknown",
            "duration_ms": duration_ms,
            "chunks_count": len(chunks),
            "dependency_edges_count": len(dep_edges),
            "related_tests_count": len(related_tests),
            "total_tokens": total_tokens,
            "truncated": (result_bundle or {}).get("truncated", False),
        }
        if request_id:
            metadata["request_id"] = request_id

        input_payload = {
            "query": query,
            "top_k": top_k,
            "expand_dependencies": expand_dependencies
        }

        output_payload = {
            "total_chunks": len(chunks),
            "estimated_tokens": total_tokens,
            "citations": citations[:15],
            "related_tests": related_tests,
            "omissions": (result_bundle or {}).get("omissions", []),
            "warnings": (result_bundle or {}).get("warnings", []),
            "error": error
        }

        with propagate_attributes(
            user_id=user_identifier,
            session_id=session_identifier,
            tags=tags,
            metadata=metadata
        ):
            with client.start_as_current_observation(
                name="m5_get_context",
                as_type="retriever",
                input=input_payload,
                output=output_payload
            ) as root_obs:
                # Generation observation to populate token counts and cost dashboards in Langfuse
                with client.start_as_current_observation(
                    name="context_retrieval_usage",
                    as_type="generation",
                    model="m5-context-engine",
                    input={"query": query},
                    output={"chunks_retrieved": len(chunks), "citations": citations[:5]},
                    usage_details=usage_details
                ):
                    pass

                # Sub-observation: Hybrid Search
                if chunks:
                    top_chunk = chunks[0]
                    with client.start_as_current_observation(
                        name="hybrid_search",
                        as_type="retriever",
                        input={"query": query, "top_k": top_k},
                        output={
                            "top_symbol": top_chunk.get("symbol_name"),
                            "top_file": top_chunk.get("file_path"),
                            "top_score": top_chunk.get("relevance_score"),
                            "match_type": top_chunk.get("match_type"),
                            "confidence": top_chunk.get("confidence")
                        }
                    ):
                        pass

                # Sub-observation: Dependency Expansion
                if dep_edges:
                    with client.start_as_current_observation(
                        name="expand_dependencies",
                        as_type="tool",
                        input={"expand_dependencies": expand_dependencies},
                        output={"edges_count": len(dep_edges), "edges": dep_edges[:10]}
                    ):
                        pass

                # Sub-observation: Companion Test Discovery
                if related_tests:
                    with client.start_as_current_observation(
                        name="companion_test_discovery",
                        as_type="tool",
                        input={"targets": [c.get("file_path") for c in chunks[:5]]},
                        output={"companion_tests": related_tests}
                    ):
                        pass

        flush_telemetry()

    except Exception as ex:
        logger.debug(f"Non-critical telemetry retrieval logging error: {ex}")


def log_mcp_tool_trace(
    tool_name: str,
    args: Dict[str, Any],
    output: Any,
    duration_ms: float,
    caller_identity: Optional[str] = None,
    org_id: str = "default_org",
    dept_id: str = "default_dept",
    repo_id: str = "default_repo",
    transport: str = "mcp_stdio",
    error: Optional[str] = None
) -> None:
    """
    Logs any MCP tool call to Langfuse with user attribution and token usage.
    """
    client = get_telemetry_client()
    if client is None:
        return

    # m5_get_context is already traced in detail by log_retrieval_trace
    if tool_name == "m5_get_context":
        return

    try:
        from langfuse import propagate_attributes

        user_identifier = _resolve_user_id(None, caller_identity)
        session_identifier = f"{org_id}:{dept_id}:{repo_id}"

        as_type = "tool"
        if tool_name in ("m5_search_code", "m5_find_symbol_references"):
            as_type = "retriever"

        # Estimate tokens for the tool call
        input_tokens = max(1, len(str(args)) // 4)
        output_tokens = max(1, len(str(output)) // 4)
        total_tokens = input_tokens + output_tokens
        usage_details = {
            "input": input_tokens,
            "output": output_tokens,
            "total": total_tokens
        }

        tags = [
            f"org:{org_id}",
            f"repo:{repo_id}",
            f"transport:{transport}",
            f"user:{user_identifier}",
            f"tool:{tool_name}"
        ]

        metadata = {
            "org_id": org_id,
            "dept_id": dept_id,
            "repo_id": repo_id,
            "user_id": user_identifier,
            "caller_identity": caller_identity or "unknown",
            "duration_ms": duration_ms,
            "total_tokens": total_tokens,
            "error": error
        }

        # Sanitize output representation for readable trace view
        out_summary = output
        if isinstance(output, str) and len(output) > 2000:
            out_summary = output[:2000] + "\n... [truncated for display]"

        with propagate_attributes(
            user_id=user_identifier,
            session_id=session_identifier,
            tags=tags,
            metadata=metadata
        ):
            with client.start_as_current_observation(
                name=tool_name,
                as_type=as_type,
                input=args,
                output={"result": out_summary, "error": error}
            ):
                with client.start_as_current_observation(
                    name=f"{tool_name}_usage",
                    as_type="generation",
                    model="m5-context-engine",
                    input=args,
                    output={"result": "completed"},
                    usage_details=usage_details
                ):
                    pass

        flush_telemetry()

    except Exception as ex:
        logger.debug(f"Non-critical MCP tool telemetry error: {ex}")
