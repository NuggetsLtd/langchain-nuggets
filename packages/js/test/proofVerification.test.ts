import { SignJWT, exportJWK, generateKeyPair } from "jose";
import type { JWK } from "jose";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  ProofVerificationError,
  discoverAuthority,
  resetProofVerificationCaches,
  verifyAuthorityProof
} from "../src/proofVerification.js";
import type { SigningKey } from "../src/types.js";

const API_URL = "https://accounts-dev.test";
const DISCOVERY_URI = `${API_URL}/.well-known/authority-configuration`;
const JWKS_URI = `${API_URL}/.well-known/jwks.json`;
const ISSUER = "did:web:auth-dev.test:sUn1FcjL6CHMm-aqB_kXV";
const KID = "portal-key-1";

const portal = await generateKeyPair("RS256", { extractable: true });
const portalPublicJwk: JWK = { ...(await exportJWK(portal.publicKey)), kid: KID, alg: "RS256" };

function jwks(...keys: JWK[]) {
  return new Response(JSON.stringify({ keys }), { status: 200 });
}

async function signProof(
  priv: SigningKey,
  overrides: Record<string, unknown> = {},
  kid: string | null = KID
): Promise<string> {
  const payload = {
    proof_id: "proof-1",
    agent_id: "did:web:auth-dev.test:agent1",
    controller_id: "did:web:auth-dev.test:ctrl1",
    delegation_id: "10",
    constraints_evaluated: ["not_revoked", "tool_allowed"],
    decision: "ALLOW",
    iss: ISSUER,
    ...overrides
  };
  const signer = new SignJWT(payload).setIssuedAt();
  signer.setProtectedHeader(kid === null ? { alg: "RS256" } : { alg: "RS256", kid });
  return signer.sign(priv);
}

const expected = (overrides: Record<string, unknown> = {}) => ({
  decision: "ALLOW",
  proof_id: "proof-1",
  agent_id: "did:web:auth-dev.test:agent1",
  controller_id: "did:web:auth-dev.test:ctrl1",
  constraints_evaluated: ["not_revoked", "tool_allowed"],
  ...overrides
});

function singleRoute(url: string, respond: () => Response) {
  let count = 0;
  const fetchImpl = (async (input: string | URL | Request) => {
    if (String(input) !== url) throw new Error(`unexpected fetch ${String(input)}`);
    count += 1;
    return respond();
  }) as unknown as typeof fetch;
  return { fetchImpl, calls: () => count };
}

const verify = (sig: string, exp: Record<string, unknown> = expected(), fetchImpl?: typeof fetch) =>
  verifyAuthorityProof({ signature: sig, expected: exp, issuer: ISSUER, jwksUri: JWKS_URI, fetchImpl });

beforeEach(() => resetProofVerificationCaches());
afterEach(() => resetProofVerificationCaches());

describe("discoverAuthority", () => {
  it("returns the issuer and jwks_uri", async () => {
    const { fetchImpl } = singleRoute(
      DISCOVERY_URI,
      () => new Response(JSON.stringify({ issuer: ISSUER, jwks_uri: JWKS_URI }), { status: 200 })
    );
    expect(await discoverAuthority(API_URL, { fetchImpl })).toEqual([ISSUER, JWKS_URI]);
  });

  it("caches discovery", async () => {
    const route = singleRoute(
      DISCOVERY_URI,
      () => new Response(JSON.stringify({ issuer: ISSUER, jwks_uri: JWKS_URI }), { status: 200 })
    );
    await discoverAuthority(API_URL, { fetchImpl: route.fetchImpl });
    await discoverAuthority(API_URL, { fetchImpl: route.fetchImpl });
    expect(route.calls()).toBe(1);
  });

  it("fails closed when discovery fetch fails", async () => {
    const { fetchImpl } = singleRoute(DISCOVERY_URI, () => new Response(null, { status: 503 }));
    await expect(discoverAuthority(API_URL, { fetchImpl })).rejects.toThrow(/authority discovery failed/);
  });

  it("rejects an off-host jwks_uri (SSRF guard)", async () => {
    const { fetchImpl } = singleRoute(
      DISCOVERY_URI,
      () =>
        new Response(JSON.stringify({ issuer: ISSUER, jwks_uri: "https://evil.test/jwks.json" }), {
          status: 200
        })
    );
    await expect(discoverAuthority(API_URL, { fetchImpl })).rejects.toThrow(/origin/);
  });

  it("rejects non-string discovery fields", async () => {
    const { fetchImpl } = singleRoute(
      DISCOVERY_URI,
      () => new Response(JSON.stringify({ issuer: 123, jwks_uri: JWKS_URI }), { status: 200 })
    );
    await expect(discoverAuthority(API_URL, { fetchImpl })).rejects.toThrow(/missing issuer\/jwks_uri/);
  });
});

