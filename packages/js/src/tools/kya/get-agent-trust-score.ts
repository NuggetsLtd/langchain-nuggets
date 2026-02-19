import { z } from "zod";
import { NuggetsBaseTool } from "../base.js";
import type { AgentTrustScore } from "../../types.js";

const schema = z.object({
  agentId: z.string().describe("The agent ID or DID to get the trust score for"),
});

export class GetAgentTrustScore extends NuggetsBaseTool {
  name = "get_agent_trust_score";
  description = "Get the trust score and provenance signals for an AI agent. Returns a score (0-1) based on verified signals: GitHub account verification, social profile verification, and registration age. Higher scores indicate more trustworthy agents with stronger developer provenance.";
  schema = schema;

  async _call({ agentId }: z.output<typeof schema>): Promise<string> {
    const score = await this.client.get<AgentTrustScore>(`/kya/agents/${encodeURIComponent(agentId)}/trust-score`);
    return JSON.stringify(score);
  }
}
