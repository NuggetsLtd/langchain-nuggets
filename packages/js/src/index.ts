export { loadPrivateKey, signAgentProof } from "./agentProof.js";
export { NuggetsAuthorityMiddleware } from "./authorityMiddleware.js";
export { extractOidcClientId, OidcClientCredentialsClient, OidcTokenError } from "./oidcClient.js";
export {
  buildProofArtifact,
  hashIntent,
  hashParameters,
  hashResult,
  stableStringify
} from "./proof.js";
export {
  discoverAuthority,
  ProofVerificationError,
  resetProofVerificationCaches,
  verifyAuthorityProof
} from "./proofVerification.js";
export {
  MiddlewareConfig
} from "./types.js";
export type {
  ActionContext,
  AuthorityDecision,
  AuthorityEvaluationRequest,
  AuthorityEvaluationResponse,
  MiddlewareConfigInput,
  PrivateKeyInput,
  ProofArtifact,
  ToolArgs,
  ToolCallLike,
  ToolCallRequestLike
} from "./types.js";
