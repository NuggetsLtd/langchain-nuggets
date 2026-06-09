import { writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  SignJWT,
  exportJWK,
  exportPKCS8,
  generateKeyPair,
  jwtVerify
} from "jose";
import type { JWK } from "jose";
import { ToolMessage } from "@langchain/core/messages";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NuggetsAuthorityMiddleware } from "../src/authorityMiddleware.js";
import { resetProofVerificationCaches } from "../src/proofVerification.js";
import { MiddlewareConfig } from "../src/types.js";
import type { MiddlewareConfigInput } from "../src/types.js";

const agent = await generateKeyPair("RS256", { extractable: true });
const agentPem = await exportPKCS8(agent.privateKey);
const agentPublicKey = agent.publicKey;

function makeConfig(overrides: Partial<MiddlewareConfigInput> = {}): MiddlewareConfig {
  return new MiddlewareConfig({
    apiUrl: "https://api.nuggets.test",
    oidcIssuerUrl: "https://auth.nuggets.test",
    agentId: "agent-123",
    controllerId: "org-456",
    delegationId: "del-789",
    agentPrivateKey: agentPem,
    verifyProofs: false,
    ...overrides
  });
}

const allowResponse = () => ({
  decision: "ALLOW" as const,
  proof_id: "proof-xyz",
  signature: "sig-abc",
  reason_code: null,
  constraints_evaluated: ["tool_allowed", "target_allowed", "cap_remaining"]
});

/** ALLOW-returning client.post mock typed with the real (url, payload, headers) call shape. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const allowPost = () => vi.fn(async (_url: string, _payload: any, _headers: Record<string, string>) => allowResponse());

const denyResponse = () => ({
  decision: "DENY" as const,
  proof_id: "proof-xyz",
  signature: "sig-abc",
  reason_code: "POLICY_VIOLATION"
});

const request = () => ({
  tool_call: { name: "external_api_call", args: { target: "stripe", amount: 100 }, id: "call-123" }
});

const handler = () =>
  vi.fn(async () => new ToolMessage({ content: '{"status": "success", "id": "txn-456"}', tool_call_id: "call-123" }));

/** Inject a fake authenticated client whose post() returns/throws as configured. */
function withClient(mw: NuggetsAuthorityMiddleware, post: ReturnType<typeof vi.fn>) {
  (mw as unknown as { client: { post: typeof post } }).client = { post };
}

beforeEach(() => resetProofVerificationCaches());
afterEach(() => {
  vi.unstubAllGlobals();
  resetProofVerificationCaches();
});

describe("construction", () => {
  it("starts with an empty proofs list", () => {
    expect(new NuggetsAuthorityMiddleware(makeConfig()).proofs).toEqual([]);
  });
});

describe("ALLOW / DENY / ERROR routing", () => {
  it("executes the tool on ALLOW and returns its message", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig());
    const post = allowPost();
    withClient(mw, post);
    const h = handler();

    const result = (await mw.wrapToolCall(request(), h)) as ToolMessage;

    expect(h).toHaveBeenCalledOnce();
    expect(result.content).toContain("success");
  });

  it("emits a proof on ALLOW", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig());
    withClient(mw, allowPost());
    await mw.wrapToolCall(request(), handler());

    expect(mw.proofs).toHaveLength(1);
    expect(mw.proofs[0]).toMatchObject({
      proof_id: "proof-xyz",
      agent_id: "agent-123",
      tool: "external_api_call",
      authority_signature: "sig-abc"
    });
  });

  it("blocks the tool on DENY with reason_code", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig());
    withClient(mw, vi.fn(async () => denyResponse()));
    const h = handler();

    const result = (await mw.wrapToolCall(request(), h)) as ToolMessage;

    expect(h).not.toHaveBeenCalled();
    const data = JSON.parse(result.content as string);
    expect(data.status).toBe("DENIED");
    expect(data.tool).toBe("external_api_call");
    expect(data.reason_code).toBe("POLICY_VIOLATION");
  });

  it("fails closed with ERROR when the authority call throws", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig());
    withClient(mw, vi.fn(async () => { throw new Error("Network error"); }));
    const h = handler();

    const result = (await mw.wrapToolCall(request(), h)) as ToolMessage;

    expect(h).not.toHaveBeenCalled();
    const data = JSON.parse(result.content as string);
    expect(data.status).toBe("ERROR");
    expect(data.message).toContain("Network error");
  });

  it("invokes the proof callback on ALLOW", async () => {
    const onProof = vi.fn();
    const mw = new NuggetsAuthorityMiddleware(makeConfig({ onProof }));
    withClient(mw, allowPost());
    await mw.wrapToolCall(request(), handler());

    expect(onProof).toHaveBeenCalledOnce();
    expect(onProof.mock.calls[0][0].proof_id).toBe("proof-xyz");
  });

  it("accumulates proofs and tracks positive latency", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig());
    withClient(mw, allowPost());
    await mw.wrapToolCall(request(), handler());
    await mw.wrapToolCall(request(), handler());
    await mw.wrapToolCall(request(), handler());

    expect(mw.proofs).toHaveLength(3);
    expect(mw.proofs[0].latency_ms).toBeGreaterThanOrEqual(0);
  });
});

