import { z } from "zod";
import { NuggetsBaseTool } from "../base.js";
import type { AgentIdentity } from "../../types.js";

const schema = z.object({
  agentName: z.string().describe("A human-readable name for this AI agent"),
  githubUrl: z.string().optional().describe("GitHub profile or repo URL for developer provenance verification"),
  twitterHandle: z.string().optional().describe("Twitter/X handle for social verification"),
});

export class RegisterAgentIdentity extends NuggetsBaseTool {
  name = "register_agent_identity";
  description = "Register this AI agent's identity with Nuggets to establish verifiable provenance. Provide developer provenance signals (GitHub, Twitter) so other agents and users can verify who built this agent. Returns a DID and agent identity record.";
  schema = schema;

  async _call(input: z.output<typeof schema>): Promise<string> {
    const identity = await this.client.post<AgentIdentity>("/kya/agents", input);
    return JSON.stringify(identity);
  }
}
