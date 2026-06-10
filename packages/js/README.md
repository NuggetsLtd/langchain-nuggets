# @nuggetslife/langchain-nuggets

[![CI](https://github.com/NuggetsLtd/langchain-nuggets/actions/workflows/ci.yml/badge.svg)](https://github.com/NuggetsLtd/langchain-nuggets/actions/workflows/ci.yml)
[![npm](https://img.shields.io/npm/v/@nuggetslife/langchain-nuggets.svg)](https://www.npmjs.com/package/@nuggetslife/langchain-nuggets)
[![node](https://img.shields.io/node/v/@nuggetslife/langchain-nuggets.svg)](https://www.npmjs.com/package/@nuggetslife/langchain-nuggets)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/NuggetsLtd/langchain-nuggets/blob/main/LICENSE)

TypeScript Authority middleware for LangChain.js / LangGraph.js.

This package is a JS/TS port of the Python `langchain-nuggets` Authority middleware. It checks each tool call with the Nuggets Authority endpoint before execution, fails closed on `DENY` or verification errors, and emits signed proof artifacts for allowed actions.

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

## Live smoke test

End-to-end check against a deployed backend (mirrors the Python `scripts/smoke_test_authority.py`). Pre-create a delegation with your test tool in `allowed_capabilities`, then from `packages/js`:

```bash
npm run build
export NUGGETS_AUTHORITY_URL="https://accounts-dev.internal-nuggets.life"
export NUGGETS_OIDC_ISSUER_URL="https://auth-dev.internal-nuggets.life"
export NUGGETS_AGENT_ID="did:web:auth-dev.internal-nuggets.life:..."
export NUGGETS_CONTROLLER_ID="..."
export NUGGETS_DELEGATION_ID="10"
export NUGGETS_AGENT_PRIVATE_KEY="/path/to/agent-jwks.json"   # or PEM
export NUGGETS_TOOL="your_tool_name"   # an in-scope allowed_capability
node scripts/smoke-test-authority.mjs
```

Exits 0 when the backend returns `ALLOW` and a verified proof artifact is emitted.

This package is under active porting. The first public-ready milestone is parity with the Python package for bearer minting, `agent_proof` signing, authority evaluation, proof verification, and emitted proof artifacts.
