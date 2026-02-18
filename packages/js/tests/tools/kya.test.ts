import { describe, it, expect, vi } from "vitest";
import { NuggetsApiClient } from "../../src/client/nuggets-api-client.js";
import { RegisterAgentIdentity } from "../../src/tools/kya/register-agent-identity.js";
import { VerifyAgentIdentity } from "../../src/tools/kya/verify-agent-identity.js";
import { GetAgentTrustScore } from "../../src/tools/kya/get-agent-trust-score.js";
import type { NuggetsConfig, AgentIdentity, AgentTrustScore } from "../../src/types.js";

const mockConfig: NuggetsConfig = {
  apiUrl: "https://api.nuggets.test",
  partnerId: "test-partner",
  partnerSecret: "test-secret",
};

function createClient() {
  return new NuggetsApiClient(mockConfig);
}

describe("KYA Tools", () => {
  describe("RegisterAgentIdentity", () => {
    it("should have the correct name and description", () => {
      const client = createClient();
      const tool = new RegisterAgentIdentity({ client });
      expect(tool.name).toBe("register_agent_identity");
      expect(tool.description).toContain("agent");
    });

    it("should call client.post with agentName/githubUrl and return identity JSON", async () => {
      const client = createClient();
      const tool = new RegisterAgentIdentity({ client });

      const mockIdentity: AgentIdentity = {
        agentId: "agent-123",
        did: "did:nuggets:agent-123",
        provenance: {
          github: "https://github.com/test-dev",
          twitter: undefined,
        },
        registeredAt: "2024-06-01T00:00:00Z",
      };

      vi.spyOn(client, "post").mockResolvedValue(mockIdentity);

      const result = await tool.invoke({
        agentName: "TestAgent",
        githubUrl: "https://github.com/test-dev",
      });
      const parsed = JSON.parse(result);

      expect(parsed).toEqual(mockIdentity);
      expect(client.post).toHaveBeenCalledWith("/kya/agents", {
        agentName: "TestAgent",
        githubUrl: "https://github.com/test-dev",
      });
    });
  });

  describe("VerifyAgentIdentity", () => {
    it("should have the correct name and description", () => {
      const client = createClient();
      const tool = new VerifyAgentIdentity({ client });
      expect(tool.name).toBe("verify_agent_identity");
      expect(tool.description).toContain("agent");
    });

    it("should call client.get with agentId and return identity JSON", async () => {
      const client = createClient();
      const tool = new VerifyAgentIdentity({ client });

      const mockIdentity: AgentIdentity = {
        agentId: "agent-456",
        did: "did:nuggets:agent-456",
        provenance: {
          github: "https://github.com/other-dev",
          twitter: "@otherdev",
        },
        registeredAt: "2024-05-15T00:00:00Z",
      };

      vi.spyOn(client, "get").mockResolvedValue(mockIdentity);

      const result = await tool.invoke({ agentId: "agent-456" });
      const parsed = JSON.parse(result);

      expect(parsed).toEqual(mockIdentity);
      expect(client.get).toHaveBeenCalledWith("/kya/agents/agent-456");
    });
  });

  describe("GetAgentTrustScore", () => {
    it("should have the correct name and description", () => {
      const client = createClient();
      const tool = new GetAgentTrustScore({ client });
      expect(tool.name).toBe("get_agent_trust_score");
      expect(tool.description).toContain("agent");
    });

    it("should call client.get and return trust score JSON with score and signals", async () => {
      const client = createClient();
      const tool = new GetAgentTrustScore({ client });

      const mockScore: AgentTrustScore = {
        agentId: "agent-456",
        score: 0.85,
        signals: {
          githubVerified: true,
          socialVerified: true,
          registrationAge: 180,
        },
      };

      vi.spyOn(client, "get").mockResolvedValue(mockScore);

      const result = await tool.invoke({ agentId: "agent-456" });
      const parsed = JSON.parse(result);

      expect(parsed).toEqual(mockScore);
      expect(parsed.score).toBe(0.85);
      expect(parsed.signals).toBeDefined();
      expect(parsed.signals.githubVerified).toBe(true);
      expect(client.get).toHaveBeenCalledWith("/kya/agents/agent-456/trust-score");
    });
  });
});
