# Authority Payment / Approval Contract Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Teach both SDKs the money/approval half of the ACP action contract — a scoped `nuggets.payments.send` call can carry `amount_minor`/`currency` and resolve to ALLOW, ESCALATE (human approval), or DENY, with ESCALATE surfaced as a first-class non-error pending state.

**Architecture:** Add an opt-in, typed `actionContextResolver` (JS) / `action_context_resolver` (Python) to middleware config that maps a tool call to `{ target?, amount_minor?, currency? }`. `buildEvalRequest` validates and merges it into the signed action (existing `target`-from-args stays the default). Extend the decision enum to include `ESCALATE`; on ESCALATE the wrapped tool never runs and a structured pending-approval `ToolMessage` (distinct from DENY/ERROR) is returned. Proof verification stays on for ALLOW only. JS and Python must stay behaviourally symmetric.

**Tech Stack:** TypeScript (vitest), Python 3.9+/pydantic v2 (pytest, pytest-asyncio), `@langchain/core` / `langchain-core` `ToolMessage`.

---

## Ground rules

- **TDD:** write the failing test first, watch it fail, implement the minimum, watch it pass, commit.
- **Parity:** every behaviour added to JS must have a matching Python test and vice-versa. Keep validation rules byte-identical (same amount/currency rules, same fail-closed semantics).
- **Fail closed:** a resolver that throws or returns invalid money fields must return an `ERROR` `ToolMessage` **before** the handler runs — in every mode, including `testMode`.
- **Never guess money fields** from arbitrary tool args. Only the resolver supplies `amount_minor`/`currency`. The only implicit behaviour retained is `target` defaulting to `toolArgs.target ?? toolName`.
- **Secrets:** never write a key, delegation token, or private JWKS into code, tests, fixtures, logs, or docs.
- **No real payments:** smoke handlers stay no-ops and must say so in output.

**Validation rules (both SDKs):**
- `amount_minor` / `currency` are a **pair**: both absent is allowed (non-monetary tools); if **either** is supplied, **both** are required. Supplying one without the other fails closed — this stops a half-formed payment action from reaching ACP.
- `amount_minor`: present ⇒ a non-negative safe integer (JS `Number.isSafeInteger` and `>= 0`; Python `isinstance(x, int) and not isinstance(x, bool) and x >= 0`). Otherwise fail closed.
- `currency`: present ⇒ matches `^[A-Z]{3}$`. Otherwise fail closed.
- `target`: present ⇒ non-empty string; overrides the args default. Absent ⇒ keep existing default.

**Run commands:**
- JS: `cd packages/js && npm test` (single file: `npx vitest run test/authorityMiddleware.test.ts`)
- Python: `cd packages/python && python -m pytest tests/middleware/test_authority_middleware.py -v`

---

## Task 1: JS types — extend the contract

**Files:**
- Modify: `packages/js/src/types.ts`
- Test: `packages/js/test/types.test.ts` (create if absent) — otherwise assert compile-time shape via a new resolver-validation unit in Task 2.

**Step 1: Write the failing test**

Add `packages/js/test/types.test.ts`:

```ts
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
```

**Step 2: Run to verify it fails** — `cd packages/js && npx vitest run test/types.test.ts` → FAIL (type/property missing, `agentPrivateKey: "x"` is fine because a raw non-PEM string is only validated at load time; if construction throws, use the real `agentPem` helper from `authorityMiddleware.test.ts` instead).

**Step 3: Implement** in `packages/js/src/types.ts`:

- Add exported types near `IntentResolver` (line ~20):

```ts
export type ActionContextExtras = {
  target?: string;
  amount_minor?: number;
  currency?: string;
};

export type ActionContextResolver = (
  toolName: string,
  toolArgs: ToolArgs
) => ActionContextExtras | undefined;
```

- Add `actionContextResolver?: ActionContextResolver;` to `MiddlewareConfigInput` (after `intentResolver`, ~line 36) and to the `MiddlewareConfig` class fields + constructor assignment (`this.actionContextResolver = input.actionContextResolver;`).
- Extend `ActionContext` (line ~89) with optional money fields:

```ts
export interface ActionContext {
  tool: string;
  target?: string;
  amount_minor?: number;
  currency?: string;
  parameters_hash: string;
  intent?: string | null;
  intent_hash?: string | null;
  timestamp: string;
  nonce: string;
}
```

- Change the decision union (line 107):

```ts
export type AuthorityDecision = "ALLOW" | "DENY" | "ESCALATE";
```

- Extend `AuthorityEvaluationResponse` (line ~109) with an approval identifier:

