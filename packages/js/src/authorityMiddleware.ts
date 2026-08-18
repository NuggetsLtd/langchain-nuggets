import { randomUUID } from "node:crypto";
import { ToolMessage } from "@langchain/core/messages";
import { computeActionContextHashV1, hashIntentV1, hashParametersV1 } from "./actionContext.js";
import { loadPrivateKey, signAgentProofV1 } from "./agentProof.js";
import { extractOidcClientId, OidcClientCredentialsClient } from "./oidcClient.js";
import {
  buildProofArtifact,
  hashResult
} from "./proof.js";
import {
  discoverAuthority,
  ProofVerificationError,
  verifyAuthorityProof
} from "./proofVerification.js";
import type {
  ActionContext,
  ActionContextExtras,
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
    let evalRequest: AuthorityEvaluationRequest;
    try {
      evalRequest = this.buildEvalRequest(toolName, toolArgs);
    } catch (exc) {
      return this.errorMessage(toolCallId, toolName, `Action context resolution failed (${errorDetail(exc)})`);
    }
    const start = performance.now();

    let authResponse: AuthorityEvaluationResponse;
    if (this.config.testMode) {
      authResponse = this.testModeResponse();
    } else {
      try {
        const privateKey = await this.getPrivateKey();
        const [authorityIssuer] = await discoverAuthority(this.config.apiUrl);
        const actionContextHash = computeActionContextHashV1(evalRequest);
        const payload: AuthorityEvaluationRequest = {
          ...evalRequest,
          agent_proof: await signAgentProofV1(privateKey, {
            agentId: this.config.agentId,
            nonce: evalRequest.action.nonce,
            audience: authorityIssuer,
            actionContextHash
          })
        };
        const client = await this.getClient();
        const rawResponse = await client.post(
          `${this.config.apiUrl.replace(/\/+$/, "")}${this.config.authorityEndpoint}`,
          payload,
          { "Idempotency-Key": randomUUID() }
        );
        authResponse = coerceAuthorityResponse(rawResponse);
      } catch (exc) {
        return this.errorMessage(toolCallId, toolName, `Authority evaluation failed (${errorDetail(exc)})`);
      }
    }

    if (authResponse.decision === "DENY") {
      return this.denyMessage(toolCallId, toolName, authResponse);
    }

    // Verify the signed decision for BOTH ALLOW and ESCALATE before acting on it.
    const proofFailure = await this.verifyProofOrNull(
      authResponse,
      evalRequest,
      toolCallId,
      toolName
    );
    if (proofFailure) {
      return proofFailure;
    }

    if (authResponse.decision === "ESCALATE") {
      return this.escalateMessage(toolCallId, toolName, authResponse);
    }

    // ALLOW: execute + emit ProofArtifact.
    const result = await handler(request);

    // The side effect has now happened. A proof-build/emit or onProof failure
    // must NOT propagate — surfacing it as an error could cause the caller to
    // retry an already-executed, non-idempotent action.
    try {
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
    } catch {
      // Executed; proof persistence/callback failed. Swallow so the completed
      // execution is not reported as a failure (no logger in this package).
    }
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
    const extras = validateActionContextExtras(this.config.actionContextResolver?.(toolName, toolArgs));
    const defaultTarget = typeof toolArgs.target === "undefined" ? toolName : String(toolArgs.target);
    const parametersHash = hashParametersV1(toolArgs);
    const timestamp = new Date().toISOString();
    const intentHash = intent === null ? null : hashIntentV1(intent);
    const action: ActionContext = {
      tool: toolName,
      target: extras?.target ?? defaultTarget,
      parameters_hash: parametersHash,
      intent,
      intent_hash: intentHash,
      timestamp,
      nonce: randomUUID()
    };
    if (typeof extras?.amount_minor === "number") action.amount_minor = extras.amount_minor;
    if (typeof extras?.currency === "string") action.currency = extras.currency;
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
    evalRequest: AuthorityEvaluationRequest,
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
          aud: this.config.agentId,
          action_context_version: 1,
          action_context_hash: computeActionContextHashV1(evalRequest),
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

  private escalateMessage(toolCallId: string, toolName: string, response: AuthorityEvaluationResponse): ToolMessage {
    return new ToolMessage({
      content: JSON.stringify({
        status: "PENDING_APPROVAL",
        tool: toolName,
        approval_id: response.approval_id ?? null,
        reason_code: response.reason_code ?? null,
        proof_id: response.proof_id,
        signature: response.signature,
        constraints_evaluated: response.constraints_evaluated ?? [],
        message: `Execution of '${toolName}' is pending human approval${
          response.approval_id ? ` (approval ${response.approval_id})` : ""
        }. This is not an error. The ESCALATE decision's signature is verified; 'approval_id' is a server-issued handle, not part of the signed receipt. Present or poll the approval to continue.`
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

/**
 * A non-sensitive descriptor of a thrown value for user-facing ERROR messages.
 * Returns the error's *constructor* name (or the primitive type) — never the
 * message or the instance `.name`, both of which are writable and can carry
 * resolver/tool-arg data that would otherwise reach the LLM/user. The
 * constructor name reflects the (statically defined) class, so it is safe.
 */
function errorDetail(exc: unknown): string {
  if (exc instanceof Error) return exc.constructor?.name || "Error";
  return typeof exc;
}

function validateActionContextExtras(
  extras: ActionContextExtras | undefined
): ActionContextExtras | undefined {
  if (extras === undefined) return undefined;
  if (typeof extras !== "object" || extras === null) {
    throw new Error("actionContextResolver must return an object or undefined");
  }
  if (extras.target !== undefined && (typeof extras.target !== "string" || extras.target.trim().length === 0)) {
    throw new Error("actionContextResolver target must be a non-empty string");
  }
  const hasAmount = extras.amount_minor !== undefined;
  const hasCurrency = extras.currency !== undefined;
  if (hasAmount !== hasCurrency) {
    throw new Error("actionContextResolver must supply amount_minor and currency together, or neither");
  }
  if (hasAmount && (!Number.isSafeInteger(extras.amount_minor) || (extras.amount_minor as number) < 0)) {
    throw new Error("actionContextResolver amount_minor must be a non-negative safe integer");
  }
  if (hasCurrency && !/^[A-Z]{3}$/.test(extras.currency as string)) {
    throw new Error("actionContextResolver currency must be an uppercase ISO-4217 code");
  }
  return extras;
}

function coerceAuthorityResponse(value: unknown): AuthorityEvaluationResponse {
  if (!value || typeof value !== "object") {
    throw new Error("authority response is not an object");
  }
  const response = value as Record<string, unknown>;
  if (response.decision !== "ALLOW" && response.decision !== "DENY" && response.decision !== "ESCALATE") {
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
    approval_id:
      typeof response.approval_id === "string" || typeof response.approval_id === "number"
        ? response.approval_id
        : null,
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
