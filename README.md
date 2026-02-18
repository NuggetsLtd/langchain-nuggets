# langchain-nuggets

Nuggets identity verification toolkit for LangChain — KYC, KYA, selective disclosure, and OAuth.

## Packages

| Package | Registry | Description |
|---------|----------|-------------|
| [@nuggetslife/langchain](./packages/js) | npm | TypeScript toolkit for LangChain.js |

## Quick Start

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

// Get all 11 identity tools for your LangChain agent
const tools = toolkit.getTools();
```

## Tools

### KYC (Know Your Customer)
- `initiate_kyc_verification` — Start identity verification (returns deeplink/QR)
- `check_kyc_status` — Check verification completion status
- `verify_age` — Selective disclosure age proof (18+ without revealing DOB)
- `verify_credential` — Verify a specific credential type

### KYA (Know Your Agent)
- `register_agent_identity` — Register AI agent identity with provenance
- `verify_agent_identity` — Verify another agent's identity
- `get_agent_trust_score` — Get trust score and provenance signals

### Credential & Auth
- `request_credential_presentation` — Request verifiable credentials from user
- `verify_presentation` — Cryptographically verify presented credentials
- `initiate_oauth_flow` — Start OAuth/OIDC flow with Nuggets as IdP
- `check_auth_status` — Check user authentication and verification status

## MCP Integration

LangChain agents can also consume Nuggets via MCP:

```typescript
import { MultiServerMCPClient } from "@langchain/mcp-adapters";

const client = new MultiServerMCPClient({
  nuggets: {
    transport: "sse",
    url: "https://mcp.nuggets.life/sse",
    headers: { Authorization: "Bearer <token>" },
  },
});

const tools = await client.getTools();
```

## Configuration

| Env Variable | Description |
|---|---|
| `NUGGETS_API_URL` | Nuggets API endpoint |
| `NUGGETS_PARTNER_ID` | Partner ID from Nuggets portal |
| `NUGGETS_PARTNER_SECRET` | Partner secret key |

## Development

```bash
pnpm install
pnpm build
pnpm test
```

## License

MIT
