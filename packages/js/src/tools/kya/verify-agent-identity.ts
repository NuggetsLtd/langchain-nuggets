import { z } from "zod";
import { NuggetsBaseTool } from "../base.js";
import type { AgentIdentity } from "../../types.js";

const schema = z.object({
  agentId: z.string().describe("The agent ID or DID of the agent to verify"),
});

export class VerifyAgentIdentity extends NuggetsBaseTool {
  name = "verify_agent_identity";
  description = "Verify another AI agent's identity through Nuggets. Returns the agent's registered identity including DID, developer provenance signals, and registration date. Use this before trusting data from or sharing data with another agent.";
  schema = schema;

  async _call({ agentId }: z.output<typeof schema>): Promise<string> {
    const identity = await this.client.get<AgentIdentity>(`/kya/agents/${encodeURIComponent(agentId)}`);
    return JSON.stringify(identity);
  }
}
