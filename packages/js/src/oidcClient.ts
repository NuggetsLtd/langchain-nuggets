import { randomUUID } from "node:crypto";
import { SignJWT } from "jose";
import type { SigningKey } from "./types.js";

const DEFAULT_ASSERTION_TTL_SECONDS = 300;
const REFRESH_BEFORE_EXPIRY_SECONDS = 30;
const DEFAULT_MAX_TOKEN_ATTEMPTS = 3;
const DEFAULT_TOKEN_RETRY_DELAY_MS = 300;

interface CachedToken {
  accessToken: string;
  expiresAt: number;
}

export class OidcTokenError extends Error {
  statusCode: number;

  constructor(message: string, statusCode: number) {
    super(message);
    this.name = "OidcTokenError";
    this.statusCode = statusCode;
  }
}

export interface OidcClientCredentialsClientInput {
  issuerUrl: string;
  clientId: string;
  privateKey: SigningKey;
  scope?: string;
  resource?: string;
  fetchImpl?: typeof fetch;
  /** Attempts for a token request before giving up. Default 3. */
  maxTokenAttempts?: number;
  /** Base backoff between token retries, multiplied by the attempt number. Default 300ms. */
  retryDelayMs?: number;
}

export class OidcClientCredentialsClient {
  private issuerUrl: string;
  private tokenEndpoint: string;
  private clientId: string;
  private privateKey: SigningKey;
  private scope: string;
  private resource?: string;
  private token?: CachedToken;
  private fetchImpl: typeof fetch;
  private maxTokenAttempts: number;
  private retryDelayMs: number;

  constructor(input: OidcClientCredentialsClientInput) {
    this.issuerUrl = input.issuerUrl.replace(/\/+$/, "");
    this.tokenEndpoint = `${this.issuerUrl}/token`;
    this.clientId = input.clientId;
    this.privateKey = input.privateKey;
    this.scope = input.scope ?? "authority.evaluate";
    this.resource = input.resource;
    this.fetchImpl = input.fetchImpl ?? fetch;
    this.maxTokenAttempts = normalizeAttempts(input.maxTokenAttempts);
    this.retryDelayMs = normalizeDelayMs(input.retryDelayMs);
  }

  async buildClientAssertion(): Promise<string> {
    const now = Math.floor(Date.now() / 1000);
    return new SignJWT({})
      .setProtectedHeader({ alg: "RS256" })
      .setIssuer(this.clientId)
      .setSubject(this.clientId)
      .setAudience(this.tokenEndpoint)
      .setIssuedAt(now)
      .setExpirationTime(now + DEFAULT_ASSERTION_TTL_SECONDS)
      .setJti(randomUUID())
      .sign(this.privateKey);
  }

  private tokenIsFresh(): boolean {
    if (!this.token) {
      return false;
    }
    return this.token.expiresAt > Date.now() / 1000 + REFRESH_BEFORE_EXPIRY_SECONDS;
  }

  async getAccessToken(): Promise<string> {
    if (this.tokenIsFresh()) {
      return this.token!.accessToken;
    }

    // Retry transient failures (network errors, 5xx) so a one-off blip at the
    // token endpoint does not surface as a hard error before the agent can even
    // request an authority decision. A 4xx (auth/config) or malformed response
    // is not retried. If the endpoint stays unreachable we still throw, so the
    // caller fails closed.
    let lastError: unknown;
    for (let attempt = 1; attempt <= this.maxTokenAttempts; attempt++) {
      try {
        return await this.requestToken();
      } catch (error) {
        lastError = error;
        if (attempt >= this.maxTokenAttempts || !isTransientTokenError(error)) {
          throw error;
        }
        await delay(this.retryDelayMs * attempt);
      }
    }
    // The loop always returns or throws; this only satisfies the type checker.
    throw lastError instanceof Error
      ? lastError
      : new OidcTokenError("OIDC token exchange failed", 0);
  }

