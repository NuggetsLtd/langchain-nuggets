import { z } from "zod";
import { NuggetsBaseTool } from "../base.js";
import type { PresentationResult } from "../../types.js";

const schema = z.object({
  sessionId: z.string().describe("The presentation session ID returned by request_credential_presentation"),
});

export class VerifyPresentation extends NuggetsBaseTool {
  name = "verify_presentation";
  description = 'Check the status of a credential presentation request and cryptographically verify any presented credentials. Returns status: "pending" (awaiting user), "presented" (user shared credentials), "rejected" (user declined), or "expired". If presented, includes the verified credentials and a verified boolean.';
  schema = schema;

  async _call({ sessionId }: z.output<typeof schema>): Promise<string> {
    const result = await this.client.get<PresentationResult>(`/credentials/presentations/${sessionId}`);
    return JSON.stringify(result);
  }
}
