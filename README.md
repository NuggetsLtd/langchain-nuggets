# langchain-nuggets

Nuggets identity verification for LangChain — KYC, KYA, selective disclosure, and OAuth across three integration layers.

## Architecture

| Layer | Package | Purpose | Languages |
|-------|---------|---------|-----------|
| **Native Toolkit** | [`@nuggetslife/langchain`](./packages/js) (npm) / [`langchain-nuggets`](./packages/python) (PyPI) | Optimized DX with full type safety | TypeScript, Python |
| **MCP Server** | [`@nuggetslife/mcp-server`](./packages/mcp-server) | Works with any MCP client (Claude Desktop, Cursor, etc.) | Any |
| **LangGraph Auth** | [`langchain-nuggets[langgraph]`](./packages/python/langchain_nuggets/langgraph) | Nuggets OIDC as auth backend for deployed agents | Python |
| **Authority Middleware** | [`langchain-nuggets`](./packages/python/langchain_nuggets/middleware) | Pre-execution trust enforcement for every tool call | Python |

## Quick Start

### TypeScript

```bash
npm install @nuggetslife/langchain @langchain/core
```

```typescript
import { NuggetsToolkit } from "@nuggetslife/langchain";

const toolkit = new NuggetsToolkit({
  apiUrl: "https://api.nuggets.life",
  partnerId: "your-partner-id",
  partnerSecret: "your-secret",
});

const tools = toolkit.getTools(); // 11 identity tools
```

### Python

```bash
pip install langchain-nuggets
```

```python
from langchain_nuggets import NuggetsToolkit

toolkit = NuggetsToolkit(
    api_url="https://api.nuggets.life",
    partner_id="your-partner-id",
    partner_secret="your-secret",
)

tools = toolkit.get_tools()  # 11 identity tools
```

### MCP Server (Claude Desktop / Cursor)

Add to your Claude Desktop config:

```json
{
  "mcpServers": {
    "nuggets": {
      "command": "npx",
      "args": ["@nuggetslife/mcp-server"],
      "env": {
        "NUGGETS_API_URL": "https://api.nuggets.life",
        "NUGGETS_PARTNER_ID": "your-partner-id",
        "NUGGETS_PARTNER_SECRET": "your-partner-secret"
      }
    }
  }
}
```

### LangGraph Auth Provider

```bash
pip install langchain-nuggets[langgraph]
```

```python
from langchain_nuggets.langgraph import NuggetsAuth

nuggets = NuggetsAuth(issuer_url="https://oidc.nuggets.life")
auth = nuggets.auth  # Pass to langgraph.json
```

See the [full example deployment](./examples/python/langgraph_auth_agent/).

### Authority Middleware

Intercept every tool call with Nuggets trust enforcement — validates authority, enforces policy, and emits cryptographic proof artifacts.

```python
from langchain_nuggets.middleware import NuggetsAuthorityMiddleware, MiddlewareConfig
from langgraph.prebuilt import ToolNode

config = MiddlewareConfig(
    api_url="https://api.nuggets.life",
    partner_id="your-partner-id",
    partner_secret="your-secret",
    agent_id="agent-001",
    controller_id="org-001",
    delegation_id="del-001",
)

middleware = NuggetsAuthorityMiddleware(config)

# Every tool call goes through Nuggets authority check
tool_node = ToolNode(
    tools=your_tools,
    wrap_tool_call=middleware.wrap_tool_call,
)

# After execution, inspect proof artifacts
for proof in middleware.proofs:
    print(f"{proof.proof_id}: {proof.tool} ({proof.latency_ms:.0f}ms)")
```

See the [demo script](./examples/python/authority_middleware_demo.py).

## Tools

### KYC (Know Your Customer)

| Tool | Description |
|------|-------------|
| `initiate_kyc_verification` | Start identity verification (returns deeplink/QR) |
| `check_kyc_status` | Check verification completion status |
| `verify_age` | Selective disclosure — prove minimum age without revealing DOB |
| `verify_credential` | Verify a specific credential with selective disclosure |

### KYA (Know Your Agent)

