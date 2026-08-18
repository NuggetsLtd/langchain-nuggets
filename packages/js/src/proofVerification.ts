import { decodeJwt, decodeProtectedHeader, importJWK, jwtVerify, type JWK, type JWTPayload } from "jose";

export class ProofVerificationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ProofVerificationError";
  }
}

const CACHE_TTL_MS = 300_000;
const discoveryCache = new Map<string, { value: [string, string]; expiresAt: number }>();
const jwksCache = new Map<string, { value: JWK[]; expiresAt: number }>();

export function resetProofVerificationCaches(): void {
  discoveryCache.clear();
  jwksCache.clear();
}

export async function discoverAuthority(
  apiUrl: string,
  options?: { fetchImpl?: typeof fetch }
): Promise<[string, string]> {
  const cached = discoveryCache.get(apiUrl);
  if (cached && cached.expiresAt > Date.now()) {
    return cached.value;
  }

  const discoveryUrl = `${apiUrl.replace(/\/+$/, "")}/.well-known/authority-configuration`;
  const fetchImpl = options?.fetchImpl ?? fetch;
  let response: Response;
  try {
    response = await fetchImpl(discoveryUrl);
  } catch (exc) {
    throw new ProofVerificationError(`authority discovery failed for ${discoveryUrl}: ${exc}`);
  }

  if (response.status !== 200) {
    throw new ProofVerificationError(
      `authority discovery failed (${response.status}) for ${discoveryUrl}`
    );
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch (exc) {
    throw new ProofVerificationError(`authority discovery at ${discoveryUrl} is not JSON: ${exc}`);
  }

  const issuer = isRecord(body) && typeof body.issuer === "string" ? body.issuer : undefined;
  const jwksUri = isRecord(body) && typeof body.jwks_uri === "string" ? body.jwks_uri : undefined;
  if (!issuer || !jwksUri) {
    throw new ProofVerificationError(`authority discovery at ${discoveryUrl} missing issuer/jwks_uri`);
  }

  const discoveryOrigin = new URL(discoveryUrl).origin;
  const jwksOrigin = new URL(jwksUri).origin;
  if (jwksOrigin !== discoveryOrigin) {
    throw new ProofVerificationError(
      `discovery jwks_uri origin ${jwksOrigin} does not match api_url origin ${discoveryOrigin}`
    );
  }

  const value: [string, string] = [issuer, jwksUri];
  discoveryCache.set(apiUrl, { value, expiresAt: Date.now() + CACHE_TTL_MS });
  return value;
}

export interface VerifyAuthorityProofInput {
  signature: string;
  expected: Record<string, unknown>;
  issuer: string;
  jwksUri: string;
  fetchImpl?: typeof fetch;
}

export async function verifyAuthorityProof(input: VerifyAuthorityProofInput): Promise<JWTPayload> {
  const cached = jwksCache.get(input.jwksUri);
  const keys = cached && cached.expiresAt > Date.now()
    ? cached.value
    : await fetchJwks(input.jwksUri, input.fetchImpl ?? fetch);
  if (!cached || cached.expiresAt <= Date.now()) {
    jwksCache.set(input.jwksUri, { value: keys, expiresAt: Date.now() + CACHE_TTL_MS });
  }
  return verifyCore(input.signature, input.expected, input.issuer, keys);
}

async function fetchJwks(jwksUri: string, fetchImpl: typeof fetch): Promise<JWK[]> {
  let response: Response;
  try {
    response = await fetchImpl(jwksUri);
  } catch (exc) {
    throw new ProofVerificationError(`JWKS fetch failed for ${jwksUri}: ${exc}`);
  }
  if (response.status !== 200) {
    throw new ProofVerificationError(`JWKS fetch failed (${response.status}) for ${jwksUri}`);
  }
  let body: unknown;
  try {
    body = await response.json();
  } catch (exc) {
    throw new ProofVerificationError(`JWKS at ${jwksUri} is not JSON: ${exc}`);
  }
  const keys = isRecord(body) && Array.isArray(body.keys) ? body.keys : undefined;
  if (!keys || keys.length === 0) {
    throw new ProofVerificationError(`JWKS at ${jwksUri} has no keys`);
  }
  return keys as JWK[];
}

async function verifyCore(
  signature: string,
  expected: Record<string, unknown>,
  issuer: string,
  keys: JWK[]
): Promise<JWTPayload> {
  let claims: JWTPayload;
  try {
    claims = decodeJwt(signature);
  } catch (exc) {
    throw new ProofVerificationError(`proof is not a decodable JWS: ${exc}`);
  }
  if (!claims.iss) {
    throw new ProofVerificationError("proof has no iss claim");
  }
  if (claims.iss !== issuer) {
    throw new ProofVerificationError(`proof issuer mismatch: proof=${claims.iss} expected=${issuer}`);
  }

  let header: ReturnType<typeof decodeProtectedHeader>;
  try {
    header = decodeProtectedHeader(signature);
  } catch (exc) {
    throw new ProofVerificationError(`proof has an invalid protected header: ${exc}`);
  }
  const candidates = candidateKeys(keys, typeof header.kid === "string" ? header.kid : undefined);
  if (candidates.length === 0) {
    throw new ProofVerificationError("no usable key in JWKS");
  }

  let lastError: unknown;
  for (const jwk of candidates) {
    let key;
    try {
      key = await importJWK(jwk, "RS256");
    } catch (exc) {
      lastError = exc;
      continue;
    }
    const v1 = expected.action_context_version === 1;
    let verified;
    try {
      verified = await jwtVerify(signature, key, {
        algorithms: ["RS256"],
        issuer,
        ...(typeof expected.aud === "string" ? { audience: expected.aud } : {}),
        ...(v1 ? { requiredClaims: ["iat", "exp", "jti", "aud"] } : {})
      });
    } catch (exc) {
      if (
        typeof exc === "object" &&
        exc !== null &&
        "code" in exc &&
        exc.code === "ERR_JWS_SIGNATURE_VERIFICATION_FAILED"
      ) {
        lastError = exc;
        continue;
      }
      throw new ProofVerificationError(`proof claim validation failed: ${exc}`);
    }
    if (v1 &&
      (typeof verified.payload.iat !== "number" ||
        typeof verified.payload.exp !== "number" ||
        verified.payload.exp <= verified.payload.iat)) {
      throw new ProofVerificationError("proof has an invalid bounded lifetime");
    }
    bind(verified.payload, expected);
    return verified.payload;
  }
  throw new ProofVerificationError(`proof signature verification failed: ${lastError}`);
}

function candidateKeys(keys: JWK[], kid?: string): JWK[] {
  const objects = keys.filter((key) => key && typeof key === "object");
  if (!kid) {
    return objects;
  }
  return [
    ...objects.filter((key) => key.kid === kid),
    ...objects.filter((key) => key.kid !== kid)
  ];
}

function bind(claims: JWTPayload, expected: Record<string, unknown>): void {
  for (const field of [
    "decision",
    "proof_id",
    "agent_id",
    "controller_id",
    "aud",
    "action_context_version",
    "action_context_hash"
  ]) {
    if (field in expected && claims[field] !== expected[field]) {
      throw new ProofVerificationError(
        `proof ${field} mismatch: proof=${String(claims[field])} expected=${String(expected[field])}`
      );
    }
  }

  if ("constraints_evaluated" in expected) {
    const proofConstraints = Array.isArray(claims.constraints_evaluated)
      ? claims.constraints_evaluated
      : [];
    const expectedConstraints = Array.isArray(expected.constraints_evaluated)
      ? expected.constraints_evaluated
      : [];
    if (JSON.stringify(proofConstraints) !== JSON.stringify(expectedConstraints)) {
      throw new ProofVerificationError(
        `proof constraints_evaluated mismatch: proof=${JSON.stringify(
          proofConstraints
        )} expected=${JSON.stringify(expectedConstraints)}`
      );
    }
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
