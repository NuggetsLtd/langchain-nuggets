import { ToolMessage } from "@langchain/core/messages";
import { describe, expect, it, vi } from "vitest";
import { createNuggetsAuthorityMiddleware } from "../src/agent.js";
import { MiddlewareConfig } from "../src/types.js";

const testConfig = () =>
  new MiddlewareConfig({
    apiUrl: "https://unreachable.invalid",
    agentId: "agent-1",
    controllerId: "org-1",
    delegationId: "del-1",
    testMode: true
  });

// Minimal LangChain.js ToolCallRequest (camelCase toolCall); the adapter only
// reads toolCall.{name,args,id} and passes the request through to the handler.
// Typed loosely — the real generic carries the full agent state schema.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const lcRequest = (): any => ({
  toolCall: { name: "external_api_call", args: { target: "stripe", amount: 100 }, id: "call-1" },
  tool: undefined,
  state: { messages: [] },
  runtime: {}
});

describe("createNuggetsAuthorityMiddleware", () => {
  it("produces a named AgentMiddleware with a wrapToolCall hook", () => {
    const mw = createNuggetsAuthorityMiddleware(testConfig());
    expect(mw.name).toBe("NuggetsAuthorityMiddleware");
    expect(typeof mw.wrapToolCall).toBe("function");
  });

  it("adapts the camelCase toolCall and runs the handler on ALLOW (test mode)", async () => {
    const mw = createNuggetsAuthorityMiddleware(testConfig());
    const handler = vi.fn(async () => new ToolMessage({ content: '{"ok": true}', tool_call_id: "call-1" }));

    const result = (await mw.wrapToolCall!(lcRequest(), handler)) as ToolMessage;

    expect(handler).toHaveBeenCalledOnce();
    expect(result.content).toContain("ok");
  });

  it("exposes proofs emitted by the underlying middleware", async () => {
    const mw = createNuggetsAuthorityMiddleware(testConfig());
    const handler = vi.fn(async () => new ToolMessage({ content: "{}", tool_call_id: "call-1" }));

    await mw.wrapToolCall!(lcRequest(), handler);

    expect(mw.proofs).toHaveLength(1);
    expect(mw.proofs[0].test_mode).toBe(true);
    expect(mw.proofs[0].tool).toBe("external_api_call");
  });

  it("accepts a plain config object as well as a MiddlewareConfig", () => {
    const mw = createNuggetsAuthorityMiddleware({
      apiUrl: "https://unreachable.invalid",
      agentId: "a",
      controllerId: "c",
      delegationId: "d",
      testMode: true
    });
    expect(mw.name).toBe("NuggetsAuthorityMiddleware");
  });
});
