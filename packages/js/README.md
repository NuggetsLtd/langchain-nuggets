# @nuggetslife/langchain-nuggets

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

This package is under active porting. The first public-ready milestone is parity with the Python package for bearer minting, `agent_proof` signing, authority evaluation, proof verification, and emitted proof artifacts.
