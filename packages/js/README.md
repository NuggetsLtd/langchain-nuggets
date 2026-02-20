# @nuggetslife/langchain

Nuggets identity verification toolkit for [LangChain.js](https://js.langchain.com/) — KYC, KYA, selective disclosure, and OAuth tools with full type safety and LLM-optimized descriptions.

## Installation

```bash
npm install @nuggetslife/langchain @langchain/core
```

## Quick Start

```typescript
import { NuggetsToolkit } from "@nuggetslife/langchain";

const toolkit = new NuggetsToolkit({
  apiUrl: "https://api.nuggets.life",
  partnerId: "your-partner-id",
  partnerSecret: "your-secret",
});

const tools = toolkit.getTools();
// → 11 LangChain tools ready for any agent
```

Or configure via environment variables:

```bash
export NUGGETS_API_URL=https://api.nuggets.life
export NUGGETS_PARTNER_ID=your-partner-id
export NUGGETS_PARTNER_SECRET=your-secret
```

```typescript
const toolkit = new NuggetsToolkit();
const tools = toolkit.getTools();
```

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

## Usage with an Agent

```typescript
import { ChatOpenAI } from "@langchain/openai";
import { AgentExecutor, createOpenAIToolsAgent } from "langchain/agents";
import { ChatPromptTemplate } from "@langchain/core/prompts";
import { NuggetsToolkit } from "@nuggetslife/langchain";

const toolkit = new NuggetsToolkit();
const tools = toolkit.getTools();
const llm = new ChatOpenAI({ model: "gpt-4o" });

const prompt = ChatPromptTemplate.fromMessages([
  ["system", "You are an identity verification assistant powered by Nuggets."],
  ["human", "{input}"],
  ["placeholder", "{agent_scratchpad}"],
]);

const agent = await createOpenAIToolsAgent({ llm, tools, prompt });
const executor = new AgentExecutor({ agent, tools });

const result = await executor.invoke({
  input: "Verify my identity. My email is alice@example.com.",
});
```

## Configuration

| Variable | Description |
|----------|-------------|
| `NUGGETS_API_URL` | Nuggets API endpoint |
| `NUGGETS_PARTNER_ID` | Partner ID from Nuggets portal |
| `NUGGETS_PARTNER_SECRET` | Partner secret key |


## Self-Hosted Deployment

Point the configuration to your own Nuggets instance:

```typescript
const toolkit = new NuggetsToolkit({
  apiUrl: "https://nuggets.internal.example.com/api",
  partnerId: "your-partner-id",
  partnerSecret: "your-secret",
});
```

### Custom CA Certificates

For self-hosted instances using a private CA, use Node.js's built-in mechanism:

```bash
NODE_EXTRA_CA_CERTS=/etc/ssl/private-ca/nuggets-ca.pem node your-agent.js
```

## License

MIT
