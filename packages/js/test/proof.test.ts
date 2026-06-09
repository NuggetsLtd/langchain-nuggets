import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";
import {
  buildProofArtifact,
  hashIntent,
  hashParameters,
  hashResult,
  stableStringify
} from "../src/proof.js";
import type { AuthorityEvaluationResponse } from "../src/types.js";

const sha256Hex = (s: string) => createHash("sha256").update(s, "utf8").digest("hex");

describe("hashParameters", () => {
  it("is deterministic regardless of key order", () => {
    expect(hashParameters({ b: 2, a: 1 })).toBe(hashParameters({ a: 1, b: 2 }));
  });

  it("produces different hashes for different args", () => {
    expect(hashParameters({ amount: 100 })).not.toBe(hashParameters({ amount: 200 }));
  });

  it("hashes empty args as sha256('{}')", () => {
    expect(hashParameters({})).toBe(sha256Hex("{}"));
  });

  it("matches the Python reference hash for an ASCII vector", () => {
    // ground truth from packages/python hash_parameters({"key": "value"})
    expect(hashParameters({ key: "value" })).toBe(
      "e43abcf3375244839c012f9633f95862d232a95b00d5bc7348b3098b9fed7f32"
    );
  });

  it("matches the Python reference hash for a non-ASCII vector (ensure_ascii parity)", () => {
    // ground truth from packages/python hash_parameters({"city": "São Paulo", "emoji": "🚀"})
    expect(hashParameters({ city: "São Paulo", emoji: "🚀" })).toBe(
      "c3f77c7efb68d9b23b5c4c22daa7a9fb4ff17e3ac8e81f8370ea2a932428ecba"
    );
  });
});

describe("stableStringify", () => {
  it("sorts keys and uses compact separators", () => {
    expect(stableStringify({ b: 2, a: 1 })).toBe('{"a":1,"b":2}');
  });

  it("escapes non-ASCII as \\uXXXX to match Python json.dumps", () => {
    expect(stableStringify({ x: "é" })).toBe('{"x":"\\u00e9"}');
  });
});

describe("hashResult", () => {
  it("hashes the result string with sha256", () => {
    const result = '{"status": "success"}';
    expect(hashResult(result)).toBe(sha256Hex(result));
  });
});

describe("hashIntent", () => {
  it("is deterministic", () => {
    expect(hashIntent("transfer funds", "phash1", "2026-01-01T00:00:00Z")).toBe(
      hashIntent("transfer funds", "phash1", "2026-01-01T00:00:00Z")
    );
  });

  it("changes with intent, params, or timestamp", () => {
    const base = hashIntent("transfer funds", "phash1", "2026-01-01T00:00:00Z");
    expect(hashIntent("check balance", "phash1", "2026-01-01T00:00:00Z")).not.toBe(base);
    expect(hashIntent("transfer funds", "phash2", "2026-01-01T00:00:00Z")).not.toBe(base);
    expect(hashIntent("transfer funds", "phash1", "2026-01-02T00:00:00Z")).not.toBe(base);
  });

  it("matches sha256(intent + parametersHash + timestamp)", () => {
    expect(hashIntent("transfer funds", "phash1", "2026-01-01T00:00:00Z")).toBe(
      sha256Hex("transfer funds" + "phash1" + "2026-01-01T00:00:00Z")
    );
  });
});

describe("buildProofArtifact", () => {
  const response: AuthorityEvaluationResponse = {
    decision: "ALLOW",
    proof_id: "proof-001",
    signature: "sig-abc"
  };
  const base = {
    authorityResponse: response,
    agentId: "agent-1",
    controllerId: "org-1",
    delegationId: "del-1",
    tool: "stripe_payment",
    parametersHash: "params-hash",
    resultHash: "result-hash",
    latencyMs: 55.3
  };

  it("builds a proof from response + context", () => {
    const proof = buildProofArtifact(base);
    expect(proof.proof_id).toBe("proof-001");
    expect(proof.agent_id).toBe("agent-1");
    expect(proof.authority_signature).toBe("sig-abc");
    expect(proof.tool).toBe("stripe_payment");
    expect(proof.latency_ms).toBe(55.3);
    expect(proof.timestamp).toContain("T");
    expect(proof.timestamp.endsWith("Z") || proof.timestamp.endsWith("+00:00")).toBe(true);
  });

  it("includes intent_hash when provided, null otherwise", () => {
    expect(buildProofArtifact({ ...base, intentHash: "intent-hash-abc" }).intent_hash).toBe(
      "intent-hash-abc"
    );
    expect(buildProofArtifact(base).intent_hash).toBeNull();
  });

  it("carries constraints_evaluated from the response, [] by default", () => {
    expect(
      buildProofArtifact({
        ...base,
        authorityResponse: { ...response, constraints_evaluated: ["tool_allowed", "cap_remaining"] }
      }).constraints_evaluated
    ).toEqual(["tool_allowed", "cap_remaining"]);
    expect(buildProofArtifact(base).constraints_evaluated).toEqual([]);
  });
});