```ts
export interface AuthorityEvaluationResponse {
  decision: AuthorityDecision;
  proof_id: string;
  signature: string;
  reason_code?: string | null;
  approval_id?: string | null;
  constraints_evaluated?: string[];
}
```

**Step 4: Run** `npx vitest run test/types.test.ts` → PASS.

**Step 5: Commit** — `git add packages/js/src/types.ts packages/js/test/types.test.ts && git commit -m "feat(js): add payment/approval fields to authority contract types"`

---

## Task 2: JS middleware — resolver merge + validation (fail closed)

**Files:**
- Modify: `packages/js/src/authorityMiddleware.ts` (`buildEvalRequest` ~line 111; `wrapToolCall` ~line 44)
- Test: `packages/js/test/authorityMiddleware.test.ts`

**Step 1: Write the failing tests** — append a `describe("action context resolver", ...)` block:

```ts
describe("action context resolver", () => {
  it("merges validated amount_minor/currency/target into the signed action", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig({
      actionContextResolver: () => ({ amount_minor: 100, currency: "GBP", target: "did:web:merchant" })
    }));
    const post = allowPost();
    withClient(mw, post);
    await mw.wrapToolCall(
      { tool_call: { name: "nuggets.payments.send", args: { note: "x" }, id: "c1" } },
      handler()
    );
    const action = post.mock.calls[0][1].action;
    expect(action.amount_minor).toBe(100);
    expect(action.currency).toBe("GBP");
    expect(action.target).toBe("did:web:merchant");
  });

  it("keeps the args.target default when the resolver omits target", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig({
      actionContextResolver: () => ({ amount_minor: 100, currency: "GBP" })
    }));
    const post = allowPost();
    withClient(mw, post);
    await mw.wrapToolCall(
      { tool_call: { name: "nuggets.payments.send", args: { target: "stripe" }, id: "c1" } },
      handler()
    );
    expect(post.mock.calls[0][1].action.target).toBe("stripe");
  });

  it("fails closed (ERROR, handler not called) on invalid amount_minor", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig({
      actionContextResolver: () => ({ amount_minor: -1, currency: "GBP" })
    }));
    const h = handler();
    withClient(mw, allowPost());
    const res = (await mw.wrapToolCall(
      { tool_call: { name: "nuggets.payments.send", args: {}, id: "c1" } }, h
    )) as ToolMessage;
    expect(h).not.toHaveBeenCalled();
    expect(JSON.parse(res.content as string).status).toBe("ERROR");
  });

  it("fails closed on invalid currency", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig({
      actionContextResolver: () => ({ amount_minor: 100, currency: "gbp" })
    }));
    const h = handler();
    const res = (await mw.wrapToolCall(
      { tool_call: { name: "nuggets.payments.send", args: {}, id: "c1" } }, h
    )) as ToolMessage;
    expect(h).not.toHaveBeenCalled();
    expect(JSON.parse(res.content as string).status).toBe("ERROR");
  });

  it("fails closed when amount is supplied without currency (and vice-versa)", async () => {
    for (const extras of [{ amount_minor: 100 }, { currency: "GBP" }]) {
      const mw = new NuggetsAuthorityMiddleware(makeConfig({ actionContextResolver: () => extras }));
      const h = handler();
      const res = (await mw.wrapToolCall(
        { tool_call: { name: "nuggets.payments.send", args: {}, id: "c1" } }, h
      )) as ToolMessage;
      expect(h).not.toHaveBeenCalled();
      expect(JSON.parse(res.content as string).status).toBe("ERROR");
    }
  });

  it("allows both amount and currency to be absent (non-monetary tool)", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig({
      actionContextResolver: () => ({ target: "did:web:merchant" })
    }));
    const post = allowPost();
    withClient(mw, post);
    await mw.wrapToolCall(
      { tool_call: { name: "lookup", args: {}, id: "c1" } }, handler()
    );
    const action = post.mock.calls[0][1].action;
    expect(action.amount_minor).toBeUndefined();
    expect(action.currency).toBeUndefined();
  });

  it("fails closed when the resolver throws — before the handler and even in testMode", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig({
      testMode: true,
      actionContextResolver: () => { throw new Error("resolver boom"); }
    }));
    const h = handler();
    const res = (await mw.wrapToolCall(
      { tool_call: { name: "nuggets.payments.send", args: {}, id: "c1" } }, h
    )) as ToolMessage;
    expect(h).not.toHaveBeenCalled();
    expect(JSON.parse(res.content as string).status).toBe("ERROR");
  });
});
```

