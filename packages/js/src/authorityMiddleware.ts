import { randomUUID } from "node:crypto";
import { ToolMessage } from "@langchain/core/messages";
import { loadPrivateKey, signAgentProof } from "./agentProof.js";
import { extractOidcClientId, OidcClientCredentialsClient } from "./oidcClient.js";
import {
  buildProofArtifact,
  hashIntent,
  hashParameters,
  hashResult
} from "./proof.js";
import {
  discoverAuthority,
  ProofVerificationError,
  verifyAuthorityProof
} from "./proofVerification.js";
import type {
  ActionContext,
  AuthorityEvaluationRequest,
  AuthorityEvaluationResponse,
  MiddlewareConfig,
  ProofArtifact,
  SigningKey,
  ToolArgs,
  ToolCallRequestLike
} from "./types.js";

export class NuggetsAuthorityMiddleware {
  private config: MiddlewareConfig;
  private proofList: ProofArtifact[] = [];
  private privateKeyPromise?: Promise<SigningKey>;
  private client?: OidcClientCredentialsClient;

  constructor(config: MiddlewareConfig) {
    this.config = config;
    if (config.agentPrivateKey) {
      this.privateKeyPromise = loadPrivateKey(config.agentPrivateKey);
    }
  }

  get proofs(): ProofArtifact[] {
    return [...this.proofList];
  }

  async wrapToolCall(
    request: ToolCallRequestLike,
    handler: (request: ToolCallRequestLike) => unknown | Promise<unknown>
  ): Promise<unknown> {
    const toolCall = request.tool_call;
    const toolName = toolCall.name;
    const toolArgs = toolCall.args;
    const toolCallId = toolCall.id;
    const evalRequest = this.buildEvalRequest(toolName, toolArgs);
    const start = performance.now();

    let authResponse: AuthorityEvaluationResponse;
    if (this.config.testMode) {
      authResponse = this.testModeResponse();
    } else {
      try {
        const privateKey = await this.getPrivateKey();
        const payload: AuthorityEvaluationRequest = {
          ...evalRequest,
          agent_proof: await signAgentProof(privateKey, this.config.agentId, evalRequest.action.nonce)
        };
        const client = await this.getClient();
        const rawResponse = await client.post(
          `${this.config.apiUrl.replace(/\/+$/, "")}${this.config.authorityEndpoint}`,
          payload,
          { "Idempotency-Key": randomUUID() }
        );
        authResponse = coerceAuthorityResponse(rawResponse);
      } catch (exc) {
        return this.errorMessage(toolCallId, toolName, `Authority evaluation failed: ${exc}`);
      }
    }

    if (authResponse.decision === "DENY") {
      return this.denyMessage(toolCallId, toolName, authResponse);
    }

    const proofFailure = await this.verifyProofOrNull(authResponse, toolCallId, toolName);
    if (proofFailure) {
      return proofFailure;
    }

    const result = await handler(request);
    const resultContent = extractResultContent(result);
    const proof = buildProofArtifact({
      authorityResponse: authResponse,
      agentId: this.config.agentId,
      controllerId: this.config.controllerId,
      delegationId: this.config.delegationId,
      tool: toolName,
      parametersHash: evalRequest.action.parameters_hash,
      resultHash: hashResult(resultContent),
      latencyMs: performance.now() - start,
      intentHash: evalRequest.action.intent_hash ?? null,
      testMode: this.config.testMode
    });
    await this.emitProof(proof);
    return result;
  }

  async awrapToolCall(
    request: ToolCallRequestLike,
    handler: (request: ToolCallRequestLike) => unknown | Promise<unknown>
  ): Promise<unknown> {
    return this.wrapToolCall(request, handler);
  }

  buildEvalRequest(toolName: string, toolArgs: ToolArgs): AuthorityEvaluationRequest {
    const intent = this.config.intentResolver?.(toolName, toolArgs) ?? null;
    const target = typeof toolArgs.target === "undefined" ? toolName : String(toolArgs.target);
    const parametersHash = hashParameters(toolArgs);
    const timestamp = new Date().toISOString();
    const intentHash = intent === null ? null : hashIntent(intent, parametersHash, timestamp);
    const action: ActionContext = {
      tool: toolName,
      target,
      parameters_hash: parametersHash,
      intent,
      intent_hash: intentHash,
      timestamp,
      nonce: randomUUID()
    };
    return {
      agent_id: this.config.agentId,
      controller_id: this.config.controllerId,
      delegation_id: this.config.delegationId,
      action
    };
  }

