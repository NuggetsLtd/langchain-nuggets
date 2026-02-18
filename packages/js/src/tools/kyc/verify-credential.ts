import { z } from "zod";
import { NuggetsBaseTool } from "../base.js";
import type { KycSession } from "../../types.js";

const schema = z.object({
  userId: z.string().describe("The user's identifier (email or Nuggets address)"),
  credentialType: z.string().describe("The type of credential to verify (e.g. \"address\", \"nationality\", \"email\", \"phone\")"),
});

export class VerifyCredential extends NuggetsBaseTool {
  name = "verify_credential";
  description = "Request selective disclosure verification of a specific credential for a user. The user will be asked to share only the requested credential type from their Nuggets app. Returns a deeplink/QR code for the user to approve. Use check_kyc_status with the returned sessionId to check completion.";
  schema = schema;

  async _call({ userId, credentialType }: z.output<typeof schema>): Promise<string> {
    const session = await this.client.post<KycSession>("/kyc/verify-credential", { userId, credentialType });
    return JSON.stringify(session);
  }
}
