import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

describe("createNuggetsMcpServer", () => {
  const originalEnv = { ...process.env };

  beforeEach(() => {
    vi.resetModules();
    process.env = { ...originalEnv };
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  it("should create a server with explicit config", async () => {
    const { createNuggetsMcpServer } = await import("../src/index.js");
    const server = createNuggetsMcpServer({
      apiUrl: "https://api.nuggets.test",
      partnerId: "pid",
      partnerSecret: "psecret",
    });
    expect(server).toBeInstanceOf(McpServer);
  });

  it("should create a server from environment variables", async () => {
    process.env.NUGGETS_API_URL = "https://api.nuggets.test";
    process.env.NUGGETS_PARTNER_ID = "env-pid";
    process.env.NUGGETS_PARTNER_SECRET = "env-psecret";

    const { createNuggetsMcpServer } = await import("../src/index.js");
    const server = createNuggetsMcpServer();
    expect(server).toBeInstanceOf(McpServer);
  });

  it("should throw when apiUrl is missing", async () => {
    process.env.NUGGETS_PARTNER_ID = "pid";
    process.env.NUGGETS_PARTNER_SECRET = "ps";
    delete process.env.NUGGETS_API_URL;

    const { createNuggetsMcpServer } = await import("../src/index.js");
    expect(() => createNuggetsMcpServer()).toThrow("apiUrl");
  });

  it("should throw when partnerId is missing", async () => {
    process.env.NUGGETS_API_URL = "https://api.nuggets.test";
    process.env.NUGGETS_PARTNER_SECRET = "ps";
    delete process.env.NUGGETS_PARTNER_ID;

    const { createNuggetsMcpServer } = await import("../src/index.js");
    expect(() => createNuggetsMcpServer()).toThrow("partnerId");
  });

  it("should throw when partnerSecret is missing", async () => {
    process.env.NUGGETS_API_URL = "https://api.nuggets.test";
    process.env.NUGGETS_PARTNER_ID = "pid";
    delete process.env.NUGGETS_PARTNER_SECRET;

    const { createNuggetsMcpServer } = await import("../src/index.js");
    expect(() => createNuggetsMcpServer()).toThrow("partnerSecret");
  });

  it("should register 11 tools on the created server", async () => {
    const { createNuggetsMcpServer } = await import("../src/index.js");
    const server = createNuggetsMcpServer({
      apiUrl: "https://api.nuggets.test",
      partnerId: "pid",
      partnerSecret: "ps",
    });
    const tools = (server as any)._registeredTools;
    expect(Object.keys(tools)).toHaveLength(11);
  });
});
