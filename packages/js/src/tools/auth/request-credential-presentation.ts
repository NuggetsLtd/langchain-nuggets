import { z } from "zod";
import { NuggetsBaseTool } from "../base.js";
import type { CredentialPresentation } from "../../types.js";

const schema = z.object({
  userId: z.string().describe("The user's identifier (email or Nuggets address)"),
  credentialTypes: z.array(z.string()).describe('Array of credential types to request (e.g. ["email", "phone", "address"])'),
});

export class RequestCredentialPresentation extends NuggetsBaseTool {
  name = "request_credential_presentation";
  description = "Ask a user to present one or more verifiable credentials from their Nuggets app. Specify which credential types you need. The user will see a request in their app and can approve or reject sharing each credential. Use verify_presentation with the returned sessionId to check if the user responded.";
  schema = schema;

  async _call(input: z.output<typeof schema>): Promise<string> {
    const presentation = await this.client.post<CredentialPresentation>("/credentials/presentations", input);
    return JSON.stringify(presentation);
  }
}