**Step 2: Run** → FAIL (fields absent / resolver not invoked / buildEvalRequest throws uncaught).

**Step 3: Implement**

In `authorityMiddleware.ts`:

1. Wrap the `buildEvalRequest` call so a throw becomes a fail-closed ERROR in all modes. Replace line 52 (`const evalRequest = this.buildEvalRequest(...)`) region:

```ts
let evalRequest: AuthorityEvaluationRequest;
try {
  evalRequest = this.buildEvalRequest(toolName, toolArgs);
} catch (exc) {
  return this.errorMessage(toolCallId, toolName, `Action context resolution failed: ${exc}`);
}
const start = performance.now();
```

2. In `buildEvalRequest`, resolve and validate extras, then merge:

```ts
buildEvalRequest(toolName: string, toolArgs: ToolArgs): AuthorityEvaluationRequest {
  const intent = this.config.intentResolver?.(toolName, toolArgs) ?? null;
  const extras = validateActionContextExtras(this.config.actionContextResolver?.(toolName, toolArgs));
  const defaultTarget = typeof toolArgs.target === "undefined" ? toolName : String(toolArgs.target);
  const parametersHash = hashParameters(toolArgs);
  const timestamp = new Date().toISOString();
  const intentHash = intent === null ? null : hashIntent(intent, parametersHash, timestamp);
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
```

3. Add a module-level validator (bottom of file, near `coerceAuthorityResponse`):

```ts
function validateActionContextExtras(
  extras: ActionContextExtras | undefined
): ActionContextExtras | undefined {
  if (extras === undefined) return undefined;
  if (typeof extras !== "object" || extras === null) {
    throw new Error("actionContextResolver must return an object or undefined");
  }
  if (extras.target !== undefined && (typeof extras.target !== "string" || extras.target.length === 0)) {
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
```

4. Add `ActionContextExtras` to the type imports at the top of the file.

**Step 4: Run** → PASS.

**Step 5: Commit** — `git commit -am "feat(js): opt-in action-context resolver for payment amount/currency (fail closed)"`

---

## Task 3: JS middleware — ESCALATE as a verified, first-class result

ACP signs final `ALLOW`, `ESCALATE`, and post-auth `DENY` decisions. The SDK **requires and verifies** the ESCALATE signature before returning `PENDING_APPROVAL` — the approval state is customer-facing, so it must be as trustworthy as ALLOW. No post-execution `ProofArtifact` is emitted (no tool ran), but the verified signed decision/receipt data (proof_id, signature, constraints) is returned alongside the pending-approval result.

**Files:**
- Modify: `packages/js/src/authorityMiddleware.ts` (`coerceAuthorityResponse`, `wrapToolCall`; add `escalateMessage`)
- Test: `packages/js/test/authorityMiddleware.test.ts`

**Step 1: Write the failing tests.** Use `verifyProofs: false` for the routing tests, and mirror the existing "passes through and emits a proof when the signature is a verifiable JWS" test (lines ~256-303) for the verified-ESCALATE test — same fetch stub, same portal keypair, but `decision: "ESCALATE"` in both the SignJWT body and the response.

