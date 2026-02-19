# Authority Middleware — Architecture

## Execution Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        LangGraph Agent                              │
│                                                                     │
│  ┌──────────┐    ┌──────────────────────────────────────────────┐   │
│  │   LLM    │───▶│               ToolNode                       │   │
│  │ (decide  │    │  wrap_tool_call = middleware.wrap_tool_call   │   │
│  │  action) │    └──────────────┬───────────────────────────────┘   │
│  └──────────┘                   │                                   │
│                                 ▼                                   │
│              ┌──────────────────────────────────┐                   │
│              │  NuggetsAuthorityMiddleware       │                   │
│              │                                   │                   │
│              │  1. Extract tool name, args, id   │                   │
│              │  2. Hash parameters (SHA-256)     │                   │
│              │  3. Build evaluation payload      │                   │
│              │     ┌───────────────────────┐     │                   │
│              │     │ agent_id              │     │                   │
│              │     │ controller_id         │     │                   │
│              │     │ delegation_id         │     │                   │
│              │     │ action:               │     │                   │
│              │     │   tool, target,       │     │                   │
│              │     │   parameters_hash,    │     │                   │
│              │     │   intent, timestamp   │     │                   │
│              │     └───────────────────────┘     │                   │
│              └──────────────┬───────────────────┘                   │
│                             │                                       │
│                             ▼                                       │
│              ┌──────────────────────────────────┐                   │
│              │  POST /authority/evaluate         │                   │
│              │  (Nuggets Control Plane)          │                   │
│              └──────────────┬───────────────────┘                   │
│                             │                                       │
│                    ┌────────┴────────┐                              │
│                    ▼                 ▼                               │
│              ┌──────────┐    ┌──────────────┐                       │
│              │  ALLOW   │    │    DENY      │                       │
│              └─────┬────┘    └──────┬───────┘                       │
│                    │                │                                │
│                    ▼                ▼                                │
│           ┌──────────────┐  ┌────────────────┐                      │
│           │ Execute tool │  │ Return error   │                      │
│           │ handler()    │  │ ToolMessage    │                      │
│           └──────┬───────┘  │ (tool blocked) │                      │
│                  │          └────────────────┘                      │
│                  ▼                                                   │
│           ┌──────────────┐                                          │
│           │ Hash result  │                                          │
│           │ Build proof  │                                          │
│           │ Emit artifact│                                          │
│           └──────┬───────┘                                          │
│                  │                                                   │
│                  ▼                                                   │
│           ┌──────────────────────────────────┐                      │
│           │         ProofArtifact            │                      │
│           │  proof_id, agent_id,             │                      │
│           │  controller_id, delegation_id,   │                      │
│           │  tool, parameters_hash,          │                      │
│           │  result_hash,                    │                      │
│           │  authority_signature,            │                      │
│           │  timestamp, latency_ms           │                      │
│           └──────────────────────────────────┘                      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Trust Primitives Mapping

```
┌─────────────────────────────────────────────────────────┐
│                   6 Nuggets Trust Primitives             │
├──────────────────┬──────────────────────────────────────┤
│ 1. Actor Identity│  agent_id in evaluation payload      │
│                  │  Validated by authority endpoint      │
├──────────────────┼──────────────────────────────────────┤
│ 2. Authority     │  delegation_id + controller_id       │
│                  │  Delegation token verified server-side│
├──────────────────┼──────────────────────────────────────┤
│ 3. Policy        │  Evaluated server-side against:      │
│                  │  tool name, target, parameters,      │
│                  │  delegation constraints               │
├──────────────────┼──────────────────────────────────────┤
│ 4. Intent        │  ActionContext.intent field           │
│                  │  Hashed into proof artifact           │
├──────────────────┼──────────────────────────────────────┤
│ 5. Consent       │  Encoded in delegation constraints   │
│                  │  Scope, time bounds, caps enforced    │
│                  │  dynamically by authority endpoint    │
├──────────────────┼──────────────────────────────────────┤
│ 6. Accountability│  ProofArtifact emitted per ALLOW     │
│                  │  SHA-256 hashes of params + result    │
│                  │  Authority signature bound to proof   │
│                  │  Verifiable independently of logs     │
└──────────────────┴──────────────────────────────────────┘
```

## Component Relationships

```
                    ┌───────────────┐
                    │ MiddlewareConfig│
                    │ (Pydantic)     │
                    └───────┬───────┘
                            │ configures
                            ▼
┌────────────────────────────────────────────┐
│       NuggetsAuthorityMiddleware           │
│                                            │
│  ┌──────────────────┐  ┌───────────────┐  │
│  │ NuggetsApiClient │  │ proof.py      │  │
│  │ (reused from     │  │ hash_params() │  │
│  │  toolkit layer)  │  │ hash_result() │  │
│  │                  │  │ build_proof() │  │
│  │  .post() sync    │  └───────────────┘  │
│  │  .apost() async  │                     │
│  └──────────────────┘                     │
│                                            │
│  Exposes:                                  │
│    .wrap_tool_call(request, handler)       │
│    .awrap_tool_call(request, handler)      │
│    .proofs → List[ProofArtifact]           │
└────────────────────────────────────────────┘
         │                        │
         │ sync                   │ async
         ▼                        ▼
  ToolNode(                ToolNode(
    wrap_tool_call=...)      awrap_tool_call=...)
```
