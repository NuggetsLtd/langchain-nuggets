<p align="center">
  <a href="https://nuggets.life"><img src="./docs/assets/nuggets-logo.svg" alt="Nuggets" height="104"></a>
</p>

# langchain-nuggets

[![CI](https://github.com/NuggetsLtd/langchain-nuggets/actions/workflows/ci.yml/badge.svg)](https://github.com/NuggetsLtd/langchain-nuggets/actions/workflows/ci.yml)
[![CodeQL](https://github.com/NuggetsLtd/langchain-nuggets/actions/workflows/codeql.yml/badge.svg)](https://github.com/NuggetsLtd/langchain-nuggets/actions/workflows/codeql.yml)
[![PyPI](https://img.shields.io/pypi/v/langchain-nuggets.svg)](https://pypi.org/project/langchain-nuggets/)
[![Python versions](https://img.shields.io/pypi/pyversions/langchain-nuggets.svg)](https://pypi.org/project/langchain-nuggets/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

Authority middleware for LangChain / LangGraph — pre-execution trust enforcement on every tool call.

Wrap any `ToolNode` and the middleware calls the Nuggets authority endpoint before each tool executes. The backend evaluates a scoped delegation, returns an `ALLOW` or `DENY` decision, and signs an audit proof. Tools that aren't allowed never run.

## Why Nuggets Authority?

Most agent middleware shapes *prompts* or guardrails *outputs*. Nuggets Authority governs *actions* — it answers "is this agent allowed to do **this**, right now, on whose authority?" before a tool ever runs, and leaves cryptographic proof that it did.

- **Pre-execution enforcement, not after-the-fact logging.** Every tool call is checked against a scoped delegation *before* it executes. Unauthorized calls never run — the middleware fails closed.
- **Cryptographic accountability.** Each decision is a signed, independently verifiable proof artifact — who acted, what they did, when, and under which authority. Proof verification is on by default and tamper-evident.
- **Authority you can scope and revoke.** Delegations are bound by capability, target, invocation cap, and expiry — issued and revoked in the Nuggets portal, enforced live by the backend.
- **Identity you can trust.** Every request is signed by the agent's key (RS256) and bound to its decentralized identifier (DID); the backend verifies ownership before deciding.
- **Drop-in for LangChain & LangGraph.** Works with both `ToolNode` and `create_agent` in a few lines — no changes to your tools.
- **Run it your way.** Hosted Nuggets, or self-hosted against your own deployment with a private CA.

Built on [Nuggets](https://nuggets.life) — the decentralized identity and verifiable-trust infrastructure already used for self-sovereign identity and verifiable credentials, now applied to AI agents.

### Beyond identity and policy

Enterprise identity (SSO) proves *who* an agent is. Operational policy and guardrail layers constrain *what* it may do and emit logs. Neither answers the question that matters for accountable agent actions: **who authorised this agent to take this specific action — and can anyone prove it afterwards?**

| Question | Identity / SSO | Policy / guardrails | Nuggets Authority |
|----------|:-:|:-:|:-:|
| Who is the user / agent? | ✅ | — | — |
| What may the agent access? | — | ✅ | — |
| **Who authorised this action?** | — | — | ✅ |
| **Was it within the delegated scope?** | — | — | ✅ |
| Evidence it produces | — | internal logs | cryptographic proof |
| Independently verifiable? | — | — | ✅ |
| Reveals only hashes, not raw data? | — | — | ✅ |

Nuggets **complements** your identity provider and policy layer rather than replacing them — authenticate and constrain as you do today, and Nuggets binds **delegated authority, intent, and a tamper-evident proof** to each action, enforced fail-closed before the tool runs. Proofs are signed and verifiable by any party against the authority's published keys — no callback to a Nuggets service required — and reference hashes of parameters and results, never the raw data.

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

### With `create_agent`

To use Authority as a LangChain `AgentMiddleware` (the `create_agent` API), install the `agent` extra:

```bash
pip install langchain-nuggets[agent]
```

```python
from langchain.agents import create_agent
from langchain_nuggets.middleware import NuggetsAuthorityAgentMiddleware, MiddlewareConfig

config = MiddlewareConfig(...)  # same config as above
middleware = NuggetsAuthorityAgentMiddleware(config)

agent = create_agent(
    model="...",
    tools=your_tools,
    middleware=[middleware],
)
```

Same enforcement as the `ToolNode` path — every tool call is checked before it runs, DENY/ERROR fail closed, ALLOW emits a signed proof (read them from `middleware.proofs`).

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

## Contributing

This package is maintained by the Nuggets team. Issues and pull requests are welcome — see [CONTRIBUTING.md](./CONTRIBUTING.md) for branch/PR conventions, local setup, and the live smoke test, and [SECURITY.md](./SECURITY.md) to report a vulnerability (please don't open public issues for security).

## About Nuggets

Nuggets provides decentralized identity and verifiable trust infrastructure for people and AI agents. Learn more at [nuggets.life](https://nuggets.life).

## License

[MIT](./LICENSE)
