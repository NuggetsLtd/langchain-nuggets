export { NuggetsToolkit } from "./toolkit.js";
export { NuggetsApiClient } from "./client/nuggets-api-client.js";
export { NuggetsBaseTool } from "./tools/base.js";
export type { NuggetsBaseToolParams } from "./tools/base.js";

// KYC tools
export {
  InitiateKycVerification,
  CheckKycStatus,
  VerifyAge,
  VerifyCredential,
} from "./tools/kyc/index.js";

// KYA tools
export {
  RegisterAgentIdentity,
  VerifyAgentIdentity,
  GetAgentTrustScore,
} from "./tools/kya/index.js";

// Auth tools
export {
  RequestCredentialPresentation,
  VerifyPresentation,
  InitiateOAuthFlow,
  CheckAuthStatus,
} from "./tools/auth/index.js";

// Types
export type {
  NuggetsConfig,
  KycSession,
  KycStatus,
  KycResult,
  VerifiableCredential,
  AgentIdentity,
  AgentTrustScore,
  CredentialPresentation,
  PresentationStatus,
  PresentationResult,
  OAuthSession,
  OAuthTokenResult,
  AuthStatus,
} from "./types.js";