describe("verifyAuthorityProof", () => {
  it("verifies a valid proof", async () => {
    const { fetchImpl } = singleRoute(JWKS_URI, () => jwks(portalPublicJwk));
    const claims = await verify(await signProof(portal.privateKey as SigningKey), expected(), fetchImpl);
    expect(claims.proof_id).toBe("proof-1");
    expect(claims.decision).toBe("ALLOW");
  });

  it("requires and binds the complete v1 action-proof envelope", async () => {
    const actionHash = "a".repeat(64);
    const now = Math.floor(Date.now() / 1000);
    const v1Expected = expected({
      aud: "did:web:auth-dev.test:agent1",
      action_context_version: 1,
      action_context_hash: actionHash
    });
    const { fetchImpl } = singleRoute(JWKS_URI, () => jwks(portalPublicJwk));
    const valid = await signProof(portal.privateKey as SigningKey, {
      aud: "did:web:auth-dev.test:agent1",
      jti: "proof-1",
      exp: now + 300,
      action_context_version: 1,
      action_context_hash: actionHash
    });
    expect((await verify(valid, v1Expected, fetchImpl)).action_context_hash).toBe(actionHash);

    resetProofVerificationCaches();
    const missingExpiry = await signProof(portal.privateKey as SigningKey, {
      aud: "did:web:auth-dev.test:agent1",
      jti: "proof-1",
      action_context_version: 1,
      action_context_hash: actionHash
    });
    await expect(verify(missingExpiry, v1Expected, fetchImpl)).rejects.toThrow();

    resetProofVerificationCaches();
    await expect(
      verify(valid, { ...v1Expected, action_context_hash: "b".repeat(64) }, fetchImpl)
    ).rejects.toThrow(/action_context_hash mismatch/);
  });

  it("rejects an issuer mismatch even when signed with the real key", async () => {
    const { fetchImpl } = singleRoute(JWKS_URI, () => jwks(portalPublicJwk));
    const sig = await signProof(portal.privateKey as SigningKey, { iss: "did:web:attacker.test:evil" });
    await expect(verify(sig, expected(), fetchImpl)).rejects.toThrow(/issuer mismatch/);
  });

  it("rejects a foreign-iss proof carrying a past exp at the issuer pin", async () => {
    const { fetchImpl } = singleRoute(JWKS_URI, () => jwks(portalPublicJwk));
    const sig = await signProof(portal.privateKey as SigningKey, {
      iss: "did:web:attacker.test:evil",
      exp: Math.floor(Date.now() / 1000) - 3600
    });
    await expect(verify(sig, expected(), fetchImpl)).rejects.toThrow(/issuer mismatch/);
  });

  it("rejects a proof signed by a key not in the JWKS (pinned iss, wrong key)", async () => {
    const attacker = await generateKeyPair("RS256", { extractable: true });
    const { fetchImpl } = singleRoute(JWKS_URI, () => jwks(portalPublicJwk));
    const sig = await signProof(attacker.privateKey as SigningKey);
    await expect(verify(sig, expected(), fetchImpl)).rejects.toThrow(/signature verification failed/);
  });

  it("fails closed when JWKS fetch fails", async () => {
    const { fetchImpl } = singleRoute(JWKS_URI, () => new Response(null, { status: 503 }));
    await expect(verify(await signProof(portal.privateKey as SigningKey), expected(), fetchImpl)).rejects.toThrow(
      /JWKS fetch failed/
    );
  });

  it("gives a clean error when no JWKS key is usable", async () => {
    const { fetchImpl } = singleRoute(
      JWKS_URI,
      () => new Response(JSON.stringify({ keys: [123, "nope"] }), { status: 200 })
    );
    await expect(verify(await signProof(portal.privateKey as SigningKey), expected(), fetchImpl)).rejects.toThrow(
      /no usable key/
    );
  });

  it("falls back to all keys when the kid does not match", async () => {
    const { fetchImpl } = singleRoute(JWKS_URI, () => jwks(portalPublicJwk));
    const sig = await signProof(portal.privateKey as SigningKey, {}, "unknown-kid");
    expect((await verify(sig, expected(), fetchImpl)).decision).toBe("ALLOW");
  });

  it("falls back to all keys when there is no kid", async () => {
    const { fetchImpl } = singleRoute(JWKS_URI, () => jwks(portalPublicJwk));
    const sig = await signProof(portal.privateKey as SigningKey, {}, null);
    expect((await verify(sig, expected(), fetchImpl)).decision).toBe("ALLOW");
  });

  it("verifies a rotated (retired-but-published) key", async () => {
    const retired = await generateKeyPair("RS256", { extractable: true });
    const retiredJwk: JWK = { ...(await exportJWK(retired.publicKey)), kid: "retired-k0", alg: "RS256" };
    const { fetchImpl } = singleRoute(JWKS_URI, () => jwks(retiredJwk, portalPublicJwk));
    const sig = await signProof(retired.privateKey as SigningKey, {}, "retired-k0");
    expect((await verify(sig, expected(), fetchImpl)).decision).toBe("ALLOW");
  });

  it("rejects a decision mismatch", async () => {
    const { fetchImpl } = singleRoute(JWKS_URI, () => jwks(portalPublicJwk));
    await expect(
      verify(await signProof(portal.privateKey as SigningKey), expected({ decision: "DENY" }), fetchImpl)
    ).rejects.toThrow(/decision mismatch/);
  });

  it("rejects a proof_id swap", async () => {
    const { fetchImpl } = singleRoute(JWKS_URI, () => jwks(portalPublicJwk));
    const sig = await signProof(portal.privateKey as SigningKey, { proof_id: "another-call" });
    await expect(verify(sig, expected(), fetchImpl)).rejects.toThrow(/proof_id mismatch/);
  });

  it("rejects a constraints_evaluated mismatch", async () => {
    const { fetchImpl } = singleRoute(JWKS_URI, () => jwks(portalPublicJwk));
    const sig = await signProof(portal.privateKey as SigningKey, { constraints_evaluated: ["not_revoked"] });
    await expect(verify(sig, expected(), fetchImpl)).rejects.toThrow(/constraints_evaluated mismatch/);
  });

  it("caches JWKS across calls", async () => {
    const route = singleRoute(JWKS_URI, () => jwks(portalPublicJwk));
    const sig = await signProof(portal.privateKey as SigningKey);
    await verify(sig, expected(), route.fetchImpl);
    await verify(sig, expected(), route.fetchImpl);
    expect(route.calls()).toBe(1);
  });

  it("wraps a malformed protected header as ProofVerificationError", async () => {
    const { fetchImpl } = singleRoute(JWKS_URI, () => jwks(portalPublicJwk));
    const real = await signProof(portal.privateKey as SigningKey);
    const parts = real.split(".");
    const corrupted = `@@@.${parts[1]}.${parts[2]}`; // valid payload (iss matches), garbage header
    await expect(verify(corrupted, expected(), fetchImpl)).rejects.toBeInstanceOf(ProofVerificationError);
  });

  it("throws ProofVerificationError on failure", async () => {
    const { fetchImpl } = singleRoute(JWKS_URI, () => new Response(null, { status: 503 }));
    await expect(verify(await signProof(portal.privateKey as SigningKey), expected(), fetchImpl)).rejects.toBeInstanceOf(
      ProofVerificationError
    );
  });
});
