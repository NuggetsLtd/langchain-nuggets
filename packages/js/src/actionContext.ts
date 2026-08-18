import { createHash } from "node:crypto";
import canonicalize from "canonicalize";
import type { ActionContext, AuthorityEvaluationRequest, ToolArgs } from "./types.js";

export const ACTION_CONTEXT_VERSION_V1 = 1 as const;
export const ACTION_CONTEXT_DOMAIN_V1 = "nuggets.acp.action_context.v1";
export const PARAMETERS_DOMAIN_V1 = "nuggets.acp.parameters.v1";
export const INTENT_DOMAIN_V1 = "nuggets.acp.intent.v1";

const SHA256_HEX = /^[0-9a-f]{64}$/;
const DELEGATION_ID = /^[1-9][0-9]*$/;

function assertJsonValue(value: unknown, path: string, allowFloats: boolean): void {
  if (value === null || typeof value === "string" || typeof value === "boolean") return;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new Error(`non-finite number at ${path}`);
    if (!allowFloats && !Number.isInteger(value)) throw new Error(`non-integer number at ${path}`);
    if (Number.isInteger(value) && !Number.isSafeInteger(value)) {
      throw new Error(`unsafe integer at ${path}`);
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertJsonValue(item, `${path}[${index}]`, allowFloats));
    return;
  }
  if (typeof value === "object" && Object.getPrototypeOf(value) === Object.prototype) {
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      if (item === undefined) throw new Error(`undefined value at ${path}.${key}`);
      assertJsonValue(item, `${path}.${key}`, allowFloats);
    }
    return;
  }
  throw new Error(`unsupported value at ${path}`);
}

function hashJcs(domain: string, value: unknown, allowFloats: boolean): string {
  assertJsonValue(value, "$", allowFloats);
  const serialized = canonicalize(value);
  if (typeof serialized !== "string") throw new Error("canonicalization produced no output");
  return createHash("sha256").update(`${domain}\n${serialized}`, "utf8").digest("hex");
}

export function hashParametersV1(parameters: ToolArgs): string {
  return hashJcs(PARAMETERS_DOMAIN_V1, parameters, true);
}

export function hashIntentV1(intent: string): string {
  if (intent.length === 0) throw new Error("intent must not be empty");
  return hashJcs(INTENT_DOMAIN_V1, intent, false);
}

function assertSha256(value: string, field: string): void {
  if (!SHA256_HEX.test(value)) throw new Error(`${field} must be lowercase SHA-256 hex`);
}

export function assertCanonicalDelegationId(value: string): string {
  if (!DELEGATION_ID.test(value) || !Number.isSafeInteger(Number(value))) {
    throw new Error("delegation_id must be a canonical positive safe integer string");
  }
  return value;
}

export function buildActionContextPreimageV1(input: {
  action: ActionContext;
  agentId: string;
  controllerId: string;
  delegationId?: string;
  environment?: string;
  agentVersion?: string;
}): Record<string, unknown> {
  const { action } = input;
  if (!action.tool) throw new Error("tool must not be empty");
  assertSha256(action.parameters_hash, "parameters_hash");
  const preimage: Record<string, unknown> = {
    action_context_version: ACTION_CONTEXT_VERSION_V1,
    tool: action.tool,
    parameters_hash: action.parameters_hash,
    agent_id: input.agentId,
    controller_id: input.controllerId
  };
  if (action.target !== undefined) preimage.target = action.target;
  if (action.intent_hash !== undefined && action.intent_hash !== null) {
    assertSha256(action.intent_hash, "intent_hash");
    preimage.intent_hash = action.intent_hash;
  }
  if (input.environment !== undefined) preimage.environment = input.environment;
  if (input.agentVersion !== undefined) preimage.agent_version = input.agentVersion;
  if (action.amount_minor !== undefined) preimage.amount_minor = action.amount_minor;
  if (action.currency !== undefined) preimage.currency = action.currency;
  if (input.delegationId !== undefined) {
    preimage.delegation_id = assertCanonicalDelegationId(input.delegationId);
  }
  return preimage;
}

export function computeActionContextHashV1(
  request: AuthorityEvaluationRequest,
  extras?: { environment?: string; agentVersion?: string }
): string {
  return hashJcs(
    ACTION_CONTEXT_DOMAIN_V1,
    buildActionContextPreimageV1({
      action: request.action,
      agentId: request.agent_id,
      controllerId: request.controller_id,
      delegationId: request.delegation_id,
      environment: extras?.environment,
      agentVersion: extras?.agentVersion
    }),
    false
  );
}
