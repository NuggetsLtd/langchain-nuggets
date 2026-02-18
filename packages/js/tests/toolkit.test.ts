import { describe, it, expect } from "vitest";
import { NuggetsToolkit } from "../src/toolkit.js";

describe("NuggetsToolkit", () => {
  it("should create a toolkit with config", () => {
    const toolkit = new NuggetsToolkit({
      apiUrl: "https://api.nuggets.test",
      partnerId: "test-partner",
      partnerSecret: "test-secret",
    });
    expect(toolkit).toBeInstanceOf(NuggetsToolkit);
  });

  it("should return all 11 tools from getTools()", () => {
    const toolkit = new NuggetsToolkit({
      apiUrl: "https://api.nuggets.test",
      partnerId: "test-partner",
      partnerSecret: "test-secret",
    });

    const tools = toolkit.getTools();
    expect(tools).toHaveLength(11);

    const names = tools.map((t) => t.name);
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

  it("should support environment variable defaults", () => {
    process.env.NUGGETS_API_URL = "https://api.nuggets.test";
    process.env.NUGGETS_PARTNER_ID = "env-partner";
    process.env.NUGGETS_PARTNER_SECRET = "env-secret";

    const toolkit = new NuggetsToolkit();
    const tools = toolkit.getTools();
    expect(tools).toHaveLength(11);

    delete process.env.NUGGETS_API_URL;
    delete process.env.NUGGETS_PARTNER_ID;
    delete process.env.NUGGETS_PARTNER_SECRET;
  });

  it("should throw if no config and no env vars", () => {
    delete process.env.NUGGETS_API_URL;
    delete process.env.NUGGETS_PARTNER_ID;
    delete process.env.NUGGETS_PARTNER_SECRET;

    expect(() => new NuggetsToolkit()).toThrow();
  });
});
