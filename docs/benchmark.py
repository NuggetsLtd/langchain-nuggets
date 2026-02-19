"""Latency benchmark for NuggetsAuthorityMiddleware.

Measures per-tool-invocation overhead introduced by the middleware,
isolating middleware processing time from network latency.

Usage:
    cd packages/python
    python ../../docs/benchmark.py
"""
from __future__ import annotations

import json
import statistics
import time
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import ToolMessage

from langchain_nuggets.middleware import MiddlewareConfig, NuggetsAuthorityMiddleware


def create_middleware() -> NuggetsAuthorityMiddleware:
    config = MiddlewareConfig(
        api_url="https://api.nuggets.test",
        partner_id="bench-partner",
        partner_secret="bench-secret",
        agent_id="agent-bench",
        controller_id="org-bench",
        delegation_id="del-bench",
    )
    middleware = NuggetsAuthorityMiddleware(config)
    # Mock the HTTP client to isolate middleware overhead
    middleware._client = MagicMock()
    middleware._client.post.return_value = {
        "decision": "ALLOW",
        "proof_id": "proof-bench",
        "signature": "sig-bench",
        "reason_code": None,
    }
    return middleware


def make_request(tool_name: str = "benchmark_tool", n_args: int = 5) -> MagicMock:
    request = MagicMock()
    request.tool_call = {
        "name": tool_name,
        "args": {f"param_{i}": f"value_{i}" for i in range(n_args)},
        "id": f"call-bench-{time.monotonic_ns()}",
    }
    return request


def make_handler() -> MagicMock:
    handler = MagicMock()
    handler.return_value = ToolMessage(
        content='{"status": "ok"}',
        tool_call_id="call-bench",
    )
    return handler


def benchmark_sync(iterations: int = 1000) -> dict:
    """Benchmark sync wrap_tool_call."""
    middleware = create_middleware()
    handler = make_handler()

    # Warmup
    for _ in range(50):
        middleware.wrap_tool_call(make_request(), handler)
    middleware._proofs.clear()

    latencies = []
    for _ in range(iterations):
        request = make_request()
        start = time.perf_counter_ns()
        middleware.wrap_tool_call(request, handler)
        elapsed_us = (time.perf_counter_ns() - start) / 1000
        latencies.append(elapsed_us)

    return {
        "iterations": iterations,
        "mean_us": statistics.mean(latencies),
        "median_us": statistics.median(latencies),
        "p95_us": sorted(latencies)[int(iterations * 0.95)],
        "p99_us": sorted(latencies)[int(iterations * 0.99)],
        "min_us": min(latencies),
        "max_us": max(latencies),
        "stdev_us": statistics.stdev(latencies),
    }


def benchmark_deny(iterations: int = 1000) -> dict:
    """Benchmark DENY path (no tool execution)."""
    middleware = create_middleware()
    middleware._client.post.return_value = {
        "decision": "DENY",
        "proof_id": "proof-deny",
        "signature": "sig-deny",
        "reason_code": "BENCHMARK",
    }
    handler = make_handler()

    # Warmup
    for _ in range(50):
        middleware.wrap_tool_call(make_request(), handler)

    latencies = []
    for _ in range(iterations):
        request = make_request()
        start = time.perf_counter_ns()
        middleware.wrap_tool_call(request, handler)
        elapsed_us = (time.perf_counter_ns() - start) / 1000
        latencies.append(elapsed_us)

    return {
        "iterations": iterations,
        "mean_us": statistics.mean(latencies),
        "median_us": statistics.median(latencies),
        "p95_us": sorted(latencies)[int(iterations * 0.95)],
        "p99_us": sorted(latencies)[int(iterations * 0.99)],
        "min_us": min(latencies),
        "max_us": max(latencies),
        "stdev_us": statistics.stdev(latencies),
    }


def benchmark_hashing(iterations: int = 10000) -> dict:
    """Benchmark just the SHA-256 hashing overhead."""
    from langchain_nuggets.middleware.proof import hash_parameters, hash_result

    args_small = {"key": "value"}
    args_large = {f"param_{i}": f"value_{i}" * 100 for i in range(50)}

    # Small args
    latencies_small = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        hash_parameters(args_small)
        elapsed_us = (time.perf_counter_ns() - start) / 1000
        latencies_small.append(elapsed_us)

    # Large args
    latencies_large = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        hash_parameters(args_large)
        elapsed_us = (time.perf_counter_ns() - start) / 1000
        latencies_large.append(elapsed_us)

    return {
        "small_args_mean_us": statistics.mean(latencies_small),
        "small_args_median_us": statistics.median(latencies_small),
        "large_args_mean_us": statistics.mean(latencies_large),
        "large_args_median_us": statistics.median(latencies_large),
    }


def main() -> None:
    print("=" * 70)
    print("NuggetsAuthorityMiddleware — Latency Benchmark")
    print("=" * 70)
    print()
    print("NOTE: HTTP calls are mocked. These numbers measure pure middleware")
    print("overhead (payload construction, hashing, proof building).")
    print("Real-world latency = middleware overhead + network round-trip.")
    print()

    print("-" * 70)
    print("1. ALLOW path (full flow: eval + execute + proof)")
    print("-" * 70)
    allow = benchmark_sync(1000)
    print(f"   Iterations:  {allow['iterations']}")
    print(f"   Mean:        {allow['mean_us']:.1f} µs")
    print(f"   Median:      {allow['median_us']:.1f} µs")
    print(f"   P95:         {allow['p95_us']:.1f} µs")
    print(f"   P99:         {allow['p99_us']:.1f} µs")
    print(f"   Min:         {allow['min_us']:.1f} µs")
    print(f"   Max:         {allow['max_us']:.1f} µs")
    print()

    print("-" * 70)
    print("2. DENY path (eval only, no tool execution)")
    print("-" * 70)
    deny = benchmark_deny(1000)
    print(f"   Iterations:  {deny['iterations']}")
    print(f"   Mean:        {deny['mean_us']:.1f} µs")
    print(f"   Median:      {deny['median_us']:.1f} µs")
    print(f"   P95:         {deny['p95_us']:.1f} µs")
    print(f"   P99:         {deny['p99_us']:.1f} µs")
    print()

    print("-" * 70)
    print("3. SHA-256 hashing overhead")
    print("-" * 70)
    hashing = benchmark_hashing(10000)
    print(f"   Small args (1 key):   {hashing['small_args_mean_us']:.2f} µs mean")
    print(f"   Large args (50 keys): {hashing['large_args_mean_us']:.2f} µs mean")
    print()

    print("-" * 70)
    print("4. Summary")
    print("-" * 70)
    print(f"   Middleware overhead (ALLOW):  ~{allow['median_us']:.0f} µs per tool call")
    print(f"   Middleware overhead (DENY):   ~{deny['median_us']:.0f} µs per tool call")
    print(f"   Typical LLM call:            ~500,000–2,000,000 µs")
    print(f"   Typical tool execution:      ~10,000–1,000,000 µs")
    print(f"   Authority network RTT:       ~5,000–50,000 µs (estimate)")
    print()
    print("   Middleware processing adds negligible overhead (<1ms).")
    print("   The dominant cost is the network round-trip to the authority")
    print("   evaluation endpoint, which is expected at 5–50ms depending")
    print("   on deployment topology.")
    print()


if __name__ == "__main__":
    main()
