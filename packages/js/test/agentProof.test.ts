import { writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { exportJWK, exportPKCS8, generateKeyPair, jwtVerify } from "jose";
import type { JWK } from "jose";
import { describe, expect, it } from "vitest";
import { loadPrivateKey, signAgentProof } from "../src/agentProof.js";

const kp = await generateKeyPair("RS256", { extractable: true });
const pem = await exportPKCS8(kp.privateKey);
const privateJwk = (await exportJWK(kp.privateKey)) as JWK;
const publicJwk = (await exportJWK(kp.publicKey)) as JWK;

describe("loadPrivateKey", () => {
  it("loads a PKCS8 PEM string", async () => {
    const key = await loadPrivateKey(pem);
    const jws = await signAgentProof(key, "agent-1", "nonce-1");
    await expect(jwtVerify(jws, kp.publicKey)).resolves.toBeTruthy();
  });

  it("loads a private RSA JWK", async () => {
    const key = await loadPrivateKey(privateJwk);
    const jws = await signAgentProof(key, "agent-1", "nonce-1");
    await expect(jwtVerify(jws, kp.publicKey)).resolves.toBeTruthy();
  });

  it("loads a PEM from a file path", async () => {
    const file = join(tmpdir(), `agentproof-${Date.now()}.pem`);
    writeFileSync(file, pem);
    const key = await loadPrivateKey(file);
    expect((await signAgentProof(key, "agent-1", "n")).split(".")).toHaveLength(3);
  });

  it("selects the first private RSA key from a JWKS even if a public key comes first", async () => {
    const jwks = { keys: [publicJwk, privateJwk] };
    const key = await loadPrivateKey(jwks);
    const jws = await signAgentProof(key, "agent-1", "nonce-1");
    await expect(jwtVerify(jws, kp.publicKey)).resolves.toBeTruthy();
  });

  it("rejects a JWKS with no usable private RSA key", async () => {
    await expect(loadPrivateKey({ keys: [publicJwk] })).rejects.toThrow(/private RSA/);
  });
});

describe("signAgentProof", () => {
  it("binds agent_id + nonce and sets iat/exp", async () => {
    const key = await loadPrivateKey(pem);
    const jws = await signAgentProof(key, "did:web:x:agent", "nonce-xyz");
    const { payload } = await jwtVerify(jws, kp.publicKey);
    expect(payload.agent_id).toBe("did:web:x:agent");
    expect(payload.nonce).toBe("nonce-xyz");
    expect(payload.exp!).toBeGreaterThan(payload.iat!);
  });
});
