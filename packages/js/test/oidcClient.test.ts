import { generateKeyPair, jwtVerify } from "jose";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OidcClientCredentialsClient, OidcTokenError, extractOidcClientId } from "../src/oidcClient.js";
import type { SigningKey } from "../src/types.js";

const keys = await generateKeyPair("RS256", { extractable: true });
const privateKey = keys.privateKey as SigningKey;
const publicKey = keys.publicKey;

interface MockCall {
  url: string;
  init?: RequestInit;
}

function mockFetch(responses: Array<() => Response>): { fetchImpl: typeof fetch; calls: MockCall[] } {
  const calls: MockCall[] = [];
  let i = 0;
  const fetchImpl = (async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    const make = responses[Math.min(i, responses.length - 1)];
    i += 1;
    return make();
  }) as unknown as typeof fetch;
  return { fetchImpl, calls };
}

const tokenOk = (token = "tok-1") =>
  new Response(JSON.stringify({ access_token: token, expires_in: 3600 }), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });

function makeClient(fetchImpl: typeof fetch, extra?: { resource?: string }) {
  return new OidcClientCredentialsClient({
    issuerUrl: "https://auth.test",
    clientId: "did:web:auth.test:abc",
    privateKey,
    fetchImpl,
    resource: extra?.resource
  });
}

function bodyString(init?: RequestInit): string {
  const body = init?.body;
  if (body instanceof URLSearchParams) return body.toString();
  return String(body);
}

describe("buildClientAssertion", () => {
  it("builds a JWS with the correct private_key_jwt claims", async () => {
    const { fetchImpl } = mockFetch([tokenOk]);
    const assertion = await makeClient(fetchImpl).buildClientAssertion();
    const { payload } = await jwtVerify(assertion, publicKey, { audience: "https://auth.test/token" });
    expect(payload.iss).toBe("did:web:auth.test:abc");
    expect(payload.sub).toBe("did:web:auth.test:abc");
    expect(payload.aud).toBe("https://auth.test/token");
    expect(String(payload.jti)).toHaveLength(36);
    expect(payload.exp!).toBeGreaterThan(payload.iat!);
  });

  it("uses a fresh jti per call", async () => {
    const { fetchImpl } = mockFetch([tokenOk]);
    const client = makeClient(fetchImpl);
    const [a, b] = await Promise.all([client.buildClientAssertion(), client.buildClientAssertion()]);
    const jti = (jws: string) => JSON.parse(Buffer.from(jws.split(".")[1], "base64url").toString()).jti;
    expect(jti(a)).not.toBe(jti(b));
  });
});

describe("token exchange", () => {
  it("exchanges the assertion for an access token with the expected form fields", async () => {
    const { fetchImpl, calls } = mockFetch([tokenOk]);
    const token = await makeClient(fetchImpl).getAccessToken();
    expect(token).toBe("tok-1");
    const form = bodyString(calls.at(-1)!.init);
    expect(form).toContain("grant_type=client_credentials");
    expect(form).toContain("client_assertion=");
    expect(form).toContain("scope=authority.evaluate");
  });

  it("omits resource when unset", async () => {
    const { fetchImpl, calls } = mockFetch([tokenOk]);
    await makeClient(fetchImpl).getAccessToken();
    expect(bodyString(calls.at(-1)!.init)).not.toContain("resource=");
  });

  it("includes resource when set", async () => {
    const { fetchImpl, calls } = mockFetch([tokenOk]);
    await makeClient(fetchImpl, { resource: "https://accounts.test/api/authority" }).getAccessToken();
    const form = new URLSearchParams(bodyString(calls.at(-1)!.init));
    expect(form.get("resource")).toBe("https://accounts.test/api/authority");
  });

  it("caches the token until near expiry", async () => {
    const { fetchImpl, calls } = mockFetch([tokenOk]);
    const client = makeClient(fetchImpl);
    const a = await client.getAccessToken();
    const b = await client.getAccessToken();
    expect(a).toBe(b);
    expect(calls).toHaveLength(1);
  });

  it("refreshes when the token is about to expire", async () => {
    vi.useFakeTimers();
    try {
      const { fetchImpl, calls } = mockFetch([() => tokenOk("tok-1"), () => tokenOk("tok-2")]);
      const client = makeClient(fetchImpl);
      expect(await client.getAccessToken()).toBe("tok-1");
      vi.advanceTimersByTime(3_580_000); // past expires_in(3600) - refresh window(30)
      expect(await client.getAccessToken()).toBe("tok-2");
      expect(calls).toHaveLength(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("raises OidcTokenError with the OAuth error code on failure", async () => {
    const { fetchImpl } = mockFetch([
      () => new Response(JSON.stringify({ error: "invalid_client" }), { status: 401 })
    ]);
    await expect(makeClient(fetchImpl).getAccessToken()).rejects.toMatchObject({
      name: "OidcTokenError",
      statusCode: 401
    });
  });

  it("never leaks the raw provider body in the error", async () => {
    const { fetchImpl } = mockFetch([
      () => new Response("<html>internal server secret leak</html>", { status: 500 })
    ]);
    await expect(makeClient(fetchImpl).getAccessToken()).rejects.toThrow(
      /^(?!.*internal server secret leak).*$/s
    );
  });

  it("raises on a non-JSON 200 response", async () => {
    const { fetchImpl } = mockFetch([() => new Response("not-json", { status: 200 })]);
    await expect(makeClient(fetchImpl).getAccessToken()).rejects.toBeInstanceOf(OidcTokenError);
  });

  it("raises when access_token is missing", async () => {
    const { fetchImpl } = mockFetch([
      () => new Response(JSON.stringify({ expires_in: 3600 }), { status: 200 })
    ]);
    await expect(makeClient(fetchImpl).getAccessToken()).rejects.toThrow(/access_token/);
  });
});

describe("authenticated post", () => {
  it("includes the bearer token and JSON content-type", async () => {
    const { fetchImpl, calls } = mockFetch([
      tokenOk,
      () => new Response(JSON.stringify({ decision: "ALLOW" }), { status: 200 })
    ]);
    await makeClient(fetchImpl).post("https://api.test/api/authority/evaluate", { x: 1 });
    const headers = new Headers(calls.at(-1)!.init!.headers);
    expect(headers.get("Authorization")).toBe("Bearer tok-1");
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("ignores a caller-supplied Authorization but keeps other headers", async () => {
    const { fetchImpl, calls } = mockFetch([
      tokenOk,
      () => new Response(JSON.stringify({ decision: "ALLOW" }), { status: 200 })
    ]);
    await makeClient(fetchImpl).post(
      "https://api.test/api/authority/evaluate",
      { x: 1 },
      { Authorization: "Bearer attacker", "Idempotency-Key": "k1" }
    );
    const headers = new Headers(calls.at(-1)!.init!.headers);
    expect(headers.get("Authorization")).toBe("Bearer tok-1");
    expect(headers.get("Idempotency-Key")).toBe("k1");
  });
});

describe("extractOidcClientId", () => {
  it("strips the did:nuggets:oidc: prefix", () => {
    expect(extractOidcClientId("did:nuggets:oidc:sUn1Fcj")).toBe("sUn1Fcj");
  });
  it("returns the last segment of a did:web", () => {
    expect(extractOidcClientId("did:web:auth-dev.internal-nuggets.life:WhWeJ30e5")).toBe("WhWeJ30e5");
  });
  it("returns a bare id unchanged", () => {
    expect(extractOidcClientId("agent-001")).toBe("agent-001");
  });
});
