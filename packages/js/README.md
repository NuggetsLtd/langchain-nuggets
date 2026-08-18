# @nuggetslife/langchain-nuggets

[![CI](https://github.com/NuggetsLtd/langchain-nuggets/actions/workflows/ci.yml/badge.svg)](https://github.com/NuggetsLtd/langchain-nuggets/actions/workflows/ci.yml)
[![npm](https://img.shields.io/npm/v/@nuggetslife/langchain-nuggets.svg)](https://www.npmjs.com/package/@nuggetslife/langchain-nuggets)
[![node](https://img.shields.io/node/v/@nuggetslife/langchain-nuggets.svg)](https://www.npmjs.com/package/@nuggetslife/langchain-nuggets)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/NuggetsLtd/langchain-nuggets/blob/main/LICENSE)

TypeScript Authority middleware for LangChain.js / LangGraph.js.

This package is a JS/TS port of the Python `langchain-nuggets` Authority middleware. It checks each tool call with the Nuggets Authority endpoint before execution, fails closed on `DENY` or verification errors, and emits signed proof artifacts for allowed actions.

Every non-test request carries an agent-signed, versioned RFC 8785 hash of the exact tool action. The authority's signed response must return that same locally recomputed hash, the agent audience, and a valid bounded lifetime before the wrapped tool can execute. `delegationId` must be a canonical positive decimal row ID such as `"42"`.

```bash
npm install @nuggetslife/langchain-nuggets
```

```ts
import { MiddlewareConfig, NuggetsAuthorityMiddleware } from "@nuggetslife/langchain-nuggets";

const config = new MiddlewareConfig({
  apiUrl: "https://accounts.nuggets.life",
  oidcIssuerUrl: "https://auth.nuggets.life",
  agentId: "did:web:auth.nuggets.life:your-agent-id",
  controllerId: "did:nuggets:oidc:your-controller-id",
  delegationId: "42",
  agentPrivateKey: "/secrets/agent-jwks.json"
});

const middleware = new NuggetsAuthorityMiddleware(config);
```

Wire `middleware.wrapToolCall` into a LangGraph `ToolNode`.

## With `createAgent`

For the LangChain.js `createAgent` API, install `langchain` (an optional peer dependency) and use the adapter from the `/agent` entry point — same config, same enforcement:

```bash
npm install langchain
```

```ts
import { createAgent } from "langchain";
import { createNuggetsAuthorityMiddleware } from "@nuggetslife/langchain-nuggets/agent";

const middleware = createNuggetsAuthorityMiddleware(config); // MiddlewareConfig or plain object

const agent = createAgent({
  model,
  tools,
  middleware: [middleware]
});

// emitted proofs
for (const proof of middleware.proofs) {
  console.log(proof.proof_id, proof.tool);
}
```

The core `NuggetsAuthorityMiddleware` import stays dependency-light (`@langchain/core` only); `langchain` is required only when you use the `/agent` adapter.

## Payments & approvals

For monetary tools, supply an **action-context resolver** to attach the payment `amount_minor` (minor units, integer) and `currency` (ISO-4217, uppercase) to the signed action. The resolver is the *only* source of money fields — they are never inferred from tool args — and `NUGGETS_TOOL` / the tool name must **exactly match** the delegation capability (e.g. `nuggets.payments.send`).

```ts
const config = new MiddlewareConfig({
  // ...
  actionContextResolver: (toolName, args) => ({
    amount_minor: 500,           // £5.00
    currency: "GBP",
    target: "did:web:merchant"   // optional; overrides the args-derived target
  })
});
```

`amount_minor` and `currency` are validated as a pair — supply both or neither. Invalid money fields (negative/non-integer amount, non-`^[A-Z]{3}$` currency, one without the other) fail **closed** with an `ERROR` `ToolMessage` before the tool runs.

**ESCALATE (human approval).** When the authority requires approval it returns `ESCALATE`. The middleware verifies the signed decision — exactly as it does for `ALLOW` — then returns a `PENDING_APPROVAL` `ToolMessage`. This is **not** an error, and the wrapped tool never runs:

```json
{ "status": "PENDING_APPROVAL", "approval_id": 500, "reason_code": "APPROVAL_REQUIRED", "proof_id": "...", "signature": "..." }
```

Operational boundary:

- **No payment handler runs** on `PENDING_APPROVAL` — nothing is executed or charged.
- The **application owns polling/redeem** of the approval, out-of-band, using `approval_id`.
- `approval_id` is a **server-issued handle, not part of the signed receipt** — treat it as an opaque identifier, not a cryptographically verified field. (The ESCALATE *decision* signature is verified.)

## Live smoke test

End-to-end check against a deployed backend (mirrors the Python `scripts/smoke_test_authority.py`). Pre-create a delegation with your test tool in `allowed_capabilities`, then from `packages/js`:

```bash
npm run build
export NUGGETS_AUTHORITY_URL="https://accounts.nuggets.life"
export NUGGETS_OIDC_ISSUER_URL="https://auth.nuggets.life"
export NUGGETS_AGENT_ID="did:web:auth.nuggets.life:..."
export NUGGETS_CONTROLLER_ID="..."
export NUGGETS_DELEGATION_ID="10"
export NUGGETS_AGENT_PRIVATE_KEY="/path/to/agent-jwks.json"   # or PEM
export NUGGETS_TOOL="your_tool_name"   # an in-scope allowed_capability
export NUGGETS_AMOUNT_MINOR="500"      # optional; 500 = £5.00 — exercises payment routing
export NUGGETS_CURRENCY="GBP"          # optional; ISO-4217, uppercase
node scripts/smoke-test-authority.mjs
```

Exits 0 when the backend returns `ALLOW` and a verified proof artifact is emitted, or on `ESCALATE` (`PENDING_APPROVAL`); the handler is a no-op and never executes a payment.

**Key hygiene.** Keep the private JWKS in a secret store or mounted secret — never in source control, logs, or `Downloads`; treat any previously downloaded key as stale. For demos and smoke runs, use a **disposable, scoped delegation** and a freshly downloaded key, and **revoke both** afterwards.

This package is at parity with the Python `langchain-nuggets` package — bearer minting, `agent_proof` signing, authority evaluation, discover-and-pin proof verification, and emitted proof artifacts — and has been validated end-to-end against a live backend.

## License

[MIT](./LICENSE)

## Trademarks

`@nuggetslife/langchain-nuggets` is an independent, community-maintained integration and is not affiliated with, sponsored by, or endorsed by LangChain, Inc. "LangChain" and "LangGraph" are trademarks of LangChain, Inc. All other trademarks are the property of their respective owners.
