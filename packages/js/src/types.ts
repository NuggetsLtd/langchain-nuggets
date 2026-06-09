import type { CryptoKey, JWK } from "jose";

/**
 * A key usable for signing with `jose` v6. `importPKCS8` returns a `CryptoKey`;
 * `importJWK` may return a `CryptoKey` or `Uint8Array`. (`jose` v6 removed the
 * old `KeyLike` alias.)
 */
export type SigningKey = CryptoKey | Uint8Array;

export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue | undefined };

export type ToolArgs = Record<string, unknown>;

export type IntentResolver = (toolName: string, toolArgs: ToolArgs) => string | null | undefined;

export type ProofCallback = (proof: ProofArtifact) => void | Promise<void>;

export type PrivateKeyInput = string | JWK | { keys: JWK[] };

export interface MiddlewareConfigInput {
  apiUrl: string;
  oidcIssuerUrl?: string;
  agentId: string;
  controllerId: string;
  delegationId: string;
  authorityEndpoint?: string;
  authorityScope?: string;
  authorityAudience?: string;
  onProof?: ProofCallback;
  intentResolver?: IntentResolver;
  testMode?: boolean;
  agentPrivateKey?: PrivateKeyInput;
  verifyProofs?: boolean;
}

export class MiddlewareConfig {
  apiUrl: string;
  oidcIssuerUrl?: string;
  agentId: string;
  controllerId: string;
  delegationId: string;
  authorityEndpoint: string;
  authorityScope: string;
  authorityAudience?: string;
  onProof?: ProofCallback;
  intentResolver?: IntentResolver;
  testMode: boolean;
  agentPrivateKey?: PrivateKeyInput;
  verifyProofs: boolean;

  constructor(input: MiddlewareConfigInput) {
    this.apiUrl = input.apiUrl;
    this.oidcIssuerUrl = input.oidcIssuerUrl;
    this.agentId = input.agentId;
    this.controllerId = input.controllerId;
    this.delegationId = input.delegationId;
    this.authorityEndpoint = input.authorityEndpoint ?? "/api/authority/evaluate";
    this.authorityScope = input.authorityScope ?? "authority.evaluate";
    this.authorityAudience = input.authorityAudience;
    this.onProof = input.onProof;
    this.intentResolver = input.intentResolver;
    this.testMode = input.testMode ?? false;
    this.agentPrivateKey = input.agentPrivateKey;
    this.verifyProofs = input.verifyProofs ?? true;

    if (!this.testMode && !this.oidcIssuerUrl) {
      throw new Error(
        "oidcIssuerUrl is required when testMode is false. Set it to the Nuggets OIDC provider URL."
      );
    }
    if (!this.testMode && !this.agentPrivateKey) {
      throw new Error(
        "agentPrivateKey is required when testMode is false. Provide a PEM string, file path, JWK, or JWKS."
      );
    }
  }

  resolvedAuthorityAudience(): string {
    return this.authorityAudience ?? `${this.apiUrl.replace(/\/+$/, "")}/api/authority`;
  }
}

export interface ActionContext {
  tool: string;
  target?: string;
  parameters_hash: string;
  intent?: string | null;
  intent_hash?: string | null;
  timestamp: string;
  nonce: string;
}

export interface AuthorityEvaluationRequest {
  agent_id: string;
  controller_id: string;
  delegation_id: string;
  action: ActionContext;
  agent_proof?: string;
}

export type AuthorityDecision = "ALLOW" | "DENY";

export interface AuthorityEvaluationResponse {
  decision: AuthorityDecision;
  proof_id: string;
  signature: string;
  reason_code?: string | null;
  constraints_evaluated?: string[];
}

export interface ProofArtifact {
  proof_id: string;
  agent_id: string;
  controller_id: string;
  delegation_id: string;
  tool: string;
  parameters_hash: string;
  result_hash: string;
  intent_hash?: string | null;
  constraints_evaluated: string[];
  authority_signature: string;
  timestamp: string;
  latency_ms: number;
  test_mode: boolean;
}

export interface ToolCallLike {
  name: string;
  args: ToolArgs;
  id: string;
}

export interface ToolCallRequestLike {
  tool_call: ToolCallLike;
}
