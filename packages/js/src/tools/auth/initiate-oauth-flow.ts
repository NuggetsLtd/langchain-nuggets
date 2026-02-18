import { z } from "zod";
import { NuggetsBaseTool } from "../base.js";
import type { OAuthSession } from "../../types.js";

const schema = z.object({
  redirectUri: z.string().describe("The URL to redirect the user to after authentication"),
  scopes: z.array(z.string()).optional().describe('OAuth scopes to request (e.g. ["openid", "profile", "email"]). Defaults to ["openid"]'),
});

export class InitiateOAuthFlow extends NuggetsBaseTool {
  name = "initiate_oauth_flow";
  description = "Start an OAuth 2.0 / OpenID Connect authentication flow with Nuggets as the identity provider. Returns an authorization URL that the user should be redirected to. After the user authenticates via Nuggets (QR scan, biometrics, or WebAuthn), they will be redirected back to the redirectUri with an authorization code.";
  schema = schema;

  async _call(input: z.output<typeof schema>): Promise<string> {
    const session = await this.client.post<OAuthSession>("/oauth/authorize", {
      redirectUri: input.redirectUri,
      scopes: input.scopes ?? ["openid"],
    });
    return JSON.stringify(session);
  }
}
