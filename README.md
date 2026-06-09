# langchain-nuggets

Authority middleware for LangChain / LangGraph — pre-execution trust enforcement on every tool call.

Wrap any `ToolNode` and the middleware calls the Nuggets authority endpoint before each tool executes. The backend evaluates a scoped delegation, returns an `ALLOW` or `DENY` decision, and signs an audit proof. Tools that aren't allowed never run.

## Install

```bash
pip install langchain-nuggets
```

For LangGraph Platform OIDC auth:

```bash
pip install langchain-nuggets[langgraph]
```

## Authority Middleware

```python
from langchain_nuggets.middleware import NuggetsAuthorityMiddleware, MiddlewareConfig
from langgraph.prebuilt import ToolNode

config = MiddlewareConfig(
    api_url="https://accounts.nuggets.life",
    oidc_issuer_url="https://auth.nuggets.life",
    agent_id="did:web:auth.nuggets.life:your-agent-id",
    controller_id="did:web:auth.nuggets.life:your-controller-id",
    delegation_id="42",
    agent_private_key="/path/to/agent-jwks.json",
)

middleware = NuggetsAuthorityMiddleware(config)

tool_node = ToolNode(
    tools=your_tools,
    wrap_tool_call=middleware.wrap_tool_call,
)

for proof in middleware.proofs:
    print(f"{proof.proof_id}: {proof.tool} ({proof.latency_ms:.0f}ms)")
```

See [`examples/python/authority_middleware_demo.py`](./examples/python/authority_middleware_demo.py) and the offline cross-org demo at [`examples/python/cross_org_authority/`](./examples/python/cross_org_authority/).

To provision an agent + delegation in the portal, see [the agent provisioning runbook](./docs/agent-provisioning.md).

### Proof verification (on by default)

Every `ALLOW` carries a proof signed by the authority. The SDK **verifies it before the tool runs** — it discovers the authority's signing identity from `{api_url}/.well-known/authority-configuration`, pins the proof's issuer to that authority, verifies the signature against the authority's published JWKS, and binds the proof to the request (decision, proof_id, agent_id, controller_id, constraints_evaluated). Any failure fails **closed** — the decision is treated as a `DENY` with `reason_code = PROOF_VERIFICATION_FAILED` and the tool does not run. No configuration needed; it's on by default.

This makes every decision **independently verifiable**. A third party can validate an emitted proof out-of-band with the exported helper:

```python
from langchain_nuggets.middleware import verify_authority_proof, discover_authority

issuer, jwks_uri = discover_authority("https://accounts.nuggets.life")
verify_authority_proof(proof_jws, expected={...}, issuer=issuer, jwks_uri=jwks_uri)
```

Disable verification only as a deliberate opt-out (e.g. an offline harness that verifies proofs separately): `MiddlewareConfig(..., verify_proofs=False)`.

### Agent private key

Every authority request is signed with an RS256 JWS proving the request originated from the agent that owns the DID. The Nuggets backend verifies the signature against the agent's registered OIDC public key.

The accounts portal generates the keypair at agent creation and lets you download the private key as a JWKS file. `MiddlewareConfig.agent_private_key` accepts:

- A filesystem path to a PEM, JWK JSON, or JWKS JSON file
- A raw PEM string
- A JWK or JWKS dict

```python
config = MiddlewareConfig(..., agent_private_key="/secrets/agent-jwks.json")
config = MiddlewareConfig(..., agent_private_key=open("agent.pem").read())
config = MiddlewareConfig(..., agent_private_key={"kty": "RSA", ...})
```

Only RS256 is supported today (matches portal-generated keys). The key is never transmitted; only the signed JWS is sent.

### Test mode

Pass `test_mode=True` to short-circuit the live auth flow during local development. Every authority check returns `ALLOW`, no HTTP is made, and the emitted proof artifact carries `test_mode=True` with `authority_signature="test-mode-unverifiable"`. Test-mode proofs do not validate against production keys.

```python
config = MiddlewareConfig(
    api_url="https://accounts.nuggets.life",  # unused in test mode
    agent_id="agent-001",
    controller_id="org-001",
    delegation_id="del-001",
    test_mode=True,
)
```

## LangGraph Platform OIDC auth

Plug Nuggets OIDC into a deployed LangGraph agent so incoming user requests are authenticated against your Nuggets identity provider.

```python
from langchain_nuggets.langgraph import NuggetsAuth

nuggets = NuggetsAuth(issuer_url="https://auth.nuggets.life")
auth = nuggets.auth  # pass to langgraph.json
```

Pre-built authorization helpers:

```python
from langchain_nuggets.langgraph import require_scopes, ownership_filter
```

`require_scopes("email", "profile")` rejects requests missing the given OIDC scopes; `ownership_filter()` enforces per-user resource ownership on create/read/search.

## Self-hosted / private CA

Point the backend URLs at your own deployment and pass `ca_cert` to either constructor:

```python
config = MiddlewareConfig(
    api_url="https://nuggets.internal.example.com",
    oidc_issuer_url="https://oidc.internal.example.com",
    # ...
    ca_cert="/etc/ssl/private-ca/nuggets-ca.pem",
)

nuggets_auth = NuggetsAuth(
    issuer_url="https://oidc.internal.example.com",
    ca_cert="/etc/ssl/private-ca/nuggets-ca.pem",
)
```

Set `verify_ssl=False` to disable TLS verification (development only).

## Development

```bash
cd packages/python
pip install -e ".[dev,langgraph]"
pytest
```

### End-to-end smoke test against a live backend

Pre-create a delegation with your test tool in `allowed_capabilities`, then run from the repo root:

```bash
export NUGGETS_AUTHORITY_URL="https://accounts-dev.internal-nuggets.life"
export NUGGETS_OIDC_ISSUER_URL="https://auth-dev.internal-nuggets.life"
export NUGGETS_AGENT_ID="did:web:auth-dev.internal-nuggets.life:..."
export NUGGETS_CONTROLLER_ID="did:web:auth-dev.internal-nuggets.life:..."
export NUGGETS_DELEGATION_ID="42"
export NUGGETS_AGENT_PRIVATE_KEY="/path/to/agent-jwks.json"
export NUGGETS_TOOL="your_tool_name"   # any capability listed in the delegation's allowed_capabilities

python scripts/smoke_test_authority.py
```

Exits 0 when the backend returns `ALLOW` and a proof artifact is emitted. See [`scripts/demo_deployed_scenarios.py`](./scripts/demo_deployed_scenarios.py) for the full ALLOW + 5 DENY walkthrough.

## License

[MIT](./LICENSE)
