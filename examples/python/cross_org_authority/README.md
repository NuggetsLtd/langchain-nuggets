# Cross-Org Authority Demo

Demonstrates all six Nuggets trust primitives with a cross-organisational delegation scenario.

## Setup

```bash
pip install langchain-nuggets fastapi uvicorn httpx python-multipart
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

## Mock vs. real backend

`local_authority.py` exercises the real auth flow shape (OIDC
`client_credentials` → bearer token → signed `agent_proof` in the
authority POST) but **does not verify** the OIDC `client_assertion`
or the `agent_proof` JWS. It's enough for the demo to run end-to-end
offline, but not a substitute for the deployed Nuggets backend, which
verifies both signatures against the agent's registered JWKS.

To verify the SDK against a real deployed environment, run from the
**repo root** (not the demo directory):

```bash
export NUGGETS_AUTHORITY_URL=...
export NUGGETS_OIDC_ISSUER_URL=...
export NUGGETS_AGENT_ID=...
export NUGGETS_CONTROLLER_ID=...
export NUGGETS_DELEGATION_ID=...
export NUGGETS_AGENT_PRIVATE_KEY=/path/to/agent-jwks.json

# CLI form
python scripts/smoke_test_authority.py

# Or via pytest (skips cleanly when env vars are unset)
pytest examples/python/cross_org_authority/test_authority_integration.py -s
```

See `scripts/smoke_test_authority.py` for full setup notes.