```ts
describe("ESCALATE decision", () => {
  const escalateResponse = () => ({
    decision: "ESCALATE" as const,
    proof_id: "proof-esc",
    signature: "sig-esc",
    reason_code: "APPROVAL_REQUIRED",
    approval_id: "appr-123",
    constraints_evaluated: ["approval_threshold"]
  });

  it("does not call the handler and returns PENDING_APPROVAL (not ERROR/DENIED)", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig()); // verifyProofs: false
    withClient(mw, vi.fn(async () => escalateResponse()));
    const h = handler();
    const res = (await mw.wrapToolCall(request(), h)) as ToolMessage;
    expect(h).not.toHaveBeenCalled();
    const data = JSON.parse(res.content as string);
    expect(data.status).toBe("PENDING_APPROVAL");
    expect(data.approval_id).toBe("appr-123");
    expect(data.reason_code).toBe("APPROVAL_REQUIRED");
  });

  it("emits no proof artifact on ESCALATE", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig());
    withClient(mw, vi.fn(async () => escalateResponse()));
    await mw.wrapToolCall(request(), handler());
    expect(mw.proofs).toHaveLength(0);
  });

  it("rejects an ESCALATE response with no signature", async () => {
    const mw = new NuggetsAuthorityMiddleware(makeConfig());
    withClient(mw, vi.fn(async () => ({ decision: "ESCALATE", proof_id: "p", approval_id: "a" })));
    const res = (await mw.wrapToolCall(request(), handler())) as ToolMessage;
    // coerce throws → fail-closed ERROR
    expect(JSON.parse(res.content as string).status).toBe("ERROR");
  });

  it("fails closed (PROOF_VERIFICATION_FAILED) on ESCALATE with an unverifiable signature", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("no network"); }));
    const mw = new NuggetsAuthorityMiddleware(makeConfig({ verifyProofs: true }));
    withClient(mw, vi.fn(async () => escalateResponse()));
    const h = handler();
    const res = (await mw.wrapToolCall(request(), h)) as ToolMessage;
    expect(h).not.toHaveBeenCalled();
    const data = JSON.parse(res.content as string);
    expect(data.status).toBe("DENIED");
    expect(data.reason_code).toBe("PROOF_VERIFICATION_FAILED");
  });

  it("verifies the signature then returns PENDING_APPROVAL with the verified receipt", async () => {
    // mirror the ALLOW verifiable-JWS test: portal keypair + fetch stub for
    // authority-configuration + jwks, but decision "ESCALATE".
    // ... build proofJws with { proof_id, agent_id, controller_id, constraints_evaluated,
    //     decision: "ESCALATE", iss } ...
    const mw = new NuggetsAuthorityMiddleware(makeConfig({ verifyProofs: true }));
    withClient(mw, vi.fn(async () => ({
      decision: "ESCALATE", proof_id: "proof-real", signature: proofJws,
      approval_id: "appr-1", reason_code: "APPROVAL_REQUIRED", constraints_evaluated: ["tool_allowed"]
    })));
    const h = handler();
    const res = (await mw.wrapToolCall(request(), h)) as ToolMessage;
    expect(h).not.toHaveBeenCalled();
    const data = JSON.parse(res.content as string);
    expect(data.status).toBe("PENDING_APPROVAL");
    expect(data.approval_id).toBe("appr-1");
    expect(data.proof_id).toBe("proof-real");   // verified receipt data present
    expect(data.signature).toBe(proofJws);
    expect(mw.proofs).toHaveLength(0);           // still no post-execution ProofArtifact
  });
});
```

**Step 2: Run** → FAIL (`coerceAuthorityResponse` rejects ESCALATE / no PENDING_APPROVAL path).

**Step 3: Implement**

1. `coerceAuthorityResponse`: accept `ESCALATE`; **keep `proof_id` and `signature` required for all three decisions** (ALLOW, DENY, ESCALATE are all signed). Parse `approval_id`:

```ts
if (response.decision !== "ALLOW" && response.decision !== "DENY" && response.decision !== "ESCALATE") {
  throw new Error("authority response missing decision");
}
if (typeof response.proof_id !== "string") throw new Error("authority response missing proof_id");
if (typeof response.signature !== "string") throw new Error("authority response missing signature");
return {
  decision: response.decision,
  proof_id: response.proof_id,
  signature: response.signature,
  reason_code: typeof response.reason_code === "string" ? response.reason_code : null,
  approval_id: typeof response.approval_id === "string" ? response.approval_id : null,
  constraints_evaluated: Array.isArray(response.constraints_evaluated)
    ? response.constraints_evaluated.filter((i): i is string => typeof i === "string")
    : []
};
```

2. In `wrapToolCall`, **verify the proof for ESCALATE too**, then branch. Reorder so verification runs for both ALLOW and ESCALATE (it already checks `authResponse.decision` in the expected payload, so an ESCALATE-signed decision verifies correctly). After the DENY check (line ~79):

```ts
// DENY handled above and returns early.
// Verify the signed decision for BOTH ALLOW and ESCALATE before acting on it.
const proofFailure = await this.verifyProofOrNull(authResponse, toolCallId, toolName);
if (proofFailure) {
  return proofFailure;
}

if (authResponse.decision === "ESCALATE") {
  return this.escalateMessage(toolCallId, toolName, authResponse);
}

// ALLOW: execute + emit ProofArtifact (unchanged below).
```

Delete the now-duplicated `verifyProofOrNull` call that previously sat only on the ALLOW path (lines ~81-84) so verification happens exactly once.

3. Add `escalateMessage` — includes the verified receipt data:

