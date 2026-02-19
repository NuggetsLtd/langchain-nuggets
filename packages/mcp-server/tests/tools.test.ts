import { describe, it, expect, vi, beforeEach } from "vitest";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { NuggetsApiClient } from "@nuggetslife/langchain";
import { registerTools } from "../src/tools.js";

function createMockClient(): NuggetsApiClient {
  return {
    get: vi.fn().mockResolvedValue({ ok: true }),
    post: vi.fn().mockResolvedValue({ ok: true }),
  } as unknown as NuggetsApiClient;
}

function createServerWithTools(client?: NuggetsApiClient) {
  const mockClient = client ?? createMockClient();
  const server = new McpServer({ name: "test", version: "0.0.1" });
  registerTools(server, mockClient);
  return { server, client: mockClient };
}

describe("registerTools", () => {
  it("should register exactly 11 tools", () => {
    const { server } = createServerWithTools();
    // Access internal registered tools map
    const tools = (server as any)._registeredTools;
    expect(Object.keys(tools)).toHaveLength(11);
  });

  it("should register all expected tool names", () => {
    const { server } = createServerWithTools();
    const tools = (server as any)._registeredTools;
    const names = Object.keys(tools);

    expect(names).toContain("initiate_kyc_verification");
    expect(names).toContain("check_kyc_status");
    expect(names).toContain("verify_age");
    expect(names).toContain("verify_credential");
    expect(names).toContain("register_agent_identity");
    expect(names).toContain("verify_agent_identity");
    expect(names).toContain("get_agent_trust_score");
    expect(names).toContain("request_credential_presentation");
    expect(names).toContain("verify_presentation");
    expect(names).toContain("initiate_oauth_flow");
    expect(names).toContain("check_auth_status");
  });

  it("should set descriptions on all tools", () => {
    const { server } = createServerWithTools();
    const tools = (server as any)._registeredTools;

    for (const [name, tool] of Object.entries(tools)) {
      expect((tool as any).description, `${name} should have a description`).toBeTruthy();
    }
  });
});

describe("KYC tool handlers", () => {
  let client: NuggetsApiClient;
  let server: McpServer;

  beforeEach(() => {
    const result = createServerWithTools();
    server = result.server;
    client = result.client;
  });

  it("initiate_kyc_verification calls POST /kyc/sessions", async () => {
    const mockResponse = { sessionId: "s1", deeplink: "nuggets://s1" };
    (client.post as any).mockResolvedValue(mockResponse);

    const tools = (server as any)._registeredTools;
    const handler = tools.initiate_kyc_verification.handler;
    const result = await handler({ userId: "user@test.com" }, {});

    expect(client.post).toHaveBeenCalledWith("/kyc/sessions", { userId: "user@test.com" });
    expect(result.content[0].type).toBe("text");
    expect(JSON.parse(result.content[0].text)).toEqual(mockResponse);
  });

  it("check_kyc_status calls GET /kyc/sessions/:id", async () => {
    const mockResponse = { sessionId: "s1", status: "completed" };
    (client.get as any).mockResolvedValue(mockResponse);

    const tools = (server as any)._registeredTools;
    const handler = tools.check_kyc_status.handler;
    const result = await handler({ sessionId: "s1" }, {});

    expect(client.get).toHaveBeenCalledWith("/kyc/sessions/s1");
    expect(JSON.parse(result.content[0].text)).toEqual(mockResponse);
  });

  it("verify_age calls POST /kyc/verify-age", async () => {
    const mockResponse = { sessionId: "age-1" };
    (client.post as any).mockResolvedValue(mockResponse);

    const tools = (server as any)._registeredTools;
    const handler = tools.verify_age.handler;
    const result = await handler({ userId: "user@test.com", minimumAge: 18 }, {});

    expect(client.post).toHaveBeenCalledWith("/kyc/verify-age", {
      userId: "user@test.com",
      minimumAge: 18,
    });
    expect(JSON.parse(result.content[0].text)).toEqual(mockResponse);
  });

  it("verify_credential calls POST /kyc/verify-credential", async () => {
    const mockResponse = { sessionId: "cred-1" };
    (client.post as any).mockResolvedValue(mockResponse);

    const tools = (server as any)._registeredTools;
    const handler = tools.verify_credential.handler;
    const result = await handler({ userId: "u1", credentialType: "address" }, {});

    expect(client.post).toHaveBeenCalledWith("/kyc/verify-credential", {
      userId: "u1",
      credentialType: "address",
    });
    expect(JSON.parse(result.content[0].text)).toEqual(mockResponse);
  });
});