  private async getPrivateKey(): Promise<SigningKey> {
    if (!this.privateKeyPromise) {
      throw new Error("agentPrivateKey required when testMode is false");
    }
    return this.privateKeyPromise;
  }

  private async getClient(): Promise<OidcClientCredentialsClient> {
    if (this.client) {
      return this.client;
    }
    if (!this.config.oidcIssuerUrl) {
      throw new Error("oidcIssuerUrl required when testMode is false");
    }
    const privateKey = await this.getPrivateKey();
    this.client = new OidcClientCredentialsClient({
      issuerUrl: this.config.oidcIssuerUrl,
      clientId: extractOidcClientId(this.config.agentId),
      privateKey,
      scope: this.config.authorityScope,
      resource: this.config.resolvedAuthorityAudience()
    });
    return this.client;
  }

  private async verifyProofOrNull(
    authResponse: AuthorityEvaluationResponse,
    toolCallId: string,
    toolName: string
  ): Promise<ToolMessage | null> {
    if (this.config.testMode || !this.config.verifyProofs) {
      return null;
    }
    try {
      const [issuer, jwksUri] = await discoverAuthority(this.config.apiUrl);
      await verifyAuthorityProof({
        signature: authResponse.signature,
        expected: {
          decision: authResponse.decision,
          proof_id: authResponse.proof_id,
          agent_id: this.config.agentId,
          controller_id: this.config.controllerId,
          constraints_evaluated: authResponse.constraints_evaluated ?? []
        },
        issuer,
        jwksUri
      });
      return null;
    } catch (exc) {
      if (exc instanceof ProofVerificationError || exc instanceof Error) {
        return this.proofFailureMessage(exc, toolCallId, toolName, authResponse.proof_id);
      }
      return this.proofFailureMessage(new Error(String(exc)), toolCallId, toolName, authResponse.proof_id);
    }
  }

  private testModeResponse(): AuthorityEvaluationResponse {
    return {
      decision: "ALLOW",
      proof_id: `test-${randomUUID()}`,
      signature: "test-mode-unverifiable",
      reason_code: null,
      constraints_evaluated: ["test_mode"]
    };
  }

  private denyMessage(toolCallId: string, toolName: string, response: AuthorityEvaluationResponse): ToolMessage {
    return new ToolMessage({
      content: JSON.stringify({
        status: "DENIED",
        tool: toolName,
        reason_code: response.reason_code ?? null,
        proof_id: response.proof_id,
        message: `Authority check denied execution of '${toolName}'${
          response.reason_code ? `: ${response.reason_code}` : ""
        }`
      }),
      tool_call_id: toolCallId
    });
  }

  private errorMessage(toolCallId: string, toolName: string, message: string): ToolMessage {
    return new ToolMessage({
      content: JSON.stringify({
        status: "ERROR",
        tool: toolName,
        message
      }),
      tool_call_id: toolCallId
    });
  }

  private proofFailureMessage(
    exc: Error,
    toolCallId: string,
    toolName: string,
    proofId: string
  ): ToolMessage {
    return new ToolMessage({
      content: JSON.stringify({
        status: "DENIED",
        tool: toolName,
        reason_code: "PROOF_VERIFICATION_FAILED",
        proof_id: proofId,
        message: `Authority proof for '${toolName}' failed verification: ${exc.message}`
      }),
      tool_call_id: toolCallId
    });
  }

  private async emitProof(proof: ProofArtifact): Promise<void> {
    this.proofList.push(proof);
    await this.config.onProof?.(proof);
  }
}

function coerceAuthorityResponse(value: unknown): AuthorityEvaluationResponse {
  if (!value || typeof value !== "object") {
    throw new Error("authority response is not an object");
  }
  const response = value as Record<string, unknown>;
  if (response.decision !== "ALLOW" && response.decision !== "DENY") {
    throw new Error("authority response missing decision");
  }
  if (typeof response.proof_id !== "string") {
    throw new Error("authority response missing proof_id");
  }
  if (typeof response.signature !== "string") {
    throw new Error("authority response missing signature");
  }
  return {
    decision: response.decision,
    proof_id: response.proof_id,
    signature: response.signature,
    reason_code: typeof response.reason_code === "string" ? response.reason_code : null,
    constraints_evaluated: Array.isArray(response.constraints_evaluated)
      ? response.constraints_evaluated.filter((item): item is string => typeof item === "string")
      : []
  };
}

function extractResultContent(result: unknown): string {
  if (result && typeof result === "object" && "content" in result) {
    const content = (result as { content: unknown }).content;
    return typeof content === "string" ? content : JSON.stringify(content);
  }
  return "";
}