```ts
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
      }. This is not an error; the signed authority decision is verified — poll or present the approval to continue.`
    }),
    tool_call_id: toolCallId
  });
}
```

**Step 4: Run** the whole JS suite → PASS. Re-run DENY + ALLOW verification tests to confirm no regression from reordering.

**Step 5: Commit** — `git commit -am "feat(js): verify and surface ESCALATE as a first-class pending-approval result"`

---

## Task 4: JS smoke script — synthetic amount/currency + ESCALATE

**Files:**
- Modify: `packages/js/scripts/smoke-test-authority.mjs`

**Step 1: Implement** (no unit test — it is a live-only script; verify by `node --check`):

- Read optional `NUGGETS_AMOUNT_MINOR` / `NUGGETS_CURRENCY`. When either is set, pass an `actionContextResolver` to `MiddlewareConfig`:

```js
const amountMinor = env("NUGGETS_AMOUNT_MINOR", false);
const currency = env("NUGGETS_CURRENCY", false);
const actionContextResolver = (amountMinor || currency)
  ? () => ({
      ...(amountMinor ? { amount_minor: Number(amountMinor) } : {}),
      ...(currency ? { currency } : {}),
      ...(target ? { target } : {})
    })
  : undefined;
```

  (Add `actionContextResolver` to the `new MiddlewareConfig({...})` call. Note `target` is already read below — move its `env()` read above the config, or inline.)

- Handle the new status in the result switch:

```js
if (parsed.status === "PENDING_APPROVAL") {
  console.log(`⏸ ESCALATE — approval ${parsed.approval_id ?? "?"} (${parsed.reason_code ?? ""}); no tool executed, no payment made`);
  process.exit(0);
}
```

- Update the handler comment / add a banner line making the no-payment guarantee explicit:

```js
console.log("NOTE: smoke handler is a no-op — it does NOT execute any payment.");
```

**Step 2: Verify** — `node --check packages/js/scripts/smoke-test-authority.mjs` → no output (valid).

**Step 3: Commit** — `git commit -am "feat(js): smoke script supports synthetic amount/currency and ESCALATE"`

---

## Task 5: Python types — mirror the contract

**Files:**
- Modify: `packages/python/langchain_nuggets/middleware/types.py`
- Test: `packages/python/tests/middleware/test_types.py`

**Step 1: Write the failing test:**

```python
def test_action_context_accepts_amount_and_currency():
    from langchain_nuggets.middleware.types import ActionContext
    ac = ActionContext(tool="nuggets.payments.send", target="did:web:m",
                        amount_minor=100, currency="GBP",
                        parameters_hash="h", timestamp="t")
    assert ac.amount_minor == 100 and ac.currency == "GBP"


def test_escalate_is_a_valid_decision():
    from langchain_nuggets.middleware.types import AuthorityEvaluationResponse
    r = AuthorityEvaluationResponse(decision="ESCALATE", proof_id="p",
                                    signature="s", approval_id="appr-1")
    assert r.decision == "ESCALATE" and r.approval_id == "appr-1"


def test_config_accepts_action_context_resolver():
    from langchain_nuggets.middleware.types import MiddlewareConfig
    cfg = MiddlewareConfig(api_url="https://x", agent_id="a", controller_id="c",
                           delegation_id="d", test_mode=True,
                           action_context_resolver=lambda name, args: {"amount_minor": 1})
    assert cfg.action_context_resolver is not None
```

**Step 2: Run** `cd packages/python && python -m pytest tests/middleware/test_types.py -v` → FAIL.

**Step 3: Implement** in `types.py`:

- `MiddlewareConfig`: add after `intent_resolver` (line ~27):

```python
action_context_resolver: Optional[
    Callable[[str, Dict[str, Any]], Optional[Dict[str, Any]]]
] = None
```

- `ActionContext`: add `amount_minor: Optional[int] = None` and `currency: Optional[str] = None` (after `target`).
- Decision alias (line 99): `AuthorityDecision = Literal["ALLOW", "DENY", "ESCALATE"]`.
- `AuthorityEvaluationResponse`: add `approval_id: Optional[str] = None`.

**Step 4: Run** → PASS.

**Step 5: Commit** — `git commit -am "feat(py): add payment/approval fields to authority contract types"`

---

## Task 6: Python middleware — resolver merge + validation (fail closed)

**Files:**
- Modify: `packages/python/langchain_nuggets/middleware/authority_middleware.py` (`_build_eval_request` ~line 116; `wrap_tool_call` ~line 264 and `awrap_tool_call` ~line 347)
- Test: `packages/python/tests/middleware/test_authority_middleware.py`

**Step 1: Write the failing tests** (mirror the JS Task 2 cases — use the file's existing fixtures/patterns for building a middleware with a mocked client; check how `test_authority_middleware.py` fakes `_client.post`). Cover:
- resolver amount/currency/target appear in the posted payload's `action`;
- args-target default retained when resolver omits target;
- invalid `amount_minor` (-1) ⇒ handler not called, status `ERROR`;
- invalid `currency` ("gbp") ⇒ handler not called, status `ERROR`;
- amount without currency (and currency without amount) ⇒ handler not called, status `ERROR`;
- both amount and currency absent (non-monetary tool) ⇒ ALLOW proceeds, action has `amount_minor=None`, `currency=None`;
- resolver raises ⇒ status `ERROR`, handler not called, including `test_mode=True`;
- async parity: one `awrap_tool_call` test for the resolver-merge case (use `pytest.mark.asyncio`).

**Step 2: Run** → FAIL.

**Step 3: Implement**

1. Add a module-level validator:

```python
import re

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