| Tool | Description |
|------|-------------|
| `register_agent_identity` | Register AI agent identity with provenance signals |
| `verify_agent_identity` | Verify another agent's identity |
| `get_agent_trust_score` | Get trust score and provenance signals (0–1) |

### Credential & Auth

| Tool | Description |
|------|-------------|
| `request_credential_presentation` | Ask user to present verifiable credentials |
| `verify_presentation` | Cryptographically verify presented credentials |
| `initiate_oauth_flow` | Start OAuth/OIDC flow with Nuggets as IdP |
| `check_auth_status` | Check user authentication and verification status |

## Examples

| Example | JS | Python | Description |
|---------|:--:|:------:|-------------|
| Basic KYC Agent | [link](./examples/js/basic-kyc-agent.ts) | [link](./examples/python/basic_kyc_agent.py) | Start KYC verification and check status |
| Multi-Agent Trust | [link](./examples/js/multi-agent-trust.ts) | [link](./examples/python/multi_agent_trust.py) | Register, verify, and score agent identities |
| Selective Disclosure | [link](./examples/js/selective-disclosure.ts) | [link](./examples/python/selective_disclosure.py) | Age verification and credential presentation |
| LangGraph Auth | — | [link](./examples/python/langgraph_auth_agent/) | Deployed agent with Nuggets OIDC auth |
| Authority Middleware | — | [link](./examples/python/authority_middleware_demo.py) | Pre-execution trust enforcement with proof artifacts |

## Configuration

All packages read configuration from environment variables:

| Variable | Description |
|----------|-------------|
| `NUGGETS_API_URL` | Nuggets API endpoint |
| `NUGGETS_PARTNER_ID` | Partner ID from Nuggets portal |
| `NUGGETS_PARTNER_SECRET` | Partner secret key |
| `NUGGETS_OIDC_ISSUER_URL` | OIDC issuer URL (LangGraph auth only) |


## Self-Hosted Deployment

All packages work with self-hosted Nuggets instances — point the environment variables to your infrastructure:

```bash
NUGGETS_API_URL=https://nuggets.internal.example.com/api
NUGGETS_OIDC_ISSUER_URL=https://nuggets.internal.example.com/oidc
NUGGETS_PARTNER_ID=your-partner-id
NUGGETS_PARTNER_SECRET=your-partner-secret
```

### Custom CA Certificates (Python)

If your instance uses a private CA, pass `ca_cert` to any constructor:

```python
from langchain_nuggets import NuggetsToolkit

toolkit = NuggetsToolkit(
    api_url="https://nuggets.internal.example.com/api",
    partner_id="your-partner-id",
    partner_secret="your-secret",
    ca_cert="/etc/ssl/private-ca/nuggets-ca.pem",
)
```

The same `ca_cert` and `verify_ssl` parameters are available on `NuggetsAuth`, `NuggetsAuthorityMiddleware`, and `NuggetsApiClient`.

To disable TLS verification entirely (development only):

```python
toolkit = NuggetsToolkit(..., verify_ssl=False)
```

### Custom CA Certificates (JS / MCP Server)

The JS toolkit uses the native `fetch` API. Trust a private CA via Node.js's built-in mechanism:

```bash
NODE_EXTRA_CA_CERTS=/etc/ssl/private-ca/nuggets-ca.pem node your-agent.js
```

For the MCP server in Claude Desktop config:

```json
{
  "mcpServers": {
    "nuggets": {
      "command": "npx",
      "args": ["@nuggetslife/mcp-server"],
      "env": {
        "NUGGETS_API_URL": "https://nuggets.internal.example.com/api",
        "NUGGETS_PARTNER_ID": "your-partner-id",
        "NUGGETS_PARTNER_SECRET": "your-secret",
        "NODE_EXTRA_CA_CERTS": "/etc/ssl/private-ca/nuggets-ca.pem"
      }
    }
  }
}
```
## Development

```bash
pnpm install
pnpm build
pnpm test
```

Python tests:

```bash
cd packages/python
pip install -e ".[dev,langgraph]"
pytest
```

## License

[MIT](./LICENSE)