describe("KYA tool handlers", () => {
  let client: NuggetsApiClient;
  let server: McpServer;

  beforeEach(() => {
    const result = createServerWithTools();
    server = result.server;
    client = result.client;
  });

  it("register_agent_identity calls POST /kya/agents", async () => {
    const mockResponse = { agentId: "a1", did: "did:nuggets:a1" };
    (client.post as any).mockResolvedValue(mockResponse);

    const tools = (server as any)._registeredTools;
    const handler = tools.register_agent_identity.handler;
    const result = await handler({ agentName: "TestAgent", githubUrl: "https://github.com/test" }, {});

    expect(client.post).toHaveBeenCalledWith("/kya/agents", {
      agentName: "TestAgent",
      githubUrl: "https://github.com/test",
    });
    expect(JSON.parse(result.content[0].text)).toEqual(mockResponse);
  });

  it("verify_agent_identity calls GET /kya/agents/:id", async () => {
    const mockResponse = { agentId: "a1", verified: true };
    (client.get as any).mockResolvedValue(mockResponse);

    const tools = (server as any)._registeredTools;
    const handler = tools.verify_agent_identity.handler;
    const result = await handler({ agentId: "a1" }, {});

    expect(client.get).toHaveBeenCalledWith("/kya/agents/a1");
    expect(JSON.parse(result.content[0].text)).toEqual(mockResponse);
  });

  it("get_agent_trust_score calls GET /kya/agents/:id/trust-score", async () => {
    const mockResponse = { agentId: "a1", score: 0.85 };
    (client.get as any).mockResolvedValue(mockResponse);

    const tools = (server as any)._registeredTools;
    const handler = tools.get_agent_trust_score.handler;
    const result = await handler({ agentId: "a1" }, {});

    expect(client.get).toHaveBeenCalledWith("/kya/agents/a1/trust-score");
    expect(JSON.parse(result.content[0].text)).toEqual(mockResponse);
  });
});

describe("Auth tool handlers", () => {
  let client: NuggetsApiClient;
  let server: McpServer;

  beforeEach(() => {
    const result = createServerWithTools();
    server = result.server;
    client = result.client;
  });

  it("request_credential_presentation calls POST /credentials/presentations", async () => {
    const mockResponse = { sessionId: "p1" };
    (client.post as any).mockResolvedValue(mockResponse);

    const tools = (server as any)._registeredTools;
    const handler = tools.request_credential_presentation.handler;
    const result = await handler({ userId: "u1", credentialTypes: ["email", "phone"] }, {});

    expect(client.post).toHaveBeenCalledWith("/credentials/presentations", {
      userId: "u1",
      credentialTypes: ["email", "phone"],
    });
    expect(JSON.parse(result.content[0].text)).toEqual(mockResponse);
  });

  it("verify_presentation calls GET /credentials/presentations/:id", async () => {
    const mockResponse = { sessionId: "p1", status: "presented", verified: true };
    (client.get as any).mockResolvedValue(mockResponse);

    const tools = (server as any)._registeredTools;
    const handler = tools.verify_presentation.handler;
    const result = await handler({ sessionId: "p1" }, {});

    expect(client.get).toHaveBeenCalledWith("/credentials/presentations/p1");
    expect(JSON.parse(result.content[0].text)).toEqual(mockResponse);
  });

  it("initiate_oauth_flow calls POST /oauth/authorize with default scopes", async () => {
    const mockResponse = { authorizationUrl: "https://auth.nuggets.life/..." };
    (client.post as any).mockResolvedValue(mockResponse);

    const tools = (server as any)._registeredTools;
    const handler = tools.initiate_oauth_flow.handler;
    const result = await handler({ redirectUri: "https://app.test/callback" }, {});

    expect(client.post).toHaveBeenCalledWith("/oauth/authorize", {
      redirectUri: "https://app.test/callback",
      scopes: ["openid"],
    });
    expect(JSON.parse(result.content[0].text)).toEqual(mockResponse);
  });

  it("initiate_oauth_flow respects custom scopes", async () => {
    const mockResponse = { authorizationUrl: "https://auth.nuggets.life/..." };
    (client.post as any).mockResolvedValue(mockResponse);

    const tools = (server as any)._registeredTools;
    const handler = tools.initiate_oauth_flow.handler;
    await handler({ redirectUri: "https://app.test/callback", scopes: ["openid", "profile"] }, {});

    expect(client.post).toHaveBeenCalledWith("/oauth/authorize", {
      redirectUri: "https://app.test/callback",
      scopes: ["openid", "profile"],
    });
  });

  it("check_auth_status calls GET /auth/status/:userId", async () => {
    const mockResponse = { authenticated: true, kycStatus: "verified" };
    (client.get as any).mockResolvedValue(mockResponse);

    const tools = (server as any)._registeredTools;
    const handler = tools.check_auth_status.handler;
    const result = await handler({ userId: "u1" }, {});

    expect(client.get).toHaveBeenCalledWith("/auth/status/u1");
    expect(JSON.parse(result.content[0].text)).toEqual(mockResponse);
  });
});
