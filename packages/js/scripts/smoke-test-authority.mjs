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
 *   export NUGGETS_AMOUNT_MINOR="500"     # optional; minor units (e.g. 500 = £5.00)
 *   export NUGGETS_CURRENCY="GBP"         # optional; ISO-4217, uppercase
 *   node scripts/smoke-test-authority.mjs
 *
 * The handler is a no-op — this script NEVER executes a real payment. Amount/
 * currency are synthetic inputs to exercise ALLOW / ESCALATE / DENY routing.
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

const tool = env("NUGGETS_TOOL");
const target = env("NUGGETS_TARGET", false);
const amountMinor = env("NUGGETS_AMOUNT_MINOR", false);
const currency = env("NUGGETS_CURRENCY", false);

// Only supply an action-context resolver when a synthetic amount/currency is
// requested. Never guess money fields — the resolver is the sole source.
const actionContextResolver = (amountMinor || currency)
  ? () => ({
      ...(amountMinor ? { amount_minor: Number(amountMinor) } : {}),
      ...(currency ? { currency } : {}),
      ...(target ? { target } : {})
    })
  : undefined;

const config = new MiddlewareConfig({
  apiUrl: env("NUGGETS_AUTHORITY_URL"),
  oidcIssuerUrl: env("NUGGETS_OIDC_ISSUER_URL"),
  agentId: env("NUGGETS_AGENT_ID"),
  controllerId: env("NUGGETS_CONTROLLER_ID"),
  delegationId: env("NUGGETS_DELEGATION_ID"),
  agentPrivateKey: loadKey(env("NUGGETS_AGENT_PRIVATE_KEY")),
  actionContextResolver
});

const middleware = new NuggetsAuthorityMiddleware(config);
const request = {
  tool_call: { name: tool, args: target ? { target } : {}, id: "smoke-call" }
};
// No-op handler: it never performs a payment or any side effect.
const handler = async () =>
  new ToolMessage({ content: JSON.stringify({ status: "ok" }), tool_call_id: "smoke-call" });

console.log("NOTE: smoke handler is a no-op — it does NOT execute any payment.");
console.log(
  `→ ${config.apiUrl}${config.authorityEndpoint}  tool=${tool}` +
    `${target ? ` target=${target}` : ""}` +
    `${amountMinor || currency ? ` amount_minor=${amountMinor ?? "?"} currency=${currency ?? "?"}` : ""}`
);

const result = await middleware.wrapToolCall(request, handler);
const content = result instanceof ToolMessage ? String(result.content) : JSON.stringify(result);

let parsed;
try {
  parsed = JSON.parse(content);
} catch {
  parsed = { status: "ok" };
}

if (parsed.status === "PENDING_APPROVAL") {
  console.log(`⏸ ESCALATE — approval ${parsed.approval_id ?? "?"} (${parsed.reason_code ?? ""}); no tool executed, no payment made`);
  process.exit(0);
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
