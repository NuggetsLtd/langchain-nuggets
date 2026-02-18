import type { StructuredToolInterface } from "@langchain/core/tools";
import { NuggetsApiClient } from "./client/nuggets-api-client.js";
import type { NuggetsConfig } from "./types.js";
import {
  InitiateKycVerification,
  CheckKycStatus,
  VerifyAge,
  VerifyCredential,
} from "./tools/kyc/index.js";
import {
  RegisterAgentIdentity,
  VerifyAgentIdentity,
  GetAgentTrustScore,
} from "./tools/kya/index.js";
import {
  RequestCredentialPresentation,
  VerifyPresentation,
  InitiateOAuthFlow,
  CheckAuthStatus,
} from "./tools/auth/index.js";

declare const process: { env: Record<string, string | undefined> };

export class NuggetsToolkit {
  private client: NuggetsApiClient;

  constructor(config?: Partial<NuggetsConfig>) {
    const resolvedConfig: NuggetsConfig = {
      apiUrl: config?.apiUrl || process.env.NUGGETS_API_URL || "",
      partnerId: config?.partnerId || process.env.NUGGETS_PARTNER_ID || "",
      partnerSecret: config?.partnerSecret || process.env.NUGGETS_PARTNER_SECRET || "",
      webhook: config?.webhook,
    };

    if (!resolvedConfig.apiUrl || !resolvedConfig.partnerId || !resolvedConfig.partnerSecret) {
      throw new Error(
        "NuggetsToolkit requires apiUrl, partnerId, and partnerSecret. " +
        "Provide them via constructor or NUGGETS_API_URL, NUGGETS_PARTNER_ID, " +
        "NUGGETS_PARTNER_SECRET environment variables."
      );
    }

    this.client = new NuggetsApiClient(resolvedConfig);
  }

  getTools(): StructuredToolInterface[] {
    const params = { client: this.client };
    return [
      new InitiateKycVerification(params),
      new CheckKycStatus(params),
      new VerifyAge(params),
      new VerifyCredential(params),
      new RegisterAgentIdentity(params),
      new VerifyAgentIdentity(params),
      new GetAgentTrustScore(params),
      new RequestCredentialPresentation(params),
      new VerifyPresentation(params),
      new InitiateOAuthFlow(params),
      new CheckAuthStatus(params),
    ];
  }
}
