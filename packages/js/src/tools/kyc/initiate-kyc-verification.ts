import { z } from "zod";
import { NuggetsBaseTool } from "../base.js";
import type { KycSession } from "../../types.js";

const schema = z.object({
  userId: z.string().describe("The user's identifier (email or Nuggets address) to start KYC verification for"),
});

export class InitiateKycVerification extends NuggetsBaseTool {
  name = "initiate_kyc_verification";
  description = "Start a KYC (Know Your Customer) identity verification flow for a user. Returns a deeplink and QR code URL that the user must scan with their Nuggets app to complete identity verification. Use check_kyc_status to poll for completion.";
  schema = schema;

  async _call({ userId }: z.output<typeof schema>): Promise<string> {
    const session = await this.client.post<KycSession>("/kyc/sessions", { userId });
    return JSON.stringify(session);
  }
}