describe("request payload", () => {
  it("sends the parameters_hash in the action", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig());
    const post = allowPost();
    withClient(mw, post);
    await mw.wrapToolCall(request(), handler());

    const { createHash } = await import("node:crypto");
    const expectedHash = createHash("sha256").update('{"amount":100,"target":"stripe"}', "utf8").digest("hex");
    expect(post.mock.calls[0][1].action.parameters_hash).toBe(expectedHash);
  });

  it("sends a unique 36-char Idempotency-Key header per call", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig());
    const post = allowPost();
    withClient(mw, post);
    await mw.wrapToolCall(request(), handler());
    await mw.wrapToolCall(request(), handler());

    const k0 = post.mock.calls[0][2]["Idempotency-Key"];
    const k1 = post.mock.calls[1][2]["Idempotency-Key"];
    expect(k0).toHaveLength(36);
    expect(k0).not.toBe(k1);
  });

  it("sends a unique 36-char nonce in the action per call", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig());
    const post = allowPost();
    withClient(mw, post);
    await mw.wrapToolCall(request(), handler());
    await mw.wrapToolCall(request(), handler());

    const n0 = post.mock.calls[0][1].action.nonce;
    const n1 = post.mock.calls[1][1].action.nonce;
    expect(n0).toHaveLength(36);
    expect(n0).not.toBe(n1);
  });
});

describe("agent_proof", () => {
  it("sends an RS256 JWS that verifies with the agent public key", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig());
    const post = allowPost();
    withClient(mw, post);
    await mw.wrapToolCall(request(), handler());

    const payload = post.mock.calls[0][1];
    expect((payload.agent_proof as string).split(".")).toHaveLength(3);
    const { payload: decoded } = await jwtVerify(payload.agent_proof, agentPublicKey);
    expect(decoded.agent_id).toBe("agent-123");
    expect(decoded.nonce).toBe(payload.action.nonce);
    expect(decoded.exp!).toBeGreaterThan(decoded.iat!);
  });

  it("is fresh per call", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig());
    const post = allowPost();
    withClient(mw, post);
    await mw.wrapToolCall(request(), handler());
    await mw.wrapToolCall(request(), handler());
    expect(post.mock.calls[0][1].agent_proof).not.toBe(post.mock.calls[1][1].agent_proof);
  });

  it("accepts a JWK-dict private key", async () => {
    const jwk = (await exportJWK(agent.privateKey)) as JWK;
    const mw = new NuggetsAuthorityMiddleware(makeConfig({ agentPrivateKey: jwk }));
    const post = allowPost();
    withClient(mw, post);
    await mw.wrapToolCall(request(), handler());

    const { payload } = await jwtVerify(post.mock.calls[0][1].agent_proof, agentPublicKey);
    expect(payload.agent_id).toBe("agent-123");
  });

  it("accepts a file-path private key", async () => {
    const file = join(tmpdir(), `agent-${Date.now()}.pem`);
    writeFileSync(file, agentPem);
    const mw = new NuggetsAuthorityMiddleware(makeConfig({ agentPrivateKey: file }));
    const post = allowPost();
    withClient(mw, post);
    await mw.wrapToolCall(request(), handler());
    expect((post.mock.calls[0][1].agent_proof as string).split(".")).toHaveLength(3);
  });
});

