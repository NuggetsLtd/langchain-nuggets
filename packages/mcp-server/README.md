# @nuggetslife/mcp-server

Nuggets identity verification as a [Model Context Protocol](https://modelcontextprotocol.io/) server. Exposes 11 identity tools (KYC, KYA, credentials, OAuth) to any MCP-compatible client — Claude Desktop, Cursor, LangChain agents via `langchain-mcp-adapters`, and more.

## Quick Start

### Claude Desktop / Cursor (stdio)

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

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

### SSE Mode (remote / langchain-mcp-adapters)

```bash
NUGGETS_API_URL=https://api.nuggets.life \
NUGGETS_PARTNER_ID=your-partner-id \
NUGGETS_PARTNER_SECRET=your-partner-secret \
PORT=3001 \
npx @nuggetslife/mcp-server/sse
```

Then connect from LangChain:

```typescript
import { MultiServerMCPClient } from "@langchain/mcp-adapters";

const client = new MultiServerMCPClient({
  nuggets: {
    transport: "sse",
    url: "http://localhost:3001/sse",
  },
});

const tools = await client.getTools();
```

### Programmatic Usage

```typescript
import { createNuggetsMcpServer } from "@nuggetslife/mcp-server";

const server = createNuggetsMcpServer({
  apiUrl: "https://api.nuggets.life",
  partnerId: "your-partner-id",
  partnerSecret: "your-partner-secret",
});
```

## Tools

| Tool | Category | Description |
|------|----------|-------------|
| `initiate_kyc_verification` | KYC | Start a KYC identity verification flow (returns deeplink/QR) |
| `check_kyc_status` | KYC | Check whether verification completed |
| `verify_age` | KYC | Selective disclosure — prove minimum age without revealing DOB |
| `verify_credential` | KYC | Verify a specific credential with selective disclosure |
| `register_agent_identity` | KYA | Register this agent's identity with Nuggets |
| `verify_agent_identity` | KYA | Verify another agent's identity |
| `get_agent_trust_score` | KYA | Get provenance signals and trust score for an agent |
| `request_credential_presentation` | Auth | Ask user to present verifiable credentials |
| `verify_presentation` | Auth | Verify presented credentials cryptographically |
| `initiate_oauth_flow` | Auth | Start OAuth/OIDC flow with Nuggets as IdP |
| `check_auth_status` | Auth | Check if a user is authenticated |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `NUGGETS_API_URL` | Yes | Nuggets API base URL |
| `NUGGETS_PARTNER_ID` | Yes | Your Nuggets partner ID |
| `NUGGETS_PARTNER_SECRET` | Yes | Your Nuggets partner secret |
| `PORT` | No | SSE server port (default: 3001) |

## SSE Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/sse` | GET | SSE connection endpoint |
| `/messages` | POST | MCP message handler |
| `/health` | GET | Health check |

## License

MIT