def _validate_action_context_extras(extras: Any) -> Optional[Dict[str, Any]]:
    if extras is None:
        return None
    if not isinstance(extras, dict):
        raise ValueError("action_context_resolver must return a dict or None")
    target = extras.get("target")
    if target is not None and (not isinstance(target, str) or not target):
        raise ValueError("action_context_resolver target must be a non-empty string")
    amount = extras.get("amount_minor")
    currency = extras.get("currency")
    if (amount is None) != (currency is None):
        raise ValueError(
            "action_context_resolver must supply amount_minor and currency together, or neither"
        )
    if amount is not None and (isinstance(amount, bool) or not isinstance(amount, int) or amount < 0):
        raise ValueError("action_context_resolver amount_minor must be a non-negative integer")
    if currency is not None and not (isinstance(currency, str) and _CURRENCY_RE.match(currency)):
        raise ValueError("action_context_resolver currency must be an uppercase ISO-4217 code")
    return extras
```

2. `_build_eval_request`: resolve + validate + merge:

```python
extras = None
if self._config.action_context_resolver is not None:
    extras = _validate_action_context_extras(
        self._config.action_context_resolver(tool_name, tool_args)
    )

default_target = tool_args.get("target", tool_name) if isinstance(tool_args, dict) else tool_name
target = extras.get("target") if extras and extras.get("target") else default_target
# ... existing parameters_hash / timestamp / intent_hash ...
return AuthorityEvaluationRequest(
    agent_id=self._config.agent_id,
    controller_id=self._config.controller_id,
    delegation_id=self._config.delegation_id,
    action=ActionContext(
        tool=tool_name,
        target=str(target),
        amount_minor=extras.get("amount_minor") if extras else None,
        currency=extras.get("currency") if extras else None,
        parameters_hash=parameters_hash,
        intent=intent,
        intent_hash=intent_hash,
        timestamp=timestamp,
    ),
)
```

3. Fail-closed wrapping: in **both** `wrap_tool_call` and `awrap_tool_call`, wrap the `eval_request = self._build_eval_request(...)` call in try/except returning the `ERROR` `ToolMessage` (reuse the existing ERROR shape) so a resolver failure short-circuits before the handler in every mode:

```python
try:
    eval_request = self._build_eval_request(tool_name, tool_args)
except Exception as exc:  # fail closed before any tool execution
    logger.error("Action context resolution failed: %s", exc)
    return ToolMessage(
        content=json.dumps({"status": "ERROR", "tool": tool_name,
                            "message": f"Action context resolution failed: {exc}"}),
        tool_call_id=tool_call_id,
    )
