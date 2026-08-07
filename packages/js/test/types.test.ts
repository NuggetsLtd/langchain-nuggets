import { describe, expect, it } from "vitest";
import { MiddlewareConfig } from "../src/types.js";
import type { ActionContextExtras, ActionContextResolver, AuthorityDecision } from "../src/types.js";

describe("types: payment/approval contract", () => {
  it("accepts an actionContextResolver on config", () => {
    const resolver: ActionContextResolver = () => ({ amount_minor: 100, currency: "GBP", target: "did:web:merchant" });
    const cfg = new MiddlewareConfig({
      apiUrl: "https://api.nuggets.test",
      oidcIssuerUrl: "https://auth.nuggets.test",
      agentId: "a", controllerId: "c", delegationId: "d",
      agentPrivateKey: "x", verifyProofs: false,
      actionContextResolver: resolver
    });
    expect(cfg.actionContextResolver).toBe(resolver);
    const extras: ActionContextExtras = { amount_minor: 0 };
    expect(extras.amount_minor).toBe(0);
  });

  it("allows ESCALATE as a decision value", () => {
    const d: AuthorityDecision = "ESCALATE";
    expect(d).toBe("ESCALATE");
  });
});
