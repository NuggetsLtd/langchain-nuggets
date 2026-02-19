# Authority Middleware — Latency Measurements

## Methodology

- HTTP calls mocked to isolate **pure middleware overhead** (payload construction, SHA-256 hashing, proof building, Pydantic serialization)
- Real-world latency = middleware overhead + authority endpoint network round-trip
- Measured using `time.perf_counter_ns()` with 1,000 iterations after 50-iteration warmup
- Platform: Python 3.12, macOS (Apple Silicon)

## Results

### ALLOW Path (full flow: eval + execute + proof)

| Metric | Value |
|--------|------:|
| Mean | 27.6 µs |
| Median | 26.9 µs |
| P95 | 34.5 µs |
| P99 | 52.8 µs |
| Min | 21.0 µs |
| Max | 133.7 µs |

### DENY Path (eval only, no tool execution or proof)

| Metric | Value |
|--------|------:|
| Mean | 21.9 µs |
| Median | 20.7 µs |
| P95 | 24.8 µs |
| P99 | 70.5 µs |

### SHA-256 Hashing

| Input Size | Mean |
|-----------|------:|
| Small (1 key) | 1.97 µs |
| Large (50 keys, ~5KB) | 137.52 µs |

## Context

| Operation | Typical Latency |
|-----------|----------------|
| **Middleware processing** | **~27 µs** |
| Authority endpoint RTT (co-located) | ~5–15 ms |
| Authority endpoint RTT (cross-region) | ~30–50 ms |
| Tool execution (API call) | ~10–1,000 ms |
| LLM inference | ~500–2,000 ms |

## Conclusion

Middleware processing overhead is **~27 µs per tool call** — negligible relative to any real operation in the pipeline. The dominant cost will be the network round-trip to the Nuggets authority evaluation endpoint. Even at 50ms (worst case cross-region), this is 2.5–10% of a typical LLM inference call, and authority enforcement happens in parallel with the latency the user is already accepting for tool execution.

## Reproducing

```bash
cd packages/python
python ../../docs/benchmark.py
```
