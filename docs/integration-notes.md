# Authority Middleware — Integration Notes

## How Invasive Is It?

**Minimally invasive.** The middleware requires **zero changes** to existing tools, agents, or LLM configuration. It slots into the standard LangGraph `ToolNode` extension point.

### Integration: 3 lines of code

```python
# Before (no middleware)
tool_node = ToolNode(tools=tools)

# After (with middleware)
middleware = NuggetsAuthorityMiddleware(config)            # +1
tool_node = ToolNode(
    tools=tools,
    wrap_tool_call=middleware.wrap_tool_call,               # +1
)
```

Plus the config setup (~8 lines, done once):

```python
config = MiddlewareConfig(
    api_url="https://api.nuggets.life",
    partner_id="...",
    partner_secret="...",
    agent_id="...",
    controller_id="...",
    delegation_id="...",
)
```

**Total: ~11 lines to integrate** into an existing LangGraph agent.

## What Changes, What Doesn't

| Aspect | Changes? | Details |
|--------|:--------:|---------|
| Tool implementations | No | Tools are unaware of the middleware |
| LLM / model config | No | The LLM sees tools normally |
| Agent logic | No | Agent graph is unchanged |
| ToolNode creation | Yes | Add `wrap_tool_call` parameter |
| New dependency | No | Uses existing `langchain-nuggets` package |
| New config | Yes | `MiddlewareConfig` with 6 required fields |

## Interception Mechanism

The middleware uses LangGraph's `wrap_tool_call` parameter on `ToolNode`. This is a **stable, public API** — not a monkey-patch or internal hook.

```
ToolNode(tools, wrap_tool_call=...)   # sync
ToolNode(tools, awrap_tool_call=...)  # async
```

The wrapper signature is:
```python
(ToolCallRequest, handler) -> ToolMessage | Command
```

- `request.tool_call` is a dict with `name`, `args`, `id`
- `handler(request)` executes the tool
- Return a `ToolMessage` directly to block execution

**Why not callbacks?** LangChain callbacks (`on_tool_start`, `on_tool_end`) are purely observational — they cannot block execution. The `wrap_tool_call` pattern is the only way to enforce pre-execution authority checks.

## Coupling Assessment

| Risk | Level | Mitigation |
|------|-------|------------|
| LangGraph version dependency | Low | Uses `ToolNode` public API, stable since LangGraph 0.2+ |
| Tool call dict structure | Low | `name`, `args`, `id` keys are part of LangChain's `ToolCall` TypedDict |
| Nuggets API availability | Medium | Middleware fails closed (denies on error), configurable |
| Network latency | Medium | Single HTTP round-trip per tool call; see latency analysis |

## Failure Modes

| Scenario | Behaviour |
|----------|-----------|
| Authority endpoint returns ALLOW | Tool executes normally, proof emitted |
| Authority endpoint returns DENY | Tool blocked, structured error ToolMessage returned to LLM |
| Authority endpoint unreachable | **Fail closed** — tool not executed, error ToolMessage returned |
| Authority endpoint returns invalid response | Fail closed — treated as error |
| Middleware config missing fields | `ValidationError` at construction time (Pydantic) |

The LLM sees denied/error results as `ToolMessage` content, so it can reason about failures and adjust its plan — no crashes or exceptions propagate.

## Async Support

Both sync and async variants are provided:

| Pattern | Method | Use case |
|---------|--------|----------|
| `wrap_tool_call` | `middleware.wrap_tool_call` | Sync tools, `ToolNode` default |
| `awrap_tool_call` | `middleware.awrap_tool_call` | Async tools, async event loops |

The async variant uses `NuggetsApiClient.apost()` (httpx.AsyncClient) for non-blocking HTTP calls.

## Proof Artifacts

After execution, proofs are accessible via `middleware.proofs` and optionally via a callback:

```python
config = MiddlewareConfig(
    ...,
    on_proof=lambda proof: audit_log.write(proof.model_dump_json()),
)
```

Each `ProofArtifact` contains:
- `proof_id` — unique ID from the authority endpoint
- `authority_signature` — cryptographic signature from the authority
- `parameters_hash` / `result_hash` — SHA-256 hashes binding params and result
- `latency_ms` — end-to-end latency measurement
- Agent, controller, delegation, and tool identifiers

## Files Added

| File | Lines | Purpose |
|------|------:|---------|
| `middleware/types.py` | 58 | Pydantic models (config, request, response, proof) |
| `middleware/proof.py` | 49 | SHA-256 hashing + proof construction |
| `middleware/authority_middleware.py` | 150 | Main middleware class |
| `middleware/__init__.py` | 25 | Public exports |
| **Total middleware** | **282** | |
| `tests/middleware/test_types.py` | 99 | Type validation tests |
| `tests/middleware/test_proof.py` | 48 | Hashing/proof tests |
| `tests/middleware/test_authority_middleware.py` | 182 | Middleware behaviour tests |
| **Total tests** | **329** | |
| `authority_middleware_demo.py` | 140 | Working demo |
| **Grand total** | **751** | |
