# LangGraph Agent with Nuggets Auth

A LangGraph Platform deployment that uses Nuggets as the OIDC authentication backend. Users must authenticate via Nuggets before accessing the agent.

## How It Works

1. **Authentication**: When a request arrives, the `auth.py` handler extracts the Bearer token from the `Authorization` header and verifies it against the Nuggets OIDC provider's JWKS.

2. **KYC Gating**: With `require_kyc=True`, only users who have completed Nuggets KYC verification can access the agent.

3. **Agent Tools**: The agent has access to all 11 Nuggets identity tools (KYC, KYA, credentials, OAuth) for managing identity operations on behalf of the authenticated user.

## Setup

1. Copy the environment template:

   ```bash
   cp .env.example .env
   ```

2. Fill in your credentials in `.env`.

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Deploy with LangGraph CLI:

   ```bash
   langgraph up
   ```

## Architecture

```
Request with Bearer token
    │
    ▼
auth.py (NuggetsAuth)
    │
    ├─ Verify JWT via Nuggets OIDC JWKS
    ├─ Check KYC status via Partner API
    ├─ Return user identity to LangGraph
    │
    ▼
agent.py (ReAct agent)
    │
    ├─ 4 KYC tools (initiate, check, verify age, verify credential)
    ├─ 3 KYA tools (register, verify, trust score)
    └─ 4 Auth tools (credentials, presentation, OAuth, status)
```

## Files

| File | Purpose |
|------|---------|
| `langgraph.json` | LangGraph Platform deployment configuration |
| `auth.py` | Nuggets OIDC auth handler (3 lines of config) |
| `agent.py` | ReAct agent with Nuggets identity tools |
| `.env.example` | Environment variable template |
| `requirements.txt` | Python dependencies |

## Calling the Agent

Once deployed, authenticate requests with a Nuggets OIDC token:

```python
from langgraph_sdk import get_client

client = get_client(
    url="http://localhost:8123",
    headers={"Authorization": "Bearer <nuggets-oidc-token>"},
)

thread = await client.threads.create()
run = await client.runs.create(
    thread["thread_id"],
    "agent",
    input={"messages": [{"role": "user", "content": "Check my KYC status"}]},
)
```
