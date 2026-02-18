export interface NuggetsConfig {
  apiUrl: string;
  partnerId: string;
  partnerSecret: string;
  webhook?: {
    callbackUrl: string;
    secret: string;
  };
}

export interface NuggetsAuthToken {
  accessToken: string;
  expiresAt: number;
}

export interface KycSession {
  sessionId: string;
  deeplink: string;
  qrCodeUrl: string;
}

export type KycStatus = "pending" | "completed" | "failed" | "expired";

export interface KycResult {
  sessionId: string;
  status: KycStatus;
  credentials?: VerifiableCredential[];
}

export interface VerifiableCredential {
  id: string;
  type: string[];
  issuer: string;
  issuanceDate: string;
  credentialSubject: Record<string, unknown>;
  proof?: Record<string, unknown>;
}

export interface AgentIdentity {
  agentId: string;
  did: string;
  provenance: {
    github?: string;
    twitter?: string;
  };
  registeredAt: string;
}

export interface AgentTrustScore {
  agentId: string;
  score: number;
  signals: {
    githubVerified: boolean;
    socialVerified: boolean;
    registrationAge: number;
  };
}

export interface CredentialPresentation {
  sessionId: string;
  deeplink: string;
  qrCodeUrl: string;
}

export type PresentationStatus = "pending" | "presented" | "rejected" | "expired";

export interface PresentationResult {
  sessionId: string;
  status: PresentationStatus;
  credentials?: VerifiableCredential[];
  verified?: boolean;
}

export interface OAuthSession {
  authorizationUrl: string;
  state: string;
  codeVerifier: string;
}

export interface OAuthTokenResult {
  accessToken: string;
  refreshToken?: string;
  idToken?: string;
  expiresIn: number;
  tokenType: string;
}

export interface AuthStatus {
  authenticated: boolean;
  userId?: string;
  kycVerified?: boolean;
  credentials?: string[];
}

export interface ApiError {
  code: string;
  message: string;
  statusCode: number;
}
