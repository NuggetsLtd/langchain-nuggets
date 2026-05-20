# Cross-Org Authority Demo

Demonstrates all six Nuggets trust primitives with a cross-organisational delegation scenario.

## Setup

```bash
pip install langchain-nuggets fastapi uvicorn httpx
```

## Run

```bash
cd examples/python/cross_org_authority
python run_demo.py
```

## Scenarios

| # | Scenario | Expected |
|---|----------|----------|
| 1 | In-scope tool call | ALLOW + proof |
| 2 | Out-of-scope tool | DENY |
| 3 | Cap exceeded | DENY |
| 4 | Expired delegation | DENY |
| 5 | Revoked delegation | DENY |
| 6 | Different intent | Different proof hash |
| 7 | Proof verification | Independent verification succeeds |

## Verify a proof

```bash
python verify_proof.py demo_proof.json
```

## Architecture

```
Org A (Acme Corp)           Org B (Partner Inc)
  │                            │
  │ issues delegation ──────>  │ Agent B has scoped access
  │                            │
  │ local_authority.py         │ NuggetsAuthorityMiddleware
  │ /api/authority/evaluate    │ wraps tool calls
  │                            │
  └── proof verifiable independently by anyone
```
