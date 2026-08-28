"""
benchmark_load_test.py — Enterprise Load Testing & Latency Benchmarking for M5

Simulates concurrent AI developers (Copilot / Claude) querying M5 over:
  1. Remote MCP Endpoint (/mcp -> m5_get_context)
  2. REST Context API (/api/context)

Calculates:
  - Throughput (Requests Per Second - RPS)
  - Success / Error Rate (100% Target)
  - Latency Percentiles: Min, P50 (Median), P95, P99, Max
  - Internal M5 Engine retrieval duration vs Total HTTP Roundtrip
"""

import time
import json
import statistics
import concurrent.futures
import requests

# ── Configuration ─────────────────────────────────────────────────────────────
BASE_URL = "http://localhost:8000"
API_KEY = "m5_live_18ed80724c2cf29269e1c1dbd29cf5c1a6a82a66548ab4a3"

BENCHMARK_QUERIES = [
    "where is MatchmakingService defined?",
    "what calls joinQueue and findAndRemoveOpponent?",
    "explain SubmissionEvaluatedConsumer kafka event processing",
    "how does MatchmakingController expose REST endpoints?",
    "where is the code execution runner logic?",
]

def _send_mcp_request(query: str):
    """Simulates a real AI editor calling m5_get_context via Remote MCP."""
    start_time = time.perf_counter()
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "m5_get_context",
            "arguments": {"query": query, "top_k": 3}
        }
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    try:
        res = requests.post(f"{BASE_URL}/mcp", json=payload, headers=headers, timeout=10)
        roundtrip_ms = (time.perf_counter() - start_time) * 1000
        success = res.status_code == 200
        
        # Parse internal engine duration
        engine_ms = 0.0
        if success:
            data = res.json()
            content_str = data.get("result", {}).get("content", [{}])[0].get("text", "{}")
            bundle = json.loads(content_str)
            engine_ms = bundle.get("elapsed_ms", 0.0)
            
        return {
            "success": success,
            "status_code": res.status_code,
            "roundtrip_ms": roundtrip_ms,
            "engine_ms": engine_ms
        }
    except Exception as e:
        return {
            "success": False,
            "status_code": 0,
            "roundtrip_ms": (time.perf_counter() - start_time) * 1000,
            "engine_ms": 0.0,
            "error": str(e)
        }

def run_load_test(concurrency: int = 5, total_requests: int = 25):
    print(f"\n{'='*70}")
    print(f"[+] Launching M5 Load Test Benchmark")
    print(f"   * Concurrency (Simulated Devs): {concurrency}")
    print(f"   * Total Requests:             {total_requests}")
    print(f"   * Target Endpoint:            {BASE_URL}/mcp")
    print(f"{'='*70}\n")

    start_bench = time.perf_counter()
    results = []
    
    # Generate tasks
    tasks = [BENCHMARK_QUERIES[i % len(BENCHMARK_QUERIES)] for i in range(total_requests)]
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(_send_mcp_request, q) for q in tasks]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())
            completed = len(results)
            if completed % 5 == 0 or completed == total_requests:
                print(f"  [+] Progress: {completed}/{total_requests} requests completed ({completed*100//total_requests}%)...")

    total_bench_duration = time.perf_counter() - start_bench
    successful_results = [r for r in results if r["success"]]
    failed_count = len(results) - len(successful_results)
    
    roundtrips = [r["roundtrip_ms"] for r in successful_results]
    engine_times = [r["engine_ms"] for r in successful_results if r["engine_ms"] > 0]
    
    # Calculate statistics
    roundtrips.sort()
    engine_times.sort()
    
    rps = total_requests / total_bench_duration if total_bench_duration > 0 else 0
    p50_http = statistics.median(roundtrips) if roundtrips else 0
    p95_http = roundtrips[int(len(roundtrips) * 0.95)] if roundtrips else 0
    p99_http = roundtrips[int(len(roundtrips) * 0.99)] if roundtrips else 0
    min_http = min(roundtrips) if roundtrips else 0
    avg_http = statistics.mean(roundtrips) if roundtrips else 0
    
    avg_engine = statistics.mean(engine_times) if engine_times else 0
    p50_engine = statistics.median(engine_times) if engine_times else 0
    p95_engine = engine_times[int(len(engine_times) * 0.95)] if engine_times else 0

    # Print Benchmark Report
    print(f"\n{'='*70}")
    print(f"[RESULTS] M5 ENTERPRISE BENCHMARK REPORT (Customer-Ready)")
    print(f"{'='*70}")
    print(f"  * Total Requests Executed:    {total_requests}")
    print(f"  * Success Rate:               {len(successful_results)/total_requests*100:.1f}% ({len(successful_results)}/{total_requests})")
    print(f"  * Errors / Timeouts:          {failed_count}")
    print(f"  * Total Test Duration:        {total_bench_duration:.2f} seconds")
    print(f"  * Throughput (RPS):           {rps:.2f} req/sec")
    print(f"----------------------------------------------------------------------")
    print(f"  [HTTP Round-Trip Latency] (Network + Server):")
    print(f"     - Min Latency:             {min_http:.2f} ms")
    print(f"     - Avg Latency:             {avg_http:.2f} ms")
    print(f"     - P50 (Median):            {p50_http:.2f} ms")
    print(f"     - P95 (95% of users):      {p95_http:.2f} ms")
    print(f"     - P99 (Peak SLA):          {p99_http:.2f} ms")
    print(f"----------------------------------------------------------------------")
    print(f"  [Core M5 Retrieval Time] (BM25 + Vector + Graph):")
    print(f"     - Avg Engine Time:         {avg_engine:.2f} ms")
    print(f"     - P50 Engine Time:         {p50_engine:.2f} ms")
    print(f"     - P95 Engine Time:         {p95_engine:.2f} ms")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    # Run test with 5 concurrent AI clients sending 25 queries
    run_load_test(concurrency=5, total_requests=25)
