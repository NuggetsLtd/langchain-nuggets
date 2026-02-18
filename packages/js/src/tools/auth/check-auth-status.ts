import { z } from "zod";
import { NuggetsBaseTool } from "../base.js";
import type { AuthStatus } from "../../types.js";

const schema = z.object({
  userId: z.string().describe("The user's identifier to check authentication status for"),
});

export class CheckAuthStatus extends NuggetsBaseTool {
  name = "check_auth_status";
  description = "Check whether a user is currently authenticated with Nuggets and their verification status. Returns whether the user is authenticated, their KYC verification status, and which credentials they have on file. Use this to gate access to sensitive operations that require verified identity.";
  schema = schema;

  async _call({ userId }: z.output<typeof schema>): Promise<string> {
    const status = await this.client.get<AuthStatus>(`/auth/status/${userId}`);
    return JSON.stringify(status);
  }
}
