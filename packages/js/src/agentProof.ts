import { readFileSync } from "node:fs";
import { existsSync } from "node:fs";
import { SignJWT, importJWK, importPKCS8 } from "jose";
import { randomUUID } from "node:crypto";
import type { JWK } from "jose";
import type { PrivateKeyInput, SigningKey } from "./types.js";

const PROOF_TTL_SECONDS = 300;

function isPem(value: string): boolean {
  return value.trimStart().startsWith("-----BEGIN");
}

function isPrivateRsaJwk(jwk: JWK): boolean {
  return jwk.kty === "RSA" && typeof jwk.d === "string";
}

/**
 * Pick the signing key from a JWK or JWKS: the first private RSA key. A JWKS may
 * legitimately list a public key (or a non-RSA key) before the usable private
 * one, so we scan rather than blindly taking `keys[0]`.
 */
function selectPrivateRsaJwk(value: JWK | { keys: JWK[] }): JWK {
  const candidates = "keys" in value ? value.keys : [value];
  if (!Array.isArray(candidates) || candidates.length === 0) {
    throw new Error("agentPrivateKey JWKS contains no keys");
  }
  const jwk = candidates.find(isPrivateRsaJwk);
  if (!jwk) {
    throw new Error("agentPrivateKey must contain a private RSA key (kty=RSA with a 'd' parameter)");
  }
  return jwk;
}

export async function loadPrivateKey(value: PrivateKeyInput): Promise<SigningKey> {
  if (typeof value === "string") {
    if (isPem(value)) {
      return importPKCS8(value, "RS256");
    }
    if (existsSync(value)) {
      const content = readFileSync(value, "utf8");
      if (isPem(content)) {
        return importPKCS8(content, "RS256");
      }
      const parsed = JSON.parse(content) as JWK | { keys: JWK[] };
      return loadPrivateKey(parsed);
    }
    throw new Error("agentPrivateKey must be a PEM string, existing file path, JWK, or JWKS");
  }

  return importJWK(selectPrivateRsaJwk(value), "RS256") as Promise<SigningKey>;
}

export async function signAgentProof(
  privateKey: SigningKey,
  agentId: string,
  nonce: string
): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  return new SignJWT({ agent_id: agentId, nonce })
    .setProtectedHeader({ alg: "RS256" })
    .setIssuedAt(now)
    .setExpirationTime(now + PROOF_TTL_SECONDS)
    .sign(privateKey);
}

export async function signAgentProofV1(
  privateKey: SigningKey,
  input: {
    agentId: string;
    nonce: string;
    audience: string;
    actionContextHash: string;
  }
): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  return new SignJWT({
    agent_id: input.agentId,
    nonce: input.nonce,
    action_context_version: 1,
    action_context_hash: input.actionContextHash
  })
    .setProtectedHeader({ alg: "RS256" })
    .setAudience(input.audience)
    .setJti(randomUUID())
    .setIssuedAt(now)
    .setExpirationTime(now + PROOF_TTL_SECONDS)
    .sign(privateKey);
}
