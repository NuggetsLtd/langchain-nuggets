# langchain-nuggets

[![CI](https://github.com/NuggetsLtd/langchain-nuggets/actions/workflows/ci.yml/badge.svg)](https://github.com/NuggetsLtd/langchain-nuggets/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/langchain-nuggets.svg)](https://pypi.org/project/langchain-nuggets/)
[![Python versions](https://img.shields.io/pypi/pyversions/langchain-nuggets.svg)](https://pypi.org/project/langchain-nuggets/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/NuggetsLtd/langchain-nuggets/blob/main/LICENSE)

Authority middleware for LangChain / LangGraph — pre-execution trust enforcement on every tool call.

Wrap any `ToolNode` and the middleware calls the Nuggets authority endpoint before each tool executes. The backend evaluates a scoped delegation, returns an `ALLOW` or `DENY` decision, and signs an audit proof. Tools that aren't allowed never run.

## Installation

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
    agent_private_key="/secrets/agent-jwks.json",
)

middleware = NuggetsAuthorityMiddleware(config)

tool_node = ToolNode(
    tools=your_tools,
    wrap_tool_call=middleware.wrap_tool_call,
)
```

**Execution model:** `Agent → Tool Call → Nuggets Authority Check → Allow/Deny → Emit Proof`

**Trust primitives enforced:** Actor Identity, Authority (delegation), Policy, Intent, Consent, Accountability (provenance).

| Behaviour | Detail |
|-----------|--------|
| **ALLOW** | Tool executes; cryptographic proof artifact emitted |
| **DENY** | Tool blocked; structured error returned with `reason_code` |
| **ERROR** | Fail closed — tool not executed |

To provision the agent identity, private key, and delegation referenced above, see [the agent provisioning runbook](https://github.com/NuggetsLtd/langchain-nuggets/blob/main/docs/agent-provisioning.md).

### Agent private key

The accounts portal generates an RS256 keypair at agent creation and lets you download the private key as a JWKS file. `MiddlewareConfig.agent_private_key` accepts:

- A filesystem path to a PEM, JWK JSON, or JWKS JSON file
- A raw PEM string
- A JWK or JWKS dict

The key is never transmitted; only the signed `agent_proof` JWS is sent.

### Test mode

`test_mode=True` short-circuits the live auth flow during local development — every check returns `ALLOW`, no HTTP is made, and the emitted proof artifact is flagged as test-mode-unverifiable.

## LangGraph Platform OIDC auth

```python
from langchain_nuggets.langgraph import NuggetsAuth

nuggets = NuggetsAuth(issuer_url="https://auth.nuggets.life")
auth = nuggets.auth  # pass to langgraph.json
```

Pre-built authorization helpers:

```python
from langchain_nuggets.langgraph import require_scopes, ownership_filter
```

## Self-hosted / private CA

Point the URLs at your own deployment and pass `ca_cert` to either constructor:

```python
MiddlewareConfig(
    api_url="https://nuggets.internal.example.com",
    oidc_issuer_url="https://oidc.internal.example.com",
    # ...
    ca_cert="/etc/ssl/private-ca/nuggets-ca.pem",
)
```

Set `verify_ssl=False` to disable TLS verification (development only).

## License

MIT