  private async requestToken(): Promise<string> {
    // A fresh assertion (and jti) per attempt keeps replay protection happy.
    const form = new URLSearchParams({
      grant_type: "client_credentials",
      client_assertion_type: "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
      client_assertion: await this.buildClientAssertion(),
      scope: this.scope
    });
    if (this.resource) {
      form.set("resource", this.resource);
    }

    let response: Response;
    try {
      response = await this.fetchImpl(this.tokenEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: form
      });
    } catch {
      // A rejected fetch is a network/transport failure. Surface it as a
      // transient OidcTokenError (statusCode 0) so the retry loop can retry it.
      // Errors thrown earlier (e.g. signing the assertion) are not caught here,
      // so they propagate and are not retried.
      throw new OidcTokenError("token endpoint request failed", 0);
    }
    const body = await decodeTokenEndpointResponse(response);
    const accessToken = body.access_token;
    if (typeof accessToken !== "string" || accessToken.length === 0) {
      throw new OidcTokenError("token endpoint response missing 'access_token' string", 200);
    }
    const expiresIn = Number(body.expires_in ?? 3600);
    if (!Number.isFinite(expiresIn)) {
      throw new OidcTokenError("token endpoint response has invalid 'expires_in' value", 200);
    }
    this.token = {
      accessToken,
      expiresAt: Date.now() / 1000 + expiresIn
    };
    return accessToken;
  }

  async post(url: string, body: unknown, headers?: Record<string, string>): Promise<unknown> {
    const token = await this.getAccessToken();
    const merged = mergeHeaders(token, headers);
    const response = await this.fetchImpl(url, {
      method: "POST",
      headers: merged,
      body: JSON.stringify(body)
    });
    return decodeJsonResponse(response);
  }
}

function isTransientTokenError(error: unknown): boolean {
  // Retry only transient failures: a network/transport error (surfaced as an
  // OidcTokenError with statusCode 0) or a 5xx from the provider. A 4xx
  // (auth/config) or a malformed response (statusCode 200) is terminal, and
  // anything that is not an OidcTokenError (e.g. a signing error) is not
  // retried.
  if (error instanceof OidcTokenError) {
    return error.statusCode === 0 || error.statusCode >= 500;
  }
  return false;
}

function normalizeAttempts(value: number | undefined): number {
  if (value === undefined || !Number.isFinite(value)) {
    return DEFAULT_MAX_TOKEN_ATTEMPTS;
  }
  return Math.max(1, Math.floor(value));
}

function normalizeDelayMs(value: number | undefined): number {
  if (value === undefined || !Number.isFinite(value)) {
    return DEFAULT_TOKEN_RETRY_DELAY_MS;
  }
  return Math.max(0, value);
}

function delay(ms: number): Promise<void> {
  if (ms <= 0) {
    return Promise.resolve();
  }
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function decodeTokenEndpointResponse(response: Response): Promise<Record<string, unknown>> {
  if (response.status >= 400) {
    let errorCode = "unknown_error";
    try {
      const body = (await response.json()) as Record<string, unknown>;
      if (typeof body.error === "string") {
        errorCode = body.error;
      }
    } catch {
      // Surface only status and OAuth error code, never raw provider body.
    }
    throw new OidcTokenError(
      `OIDC token exchange failed (status ${response.status}, error=${errorCode})`,
      response.status
    );
  }
  try {
    const parsed = await response.json();
    if (typeof parsed !== "object" || parsed === null) {
      throw new OidcTokenError("OIDC token endpoint returned a malformed response", response.status);
    }
    return parsed as Record<string, unknown>;
  } catch (exc) {
    if (exc instanceof OidcTokenError) {
      throw exc;
    }
    throw new OidcTokenError("OIDC token endpoint returned a non-JSON response", response.status);
  }
}

function mergeHeaders(token: string, extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = {};
  if (extra) {
    for (const [key, value] of Object.entries(extra)) {
      const lower = key.toLowerCase();
      if (lower === "authorization" || lower === "content-type") {
        continue;
      }
      headers[key] = value;
    }
  }
  headers["Content-Type"] = "application/json";
  headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function decodeJsonResponse(response: Response): Promise<unknown> {
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new OidcTokenError(
      response.status >= 400 ? `request failed with status ${response.status}` : "invalid JSON response",
      response.status
    );
  }
  if (response.status >= 400) {
    const message =
      data && typeof data === "object" && "message" in data && typeof data.message === "string"
        ? data.message
        : "request failed";
    throw new OidcTokenError(message, response.status);
  }
  return data;
}

export function extractOidcClientId(agentDid: string): string {
  if (agentDid.startsWith("did:nuggets:oidc:")) {
    return agentDid.slice("did:nuggets:oidc:".length);
  }
  if (agentDid.startsWith("did:web:")) {
    const segments = agentDid.split(":");
    if (segments.length >= 4) {
      return segments[segments.length - 1];
    }
  }
  return agentDid;
}