start_time = time.monotonic()
```

> `model_dump()` already serialises the new optional action fields; when they are `None` the backend simply sees them absent/null — confirm the smoke matrix (Task 11) that a null amount still behaves as before.

**Step 4: Run** → PASS.

**Step 5: Commit** — `git commit -am "feat(py): opt-in action-context resolver for payment amount/currency (fail closed)"`

---

## Task 7: Python middleware — ESCALATE as a verified, first-class result

Mirror JS Task 3: ESCALATE is a signed decision, so **require and verify** its signature before returning `PENDING_APPROVAL`. Emit no `ProofArtifact` (no tool ran), but return the verified signed decision/receipt data with the pending-approval result. `signature` stays a **required** field (do not add a default).

**Files:**
- Modify: `authority_middleware.py` (add `_make_escalate_message`; verify-then-branch in both `wrap_tool_call` and `awrap_tool_call`)
- Test: `packages/python/tests/middleware/test_authority_middleware.py`

**Step 1: Write the failing tests** (sync + async parity), mirroring how the file's existing ALLOW proof-verification tests stub `discover_authority` / `verify_authority_proof` (and their `a*` variants):
- ESCALATE with `verify_proofs=False` ⇒ handler not called, `status == "PENDING_APPROVAL"`, `approval_id` + `reason_code` present, `middleware.proofs == []`;
- ESCALATE where verification **succeeds** ⇒ `PENDING_APPROVAL` and the result carries the verified `proof_id`/`signature`; still `proofs == []`;
- ESCALATE where verification **fails** ⇒ `status == "DENIED"`, `reason_code == "PROOF_VERIFICATION_FAILED"`, handler not called;
- `AuthorityEvaluationResponse(**{no signature})` for ESCALATE ⇒ pydantic `ValidationError` (signature required).

**Step 2: Run** → FAIL.

**Step 3: Implement**

1. Add:

```python
def _make_escalate_message(self, tool_call_id, tool_name, response):
    content = json.dumps({
        "status": "PENDING_APPROVAL",
        "tool": tool_name,
        "approval_id": response.approval_id,
        "reason_code": response.reason_code,
        "proof_id": response.proof_id,
        "signature": response.signature,
        "constraints_evaluated": response.constraints_evaluated,
        "message": (
            f"Execution of '{tool_name}' is pending human approval"
            + (f" (approval {response.approval_id})" if response.approval_id else "")
            + ". This is not an error; the signed authority decision is verified — "
            + "poll or present the approval to continue."
        ),
    })
    return ToolMessage(content=content, tool_call_id=tool_call_id)
```

2. In **both** `wrap_tool_call` and `awrap_tool_call`, reorder so verification runs for ALLOW **and** ESCALATE, then branch. After the `DENY` block:

```python
# sync
proof_failure = self._verify_proof_or_none(auth_response, tool_call_id, tool_name)
if proof_failure is not None:
    return proof_failure
if auth_response.decision == "ESCALATE":
    logger.info("ESCALATE: tool=%s approval_id=%s", tool_name, auth_response.approval_id)
    return self._make_escalate_message(tool_call_id, tool_name, auth_response)
