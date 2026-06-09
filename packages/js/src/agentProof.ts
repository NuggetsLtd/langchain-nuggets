import { readFileSync } from "node:fs";
import { existsSync } from "node:fs";
import { SignJWT, importJWK, importPKCS8 } from "jose";
import type { PrivateKeyInput, SigningKey } from "./types.js";

const PROOF_TTL_SECONDS = 300;

function isPem(value: string): boolean {
  return value.trimStart().startsWith("-----BEGIN");
}

function firstJwk(value: JsonWebKey | { keys: JsonWebKey[] }): JsonWebKey {
  if ("keys" in value) {
    if (!Array.isArray(value.keys) || value.keys.length === 0) {
      throw new Error("agentPrivateKey JWKS contains no keys");
    }
    return value.keys[0];
  }
  return value;
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
      const parsed = JSON.parse(content) as JsonWebKey | { keys: JsonWebKey[] };
      return loadPrivateKey(parsed);
    }
    throw new Error("agentPrivateKey must be a PEM string, existing file path, JWK, or JWKS");
  }

  const jwk = firstJwk(value);
  if (jwk.kty !== "RSA" || !("d" in jwk)) {
    throw new Error("agentPrivateKey JWK must be a private RSA key");
  }
  return importJWK(jwk, "RS256") as Promise<SigningKey>;
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
