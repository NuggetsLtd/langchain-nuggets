import { z } from "zod";
import { NuggetsBaseTool } from "../base.js";
import type { KycResult } from "../../types.js";

const schema = z.object({
  sessionId: z.string().describe("The KYC session ID returned by initiate_kyc_verification"),
});

export class CheckKycStatus extends NuggetsBaseTool {
  name = "check_kyc_status";
  description = "Check the status of a KYC verification session. Returns status: \"pending\" (user has not yet completed), \"completed\" (verified), \"failed\" (verification failed), or \"expired\" (session timed out). If completed, includes the verified credentials.";
  schema = schema;

  async _call({ sessionId }: z.output<typeof schema>): Promise<string> {
    const result = await this.client.get<KycResult>(`/kyc/sessions/${encodeURIComponent(sessionId)}`);
    return JSON.stringify(result);
  }
}
