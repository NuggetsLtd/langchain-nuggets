import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  NuggetsApiClient,
  NuggetsApiClientError,
} from "../../src/client/nuggets-api-client.js";
import type { NuggetsConfig } from "../../src/types.js";

const TEST_CONFIG: NuggetsConfig = {
  apiUrl: "https://api.nuggets.test",
  partnerId: "partner-123",
  partnerSecret: "secret-456",
};

function mockAuthResponse() {
  return new Response(
    JSON.stringify({ token: "test-access-token", expiresIn: 3600 }),
    { status: 200, headers: { "Content-Type": "application/json" } }
  );
}

function mockJsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("NuggetsApiClient", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("should create an instance with the provided config", () => {
    const client = new NuggetsApiClient(TEST_CONFIG);
    expect(client).toBeInstanceOf(NuggetsApiClient);
  });

  it("should make an authenticated GET request", async () => {
    const responseData = { id: "session-1", status: "pending" };

    fetchMock
      .mockResolvedValueOnce(mockAuthResponse())
      .mockResolvedValueOnce(mockJsonResponse(responseData));

    const client = new NuggetsApiClient(TEST_CONFIG);
    const result = await client.get("/kyc/sessions/session-1");

    expect(result).toEqual(responseData);

    // First call: authentication
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "https://api.nuggets.test/partner/auth",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          partnerId: "partner-123",
          partnerSecret: "secret-456",
        }),
      })
    );

    // Second call: actual GET request with auth header
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "https://api.nuggets.test/kyc/sessions/session-1",
      expect.objectContaining({
        method: "GET",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer test-access-token",
        },
      })
    );
  });

  it("should make an authenticated POST request", async () => {
    const requestBody = { callbackUrl: "https://example.com/callback" };
    const responseData = {
      sessionId: "session-2",
      deeplink: "nuggets://kyc/session-2",
      qrCodeUrl: "https://api.nuggets.test/qr/session-2",
    };

    fetchMock
      .mockResolvedValueOnce(mockAuthResponse())
      .mockResolvedValueOnce(mockJsonResponse(responseData));

    const client = new NuggetsApiClient(TEST_CONFIG);
    const result = await client.post("/kyc/sessions", requestBody);

    expect(result).toEqual(responseData);

    // First call: authentication
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "https://api.nuggets.test/partner/auth",
      expect.objectContaining({
        method: "POST",
      })
    );

    // Second call: actual POST request with body
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "https://api.nuggets.test/kyc/sessions",
      expect.objectContaining({
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer test-access-token",
        },
        body: JSON.stringify(requestBody),
      })
    );
  });

  it("should cache the auth token across multiple requests", async () => {
    const firstData = { result: "first" };
    const secondData = { result: "second" };

    fetchMock
      .mockResolvedValueOnce(mockAuthResponse()) // auth for first request
      .mockResolvedValueOnce(mockJsonResponse(firstData)) // first GET
      .mockResolvedValueOnce(mockJsonResponse(secondData)); // second GET (no auth needed)

    const client = new NuggetsApiClient(TEST_CONFIG);

    const result1 = await client.get("/first");
    const result2 = await client.get("/second");

    expect(result1).toEqual(firstData);
    expect(result2).toEqual(secondData);

    // Only 3 fetch calls total: 1 auth + 2 data requests
    // The token is cached and reused for the second request
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("should throw NuggetsApiClientError when authentication fails", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ message: "Unauthorized" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      })
    );

    const client = new NuggetsApiClient(TEST_CONFIG);

    await expect(client.get("/something")).rejects.toThrow(
      NuggetsApiClientError
    );

    // Reset for property checks
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ message: "Unauthorized" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      })
    );

    await expect(client.get("/something-else")).rejects.toMatchObject({
      code: "AUTH_FAILED",
      statusCode: 401,
    });
  });

  it("should throw NuggetsApiClientError when an API request fails", async () => {
    const errorResponse = {
      code: "NOT_FOUND",
      message: "Session not found",
    };

    fetchMock
      .mockResolvedValueOnce(mockAuthResponse())
      .mockResolvedValueOnce(mockJsonResponse(errorResponse, 404));

    const client = new NuggetsApiClient(TEST_CONFIG);

    await expect(client.get("/kyc/sessions/nonexistent")).rejects.toThrow(
      NuggetsApiClientError
    );

    // Reset for property checks
    fetchMock
      .mockResolvedValueOnce(mockAuthResponse())
      .mockResolvedValueOnce(mockJsonResponse(errorResponse, 404));

    const client2 = new NuggetsApiClient(TEST_CONFIG);

    await expect(
      client2.get("/kyc/sessions/nonexistent")
    ).rejects.toMatchObject({
      message: "Session not found",
      code: "NOT_FOUND",
      statusCode: 404,
    });
  });
});
