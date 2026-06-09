/**
 * LangChain.js `createAgent` adapter.
 *
 * The core {@link NuggetsAuthorityMiddleware} is driven through the
 * `ToolNode(wrapToolCall)` shape (snake_case `tool_call`). LangChain.js's
 * `createAgent({ middleware: [...] })` instead expects an `AgentMiddleware`
 * produced by `createMiddleware`, whose `wrapToolCall` receives a camelCase
 * `ToolCallRequest`. This module bridges the two — reusing the full verified
 * enforcement path (bearer auth, agent_proof signing, discover-and-pin proof
 * verification, fail-closed DENY/ERROR, proof emission) unchanged.
 *
 * Importing this module requires `langchain` (>=1.0), an optional peer
 * dependency:
 *
 * ```bash
 * npm install langchain
 * ```
 */
import { createMiddleware } from "langchain";
import type { AgentMiddleware } from "langchain";
import { NuggetsAuthorityMiddleware } from "./authorityMiddleware.js";
import { MiddlewareConfig } from "./types.js";
import type { MiddlewareConfigInput, ProofArtifact, ToolArgs } from "./types.js";

export type NuggetsAuthorityAgentMiddleware = AgentMiddleware & {
  /** Proof artifacts emitted during this middleware's lifetime. */
  readonly proofs: ProofArtifact[];
};

/**
 * Build a Nuggets Authority `AgentMiddleware` for `createAgent`.
 *
 * ```ts
 * import { createAgent } from "langchain";
 * import { createNuggetsAuthorityMiddleware } from "@nuggetslife/langchain-nuggets/agent";
 *
 * const middleware = createNuggetsAuthorityMiddleware(config);
 * const agent = createAgent({ model, tools, middleware: [middleware] });
 * // read emitted proofs via middleware.proofs
 * ```
 */
export function createNuggetsAuthorityMiddleware(
  config: MiddlewareConfig | MiddlewareConfigInput
): NuggetsAuthorityAgentMiddleware {
  const resolved = config instanceof MiddlewareConfig ? config : new MiddlewareConfig(config);
  const core = new NuggetsAuthorityMiddleware(resolved);

  const middleware = createMiddleware({
    name: "NuggetsAuthorityMiddleware",
    wrapToolCall: async (request, handler) => {
      const result = await core.wrapToolCall(
        {
          tool_call: {
            name: request.toolCall.name,
            args: (request.toolCall.args ?? {}) as ToolArgs,
            id: request.toolCall.id ?? ""
          }
        },
        () => handler(request)
      );
      return result as Awaited<ReturnType<typeof handler>>;
    }
  });

  Object.defineProperty(middleware, "proofs", {
    get: () => core.proofs,
    enumerable: true
  });
  return middleware as unknown as NuggetsAuthorityAgentMiddleware;
}
