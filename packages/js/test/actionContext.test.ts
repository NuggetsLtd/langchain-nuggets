import { describe, expect, it } from "vitest";
import {
  computeActionContextHashV1,
  hashIntentV1,
  hashParametersV1
} from "../src/actionContext.js";
import type { AuthorityEvaluationRequest } from "../src/types.js";

function request(action: AuthorityEvaluationRequest["action"], delegationId: string): AuthorityEvaluationRequest {
  return {
    agent_id: "did:web:a",
    controller_id: "did:web:c",
    delegation_id: delegationId,
    action
  };
}

describe("ACP action context v1 golden vectors", () => {
  it("matches the frozen full-payment vector from partner#958", () => {
    const value: AuthorityEvaluationRequest = {
      agent_id: "did:web:agent.example",
      controller_id: "did:web:controller.example",
      delegation_id: "7",
      action: {
        tool: "nuggets.payment.send",
        target: "acct_123",
        parameters_hash: "a".repeat(64),
        intent_hash: "285d9d1bfc0501e36164a9f01aa63f6ac1b178b1a8163f87a58976b143f83331",
        amount_minor: 4200,
        currency: "GBP",
        timestamp: "excluded",
        nonce: "excluded"
      }
    };
    expect(computeActionContextHashV1(value, {
      environment: "production",
      agentVersion: "1.4.0"
    })).toBe("a2451c2a946c4d74eea3ac7cbde24d79a4ee1013adaba418e221ccde0554e491");
  });

  it("matches the frozen zero-amount vector", () => {
    expect(computeActionContextHashV1(request({
      tool: "refund",
      parameters_hash: "d".repeat(64),
      amount_minor: 0,
      currency: "USD",
      timestamp: "excluded",
      nonce: "excluded"
    }, "42"))).toBe("2665a9b78f32716f6537d98073971ee0654a29910637fd4f46b7e44c236d5e7d");
  });

  it("matches intent and decimal-parameter interop vectors", () => {
    expect(hashIntentV1("pay invoice 42")).toBe(
      "285d9d1bfc0501e36164a9f01aa63f6ac1b178b1a8163f87a58976b143f83331"
    );
    expect(hashIntentV1("café — π ☃ \n \"q\"")).toBe(
      "8721494a1b2e22cced778a94ef86183160d43d28de4af0b0fb64ec0b7b17579b"
    );
    expect(hashParametersV1({ quantity: 1.5, label: "café" })).toBe(
      "734b0e8e8dc237d27ceaa0c8965cf213a0451f3effc2bb99d8a7b48dc91481d8"
    );
  });

  it("rejects alternate delegation spellings and unsafe parameter numbers", () => {
    const action = {
      tool: "t",
      parameters_hash: "f".repeat(64),
      timestamp: "excluded",
      nonce: "excluded"
    };
    expect(() => computeActionContextHashV1(request(action, "042"))).toThrow(/delegation_id/);
    expect(() => hashParametersV1({ value: Number.MAX_SAFE_INTEGER + 1 })).toThrow(/unsafe/);
    expect(() => hashParametersV1({ value: Number.NaN })).toThrow(/non-finite/);
  });
});