describe("proof verification (default on, fails closed)", () => {
  it("downgrades an ALLOW with an unverifiable signature to PROOF_VERIFICATION_FAILED", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("no network"); }));
    const mw = new NuggetsAuthorityMiddleware(makeConfig({ verifyProofs: true }));
    withClient(mw, allowPost());
    const h = handler();

    const result = (await mw.wrapToolCall(request(), h)) as ToolMessage;

    expect(h).not.toHaveBeenCalled();
    const data = JSON.parse(result.content as string);
    expect(data.status).toBe("DENIED");
    expect(data.reason_code).toBe("PROOF_VERIFICATION_FAILED");
    expect(mw.proofs).toEqual([]);
  });

  it("passes through and emits a proof when the signature is a verifiable JWS", async () => {
    const portal = await generateKeyPair("RS256", { extractable: true });
    const portalJwk: JWK = { ...(await exportJWK(portal.publicKey)), kid: "portal-k1", alg: "RS256" };
    const issuer = "did:web:auth.nuggets.test:portalC1";
    const proofJws = await new SignJWT({
      proof_id: "proof-real",
      agent_id: "agent-123",
      controller_id: "org-456",
      constraints_evaluated: ["tool_allowed"],
      decision: "ALLOW",
      iss: issuer
    })
      .setProtectedHeader({ alg: "RS256", kid: "portal-k1" })
      .setIssuedAt()
      .sign(portal.privateKey);

    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("authority-configuration")) {
          return new Response(
            JSON.stringify({ issuer, jwks_uri: "https://api.nuggets.test/.well-known/jwks.json" }),
            { status: 200 }
          );
        }
        return new Response(JSON.stringify({ keys: [portalJwk] }), { status: 200 });
      })
    );

    const mw = new NuggetsAuthorityMiddleware(makeConfig({ verifyProofs: true }));
    withClient(
      mw,
      vi.fn(async () => ({
        decision: "ALLOW",
        proof_id: "proof-real",
        signature: proofJws,
        reason_code: null,
        constraints_evaluated: ["tool_allowed"]
      }))
    );
    const h = handler();

    const result = (await mw.wrapToolCall(request(), h)) as ToolMessage;

    expect(h).toHaveBeenCalledOnce();
    expect(result.content).toContain("success");
    expect(mw.proofs).toHaveLength(1);
  });
});

describe("test mode", () => {
  const testConfig = () =>
    new MiddlewareConfig({
      apiUrl: "https://unreachable.invalid",
      agentId: "agent-test",
      controllerId: "org-test",
      delegationId: "del-test",
      testMode: true
    });

  it("skips the HTTP call and runs the tool", async () => {
    const mw = new NuggetsAuthorityMiddleware(testConfig());
    const post = vi.fn();
    withClient(mw, post);
    const h = handler();

    const result = await mw.wrapToolCall(request(), h);

    expect(post).not.toHaveBeenCalled();
    expect(h).toHaveBeenCalledOnce();
    expect(result).toBeInstanceOf(ToolMessage);
  });

  it("marks the proof as test-mode and unverifiable", async () => {
    const mw = new NuggetsAuthorityMiddleware(testConfig());
    await mw.wrapToolCall(request(), handler());
    const proof = mw.proofs[0];
    expect(proof.test_mode).toBe(true);
    expect(proof.authority_signature).toBe("test-mode-unverifiable");
    expect(proof.proof_id.startsWith("test-")).toBe(true);
  });
});

describe("intent binding", () => {
  it("includes an intent_hash in the proof when an intent resolver is set", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig({ intentResolver: () => "transfer funds to user" }));
    withClient(mw, allowPost());
    await mw.wrapToolCall(request(), handler());
    expect(mw.proofs[0].intent_hash).toHaveLength(64);
  });

  it("has no intent_hash without a resolver", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig());
    withClient(mw, allowPost());
    await mw.wrapToolCall(request(), handler());
    expect(mw.proofs[0].intent_hash).toBeNull();
  });

  it("sends intent + intent_hash in the eval request", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig({ intentResolver: () => "transfer funds" }));
    const post = allowPost();
    withClient(mw, post);
    await mw.wrapToolCall(request(), handler());
    expect(post.mock.calls[0][1].action.intent).toBe("transfer funds");
    expect(post.mock.calls[0][1].action.intent_hash).not.toBeNull();
  });
});

describe("constraints_evaluated", () => {
  it("carries constraints from the response into the proof", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig());
    withClient(mw, allowPost());
    await mw.wrapToolCall(request(), handler());
    expect(mw.proofs[0].constraints_evaluated).toEqual(["tool_allowed", "target_allowed", "cap_remaining"]);
  });

  it("defaults to [] when the response omits them", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig());
    withClient(
      mw,
      vi.fn(async () => ({ decision: "ALLOW", proof_id: "proof-xyz", signature: "sig-abc", reason_code: null }))
    );
    await mw.wrapToolCall(request(), handler());
    expect(mw.proofs[0].constraints_evaluated).toEqual([]);
  });
});

describe("awrapToolCall", () => {
  it("delegates to wrapToolCall (ALLOW path)", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig());
    withClient(mw, allowPost());
    const h = handler();
    const result = (await mw.awrapToolCall(request(), h)) as ToolMessage;
    expect(h).toHaveBeenCalledOnce();
    expect(result.content).toContain("success");
  });
});
