# Agent Provisioning Runbook

End-to-end walkthrough for getting a new agent from "doesn't exist" to
"making authorized tool calls through `NuggetsAuthorityMiddleware`".

Covers two readers:

- **Tenant administrator** — uses the accounts portal to register an
  agent and grant it a delegation.
- **SDK integrator** — takes the artifacts from the administrator and
  wires them into `MiddlewareConfig`.

> The portal screens described below reflect the dev environment as of
> 2026-05. If the UI text shifts, update this doc in the same PR.

## Concepts in 30 seconds

- **Agent** — an OIDC client registered in the accounts portal. Each
  agent has a DID of the form `did:web:<oidc-host>:<client_id>` and an
  RS256 keypair. The public JWK is stored on the OIDC provider; the
  private JWK is downloaded once at creation and must be saved by the
  administrator.
- **Delegation** — a scoped grant from a *local* agent (the controller,
  owned by the tenant) to a *remote* agent (the SDK consumer's DID).
  Pins allowed actions, allowed targets, an expiry, and an invocation
  cap. Identified by a numeric `delegation_id`.
- **Controller** — the local agent that issues the delegation. Its DID
  becomes `controller_id` in the SDK config.
- **Authority endpoint** — `POST /api/authority/evaluate` on
  `accounts.nuggets.life`. The middleware calls this on
  every wrapped tool call and receives a signed ALLOW/DENY decision.

## Part 1 — Administrator: provision the agent in the portal

### 1.1 Sign in

Log into `https://accounts.nuggets.life` as a user with
"manage agents" permissions on the target tenant account. Navigate to
**AI → Agents**.

### 1.2 Create the agent

1. Click **Create**.
2. Enter an **Agent Name** (free-form; shown in the dashboard).
3. Submit. The portal generates an RS256 keypair, registers the public
   JWK on the OIDC provider, and stores the agent under the tenant.
4. You are redirected to the agent's detail page and a one-time
   **Download Key** modal opens — save the JSON to disk immediately.
   The private JWK is shown **once**; closing the modal without saving
   means the agent must be re-created.

The downloaded file is a JWKS document of the form:

```json
{
  "keys": [
    {"kty": "RSA", "alg": "RS256", "use": "sig", "kid": "...", "d": "...", ...}
  ]
}
```

### 1.3 Record the agent's DID

On the agent detail page, the **Decentralised Identifier (DID)** field
shows the agent's DID — `did:web:auth.nuggets.life:<client_id>`.
Copy it; the SDK integrator needs both the full DID (for `agent_id`)
and the bare `<client_id>` is derived automatically by the SDK.

### 1.4 Create the delegation

Navigate to **AI → Delegations** and click **Allow Agent**.

Field reference:

| Field | What goes here |
|-------|----------------|
| **Remote Agent** | The DID of the agent that will be making calls (typically the agent you just created if testing within one tenant, or another tenant's agent DID if granting cross-org access). |
| **Local Agent** | Dropdown — pick the agent in *your* tenant that acts as the controller/issuer. |
| **Allowed Actions** | Comma-separated capability strings. Must include every tool name the SDK will wrap — these are arbitrary identifiers you choose to match the tools in your own LangChain/LangGraph application. |
| **Allowed Services** | Comma-separated target strings. Leave blank for "any target". When set, every SDK call must pass a matching `target` argument. |
| **Access Expires** | Optional `datetime-local`. Leave blank for "never". |
| **Max Calls** | Integer invocation cap (defaults to 10). Each ALLOW decrements; once exhausted, every subsequent request is DENY'd with `CAP_EXCEEDED_INVOCATIONS`. |

Submit. The new row appears in the delegations table.

### 1.5 Copy the runtime bundle

Each row exposes two copy buttons:

- **Copy token** — the delegation VC (JWS signed by the portal),
  bound to `(controller_did, remote_agent_did)`. Used as
  `delegation_token` in the SDK if you prefer to pass the VC directly
  rather than the numeric ID.
- **Copy bundle** — JSON containing `delegation_id`, `delegation_token`,
  `allowed_capabilities`, `allowed_targets`, `expires_at`, and `caps`.
  This is the canonical hand-off to the SDK integrator.

The `delegation_id` from the bundle is what the SDK uses by default.

## Part 2 — SDK integrator: wire the artifacts

### 2.1 Required artifacts

From the administrator you should have received:

- The agent's private JWKS file (`agent-jwks.json` or similar).
- The agent's full DID — the `agent_id`.
- The controller (local agent) DID — the `controller_id`. Visible on
  the delegation row in the portal.
- The `delegation_id` (numeric) from the runtime bundle.
- The environment URLs:
  - Accounts portal: `https://accounts.nuggets.life`
  - OIDC issuer: `https://auth.nuggets.life`

### 2.2 Configure `MiddlewareConfig`

```python
from langchain_nuggets.middleware import MiddlewareConfig, NuggetsAuthorityMiddleware

config = MiddlewareConfig(
    api_url="https://accounts.nuggets.life",
    oidc_issuer_url="https://auth.nuggets.life",
    agent_id="did:web:auth.nuggets.life:<client_id>",
    controller_id="did:web:auth.nuggets.life:<controller_client_id>",
    delegation_id="42",
    agent_private_key="/secrets/agent-jwks.json",  # path, inline PEM, or dict
)

middleware = NuggetsAuthorityMiddleware(config)
```

`agent_private_key` accepts:

- A filesystem path to a PEM file or a JSON file containing a JWK or JWKS
- A raw PEM string
- A `dict` JWK or JWKS

Keep this value out of source — load from an env var, secret store, or
KMS-mounted file. The middleware uses it both to sign `agent_proof` JWS
on every request and to obtain OIDC access tokens via
`client_credentials`.

### 2.3 Wire into LangGraph

```python
from langgraph.prebuilt import ToolNode

tool_node = ToolNode(
    tools=tools,
    wrap_tool_call=middleware.wrap_tool_call,
)
```

That's the entire integration — no per-tool changes.

### 2.4 Verify end-to-end

Run the smoke test from the repo root:

```bash
export NUGGETS_AUTHORITY_URL="https://accounts.nuggets.life"
export NUGGETS_OIDC_ISSUER_URL="https://auth.nuggets.life"
export NUGGETS_AGENT_ID="did:web:auth.nuggets.life:..."
export NUGGETS_CONTROLLER_ID="did:web:auth.nuggets.life:..."
export NUGGETS_DELEGATION_ID="42"
export NUGGETS_AGENT_PRIVATE_KEY="/secrets/agent-jwks.json"
export NUGGETS_TOOL="your_tool_name"   # any capability you listed under Allowed Actions
export NUGGETS_TARGET="your_target"    # required when Allowed Services is set; otherwise omit
export NUGGETS_AMOUNT_MINOR="500"      # optional; minor units (500 = £5.00) — for payment capabilities
export NUGGETS_CURRENCY="GBP"          # optional; ISO-4217, uppercase — pair with NUGGETS_AMOUNT_MINOR

python scripts/smoke_test_authority.py
```

Expected output ends with `OK` and a proof_id (or `PENDING_APPROVAL`
with an `approval_id` when the decision is `ESCALATE`). The smoke handler
is a no-op — it never executes a payment. Anything else points at one of
the cases in the next section.

`NUGGETS_AMOUNT_MINOR` / `NUGGETS_CURRENCY` are supplied together via an
action-context resolver; they are the only source of the payment amount and
currency (never inferred from tool args). A currency-scoped, amount-capped
GBP delegation treats a call with **no** `amount_minor` / `currency` as out of
currency scope and rejects it — set both when testing such a delegation.

> **Disposable keys and delegations.** For smoke runs and demos, use a
> short-lived, **scoped** delegation and a **freshly downloaded** key, and
> **revoke both** once testing is done. Keep the private JWKS in a secret
> store or mounted secret — never in source control, logs, or `Downloads`;
> treat any previously downloaded key as stale.

### 2.5 Walk through the full scenario suite (optional)

`scripts/demo_deployed_scenarios.py` runs ALLOW + the five DENY
variants (out-of-scope tool, out-of-scope target, cap exhausted,
expired, revoked) plus a proof readout against a deployed backend.
Requires four pre-provisioned delegations — setup steps are at the
top of that file. Useful for demos and pre-release smoke runs.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `401 invalid_client` from the OIDC token endpoint | Public JWK on the OIDC provider doesn't match the private key the SDK is using. | Re-create the agent in the portal and reuse the freshly downloaded JWKS. The portal stores the public key only at registration time. |
| `AGENT_PROOF_INVALID` in the authority response | `agent_id` in `MiddlewareConfig` doesn't match the DID the private key was issued to, OR the key file is malformed. | Confirm the DID shown on the agent detail page exactly matches `agent_id`. Validate the JWKS file parses as JSON. |
| `TOOL_NOT_IN_SCOPE` | The tool name passed to the LLM isn't in the delegation's **Allowed Actions**. | Either add the tool name to the delegation in the portal, or rename the LangChain tool to match what was granted. |
| `TARGET_NOT_IN_SCOPE` | The tool call's `target` argument isn't in **Allowed Services**, or the call didn't pass a `target` at all. | Add the target to the delegation, leave Allowed Services blank for "any", or include `target=` in the tool's arguments. |
| `CAP_EXCEEDED_INVOCATIONS` | The delegation's **Max Calls** has been hit. | Increase the cap by editing the delegation, or create a new one. There is no auto-reset. |
| `CAP_EXCEEDED_AMOUNT` | The call's `amount_minor` exceeds the delegation's amount cap. | Lower the amount, or raise the delegation's cap. Large amounts may return `ESCALATE` (human approval) rather than a hard deny — see the payments notes in the READMEs. |
| Out-of-currency-scope deny | A currency-scoped, amount-capped delegation received a call with no `amount_minor` / `currency`. | Supply both via the action-context resolver (`NUGGETS_AMOUNT_MINOR` + `NUGGETS_CURRENCY` in the smoke test). |
| `DELEGATION_EXPIRED` / `DELEGATION_REVOKED` | The delegation's **Access Expires** has passed, or someone clicked Revoke. | Issue a new delegation. Revoked delegations can't be reactivated. |
| `STALE_TIMESTAMP` | System clock skew between SDK host and the authority backend is > 5 minutes. | Sync the SDK host's clock (NTP). |
| `nonce has already been used` (401) | The SDK reused an `action.nonce` — should not happen with stock middleware. | File a bug with the captured request body. |

## Rotation and revocation

Both are portal operations today; no SDK or API changes are required.

- **Rotate an agent's key** — there is no in-place rotation. Create a
  new agent, hand off the new JWKS + DID, and re-issue any delegations
  that pointed at the old DID. Revoke the old delegations once the new
  agent is in use.
- **Revoke a delegation** — open **AI → Delegations**, find the row,
  click **Revoke**. The change is effective immediately; the next
  authority call returns `DELEGATION_REVOKED`.

## What's *not* covered

- Self-service agent registration via API — not yet exposed.
- On-prem or self-hosted Nuggets deployment.
- Multi-tenant key escrow.