# ALLOW falls through to handler + proof emission (unchanged)
```

(async: use `await self._averify_proof_or_none(...)`; `_proof_expected` already sends `auth_response.decision`, so an ESCALATE-signed decision verifies with the same code.) Remove the old ALLOW-only `_verify_proof_or_none` call so verification happens exactly once.

3. Leave `AuthorityEvaluationResponse.signature: str` **required** (from Task 5 it already is). Add the parse-fails-without-signature test noted above.

**Step 4: Run** the whole Python middleware suite → PASS (watch for DENY/ALLOW regressions from the reorder).

**Step 5: Commit** — `git commit -am "feat(py): verify and surface ESCALATE as a first-class pending-approval result"`

---

## Task 8: Python smoke script — synthetic amount/currency + ESCALATE

**Files:**
- Modify: `scripts/smoke_test_authority.py`

**Step 1: Implement:**

- Read optional `NUGGETS_AMOUNT_MINOR` / `NUGGETS_CURRENCY`; when either is set, pass `action_context_resolver=lambda name, a: {...}` to `MiddlewareConfig` (only include keys that are set; include `target` when present).
- Add a `PENDING_APPROVAL` branch to the result handling that prints the approval id + reason and exits 0 (distinct from the DENIED/ERROR `fail(...)`).
- Add an explicit stdout line: `NOTE: smoke handler is a no-op — it does NOT execute any payment.`

**Step 2: Verify** — `cd packages/python && python -c "import ast; ast.parse(open('../../scripts/smoke_test_authority.py').read())"` (or `python -m py_compile scripts/smoke_test_authority.py` from repo root) → no error.

**Step 3: Commit** — `git commit -am "feat(py): smoke script supports synthetic amount/currency and ESCALATE"`

---

## Task 9: Documentation

**Files:**
- Modify: `packages/js/README.md`, `packages/python/README.md`, `docs/agent-provisioning.md`

**Step 1: Edit** — add to each, matching that doc's existing tone:

- `NUGGETS_TOOL` must **exactly match** the delegation capability (e.g. `nuggets.payments.send`).
- Use an **action-context resolver** to supply payment `amount_minor` (minor units, integer) and `currency` (ISO-4217, uppercase); show the JS `actionContextResolver` / Python `action_context_resolver` config option with a short `nuggets.payments.send` example.
- **ESCALATE pauses execution** — the middleware returns a `PENDING_APPROVAL` `ToolMessage` with an `approval_id` and the verified signed authority decision; it is **not** an SDK error. Applications should present or poll the approval. The ESCALATE signature is verified just like ALLOW.
- Private JWKS belongs in a **secret store or mounted secret**, never source control, logs, or `Downloads`; treat previously downloaded keys as stale.
- In `agent-provisioning.md`, add the new `NUGGETS_AMOUNT_MINOR` / `NUGGETS_CURRENCY` smoke env vars near the existing `NUGGETS_TOOL` block, and note the amount-capped GBP delegation → currency-scope requirement (a GBP amount-capped delegation rejects a call with no `amount_minor`/`currency` as out of currency scope).

**Step 2: Verify** — no dev-only knobs leak into user docs; keep it to the public config surface.

**Step 3: Commit** — `git commit -am "docs: document action-context resolver, ESCALATE, and key hygiene"`

---

## Task 10: Version bump to 1.1.0

**Files:**
- Modify: `packages/js/package.json` (`"version": "1.1.0"`), `packages/python/pyproject.toml` (`version = "1.1.0"`)

Additive change that expands the set of possible decisions → **minor** bump per the handover. Also check for a `packages/js/src/index.ts` or exported version constant and any CHANGELOG; update if present.

**Commit** — `git commit -am "chore: release 1.1.0 (payment/approval contract)"`

---

## Task 11: Full verification + deployed smoke matrix

> REQUIRED SUB-SKILL: superpowers:verification-before-completion — run the commands, paste real output, no success claims without evidence.

**Step 1: Unit + lint, both packages**

```bash
cd packages/js && npm test && npm run build
cd packages/python && python -m pytest -q && ruff check . && mypy .   # use the repo's configured commands
```

Expected: all green. Confirm the acceptance matrix is represented in unit tests:
- resolver fields appear in the signed request ✓ (Task 2/6)
- missing/invalid resolver output fails closed, handler not called ✓
- ALLOW verifies proof + executes exactly once ✓ (existing tests still pass)
- DENY never executes ✓ (existing)
- ESCALATE never executes and returns PENDING_APPROVAL (not ERROR) ✓ (Task 3/7)

**Step 2: ESCALATE verification.** The signed-decision verifier now runs for both ALLOW and ESCALATE. Unit tests cover verify-success and verify-failure paths (Tasks 3/7). The deployed smoke (Step 3) confirms the real backend's ESCALATE response verifies against the portal's published keys end-to-end — the £5.00 row is the ESCALATE case and must show `PENDING_APPROVAL` with a verified `proof_id`/`signature`, not a `PROOF_VERIFICATION_FAILED`.

**Step 3: Deployed smoke (dev → staging), disposable delegation.** Using a short-lived, disposable `nuggets.payments.send` delegation and a freshly downloaded key (never committed), run the smoke scripts against dev, then staging, and confirm:

| `NUGGETS_AMOUNT_MINOR` | Expected ACP result | Handler |
|---|---|---|
| `100` (£1.00) | ALLOW | no-op runs once, proof emitted |
| `500` (£5.00) | ESCALATE | does not run; PENDING_APPROVAL + approval_id |
| `100100` (£1,001.00) | DENY (`CAP_EXCEEDED_AMOUNT`) | does not run |
| after revocation | DENY (`DELEGATION_REVOKED`) | does not run |

Set `NUGGETS_CURRENCY=GBP` for all four. Confirm the signed ALLOW proof verifies and the action feed records each expected result. Production demo repeats this only after staging passes.

**Step 4: Release gating.** Do not publish from an unreviewed branch. Open a PR to `main` with the JS + Python parity tests; obtain the normal package-release approval; publish `@nuggetslife/langchain-nuggets` (npm) and `langchain-nuggets` (PyPI) at 1.1.0 only after CI + dev/staging smoke pass.

---

## Parity checklist (keep JS ⇄ Python identical)

- [ ] `amount_minor` / `currency` optional fields on the action
- [ ] `actionContextResolver` / `action_context_resolver` config option
- [ ] same validation rules (non-neg safe int; `^[A-Z]{3}$`; non-empty target)
- [ ] amount/currency validated as a **pair** (both or neither); one-without-the-other fails closed
- [ ] resolver failure ⇒ ERROR before handler, in all modes incl. testMode
- [ ] `AuthorityDecision` includes `ESCALATE`
- [ ] ESCALATE signature **required and verified** (verify-success + verify-fail unit tests)
- [ ] ESCALATE ⇒ `PENDING_APPROVAL` ToolMessage with `approval_id` + verified receipt, no handler, no ProofArtifact
- [ ] smoke scripts: amount/currency env + ESCALATE branch + no-payment banner
- [ ] docs updated in both READMEs + provisioning runbook
- [ ] version 1.1.0 in both packages
