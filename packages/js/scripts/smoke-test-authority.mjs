#!/usr/bin/env node
/**
 * End-to-end smoke test against a deployed Nuggets authority backend.
 *
 * Mirrors scripts/smoke_test_authority.py. Confirms the TypeScript SDK can mint
 * an OIDC token, sign the agent_proof, reach the live authority endpoint, get an
 * ALLOW, and verify the returned proof. Exits 0 on ALLOW + emitted proof.
 *
 * Build first, then run with the same env contract as the Python smoke:
 *
 *   cd packages/js && npm run build
 *   export NUGGETS_AUTHORITY_URL="https://accounts.nuggets.life"
 *   export NUGGETS_OIDC_ISSUER_URL="https://auth.nuggets.life"
 *   export NUGGETS_AGENT_ID="did:web:auth.nuggets.life:..."
 *   export NUGGETS_CONTROLLER_ID="..."
 *   export NUGGETS_DELEGATION_ID="10"
 *   export NUGGETS_AGENT_PRIVATE_KEY="/path/to/agent-jwks.json"   # or PEM
 *   export NUGGETS_TOOL="your_tool_name"   # an in-scope allowed_capability
 *   export NUGGETS_TARGET="optional-in-scope-target"
 *   node scripts/smoke-test-authority.mjs
 */
import { readFileSync } from "node:fs";
import { ToolMessage } from "@langchain/core/messages";
import { MiddlewareConfig, NuggetsAuthorityMiddleware } from "../dist/index.js";

function env(name, required = true) {
  const value = process.env[name];
  if (required && (!value || value.length === 0)) {
    console.error(`Missing required env var: ${name}`);
    process.exit(2);
  }
  return value;
}

function loadKey(raw) {
  // Accept a PEM string, a path to a PEM/JWK/JWKS file, or inline JSON.
  if (raw.trimStart().startsWith("-----BEGIN") || raw.trimStart().startsWith("{")) {
    return raw.trimStart().startsWith("{") ? JSON.parse(raw) : raw;
  }
  const content = readFileSync(raw, "utf8");
  return content.trimStart().startsWith("{") ? JSON.parse(content) : content;
}

const config = new MiddlewareConfig({
  apiUrl: env("NUGGETS_AUTHORITY_URL"),
  oidcIssuerUrl: env("NUGGETS_OIDC_ISSUER_URL"),
  agentId: env("NUGGETS_AGENT_ID"),
  controllerId: env("NUGGETS_CONTROLLER_ID"),
  delegationId: env("NUGGETS_DELEGATION_ID"),
  agentPrivateKey: loadKey(env("NUGGETS_AGENT_PRIVATE_KEY"))
});

const tool = env("NUGGETS_TOOL");
const target = env("NUGGETS_TARGET", false);

const middleware = new NuggetsAuthorityMiddleware(config);
const request = {
  tool_call: { name: tool, args: target ? { target } : {}, id: "smoke-call" }
};
const handler = async () =>
  new ToolMessage({ content: JSON.stringify({ status: "ok" }), tool_call_id: "smoke-call" });

console.log(`→ ${config.apiUrl}${config.authorityEndpoint}  tool=${tool}${target ? ` target=${target}` : ""}`);

const result = await middleware.wrapToolCall(request, handler);
const content = result instanceof ToolMessage ? String(result.content) : JSON.stringify(result);

let parsed;
try {
  parsed = JSON.parse(content);
} catch {
  parsed = { status: "ok" };
}

if (parsed.status === "DENIED" || parsed.status === "ERROR") {
  console.error(`✗ ${parsed.status}: ${parsed.reason_code ?? ""} ${parsed.message ?? ""}`);
  process.exit(1);
}

const proof = middleware.proofs.at(-1);
if (!proof) {
  console.error("✗ ALLOW but no proof artifact was emitted");
  process.exit(1);
}
console.log(`✓ ALLOW — proof ${proof.proof_id} (${proof.latency_ms.toFixed(0)}ms), verified against the authority's published keys`);
process.exit(0);
