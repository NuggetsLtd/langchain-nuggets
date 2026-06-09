import { createHash } from "node:crypto";
import type { AuthorityEvaluationResponse, ProofArtifact, ToolArgs } from "./types.js";

function sha256(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function canonicalize(value: unknown): unknown {
  if (value === undefined) {
    return undefined;
  }
  if (value === null || typeof value !== "object") {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map(canonicalize);
  }
  const out: Record<string, unknown> = {};
  for (const key of Object.keys(value as Record<string, unknown>).sort()) {
    const item = canonicalize((value as Record<string, unknown>)[key]);
    if (item !== undefined) {
      out[key] = item;
    }
  }
  return out;
}

/**
 * Escape every non-ASCII UTF-16 code unit as `\uXXXX` (lowercase hex), matching
 * Python's `json.dumps(..., ensure_ascii=True)`. Astral characters become a
 * surrogate pair of escapes, exactly as CPython emits them — so the canonical
 * string (and therefore the SHA-256 hash) is identical across the Python and
 * TypeScript SDKs.
 */
function escapeNonAscii(input: string): string {
  let out = "";
  for (let i = 0; i < input.length; i++) {
    const code = input.charCodeAt(i);
    out += code > 0x7f ? `\\u${code.toString(16).padStart(4, "0")}` : input[i];
  }
  return out;
}

export function stableStringify(value: unknown): string {
  return escapeNonAscii(JSON.stringify(canonicalize(value)));
}

export function hashParameters(args: ToolArgs): string {
  return sha256(stableStringify(args));
}

export function hashResult(result: string): string {
  return sha256(result);
}

export function hashIntent(intentString: string, parametersHash: string, timestamp: string): string {
  return sha256(`${intentString}${parametersHash}${timestamp}`);
}

export function buildProofArtifact(args: {
  authorityResponse: AuthorityEvaluationResponse;
  agentId: string;
  controllerId: string;
  delegationId: string;
  tool: string;
  parametersHash: string;
  resultHash: string;
  latencyMs: number;
  intentHash?: string | null;
  testMode?: boolean;
}): ProofArtifact {
  return {
    proof_id: args.authorityResponse.proof_id,
    agent_id: args.agentId,
    controller_id: args.controllerId,
    delegation_id: args.delegationId,
    tool: args.tool,
    parameters_hash: args.parametersHash,
    result_hash: args.resultHash,
    intent_hash: args.intentHash ?? null,
    constraints_evaluated: args.authorityResponse.constraints_evaluated ?? [],
    authority_signature: args.authorityResponse.signature,
    timestamp: new Date().toISOString(),
    latency_ms: args.latencyMs,
    test_mode: args.testMode ?? false
  };
}
