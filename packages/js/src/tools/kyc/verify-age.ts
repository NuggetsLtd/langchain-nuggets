import { z } from "zod";
import { NuggetsBaseTool } from "../base.js";
import type { KycSession } from "../../types.js";

const schema = z.object({
  userId: z.string().describe("The user's identifier (email or Nuggets address)"),
  minimumAge: z.number().describe("The minimum age to verify (e.g. 18 for age-restricted content)"),
});

export class VerifyAge extends NuggetsBaseTool {
  name = "verify_age";
  description = "Request selective disclosure age verification for a user. Proves the user meets a minimum age requirement WITHOUT revealing their actual date of birth. Returns a deeplink/QR code for the user to approve the age proof in their Nuggets app. Use check_kyc_status with the returned sessionId to check if the user approved.";
  schema = schema;

  async _call({ userId, minimumAge }: z.output<typeof schema>): Promise<string> {
    const session = await this.client.post<KycSession>("/kyc/verify-age", { userId, minimumAge });
    return JSON.stringify(session);
  }
}
