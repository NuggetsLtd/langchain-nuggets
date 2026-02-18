# langchain-nuggets

Nuggets identity verification toolkit for LangChain Python. Provides 11 ready-to-use tools for KYC, KYA, and credential verification that plug directly into any LangChain agent.

## Installation

```bash
pip install langchain-nuggets
```

## Quick Start

```python
from langchain_nuggets import NuggetsToolkit

# Config via env vars: NUGGETS_API_URL, NUGGETS_PARTNER_ID, NUGGETS_PARTNER_SECRET
toolkit = NuggetsToolkit()
tools = toolkit.get_tools()

# Or pass config directly
toolkit = NuggetsToolkit(
    api_url="https://api.nuggets.life",
    partner_id="your-partner-id",
    partner_secret="your-secret",
)
```

## Tools

### KYC (Know Your Customer)

| Tool | Description |
|------|-------------|
| `initiate_kyc_verification` | Start identity verification flow, returns deeplink/QR for Nuggets app |
| `check_kyc_status` | Poll verification session status (pending/completed/failed/expired) |
| `verify_age` | Selective disclosure age proof without revealing date of birth |
| `verify_credential` | Request specific credential (address, email, phone, nationality) |

### KYA (Know Your Agent)

| Tool | Description |
|------|-------------|
| `register_agent_identity` | Register AI agent identity with DID and provenance signals |
| `verify_agent_identity` | Verify another agent's identity and provenance |
| `get_agent_trust_score` | Get trust score (0-1) based on verified signals |

### Auth & Credentials

| Tool | Description |
|------|-------------|
| `request_credential_presentation` | Ask user to present verifiable credentials |
| `verify_presentation` | Check presentation status and verify credentials |
| `initiate_oauth_flow` | Start OAuth 2.0/OIDC flow with Nuggets as IdP |
| `check_auth_status` | Check user's authentication and verification status |

## Usage with LangChain Agent

```python
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_nuggets import NuggetsToolkit

toolkit = NuggetsToolkit()
tools = toolkit.get_tools()

llm = ChatOpenAI(model="gpt-4o", temperature=0)
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant that can verify user identities using Nuggets."),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_openai_tools_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

result = executor.invoke({"input": "Verify alice@example.com"})
```

## Configuration

| Parameter | Env Variable | Description |
|-----------|-------------|-------------|
| `api_url` | `NUGGETS_API_URL` | Nuggets API base URL |
| `partner_id` | `NUGGETS_PARTNER_ID` | Your partner ID |
| `partner_secret` | `NUGGETS_PARTNER_SECRET` | Your partner secret |

## License

MIT
