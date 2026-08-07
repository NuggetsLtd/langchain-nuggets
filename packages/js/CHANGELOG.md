# Changelog

All notable changes to `@nuggetslife/langchain-nuggets` will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.2]

Released in lockstep with the Python package's 1.1.2 security-hardening patch.

### Fixed

- **A post-execution proof/callback failure no longer masks a completed tool run.** Once the wrapped tool has executed, `buildProofArtifact`, `onProof`, and result-hashing failures are isolated and the tool's result is still returned — so a completed, possibly non-idempotent side effect can't be misreported as an error and retried.

## [1.1.1]

Security hardening. Fixes NuggetsLtd/langchain-nuggets#54.

### Security

- **Fail-closed `ERROR` messages no longer echo raw exception text.** The action-context-resolver and authority-evaluation catch paths previously interpolated `${exc}` into the `ToolMessage` content (surfaced to the LLM/user), which could leak tool-arg data from a resolver or authority error. The message now carries only a generic phrase plus the error's class name.

## [1.1.0]

Payment / approval half of the ACP action contract. Additive — expands the set of possible decisions, so a minor bump. At parity with the Python `langchain-nuggets` 1.1.0 release.

### Added

- **`actionContextResolver`** on `MiddlewareConfig` — maps a tool call to `{ target?, amount_minor?, currency? }`, merged into the signed action. Money fields are never inferred from tool args. Validated as a pair (both or neither), `amount_minor` a non-negative safe integer, `currency` matching `^[A-Z]{3}$`, `target` a non-empty (non-whitespace) string. Invalid output fails **closed** with an `ERROR` `ToolMessage` before the handler runs, including in `testMode`.
- **`ESCALATE` decision** surfaced as a first-class, non-error `PENDING_APPROVAL` `ToolMessage`. The signed decision is verified exactly as `ALLOW` is; the tool never runs and no proof artifact is emitted. The result carries the verified `proof_id`/`signature` plus the server-issued `approval_id`.
- `approval_id` on `AuthorityEvaluationResponse` (`string | number | null`), preserved verbatim — a server-issued handle, **not** part of the signed receipt; applications own polling/redeem out-of-band.
- Smoke script reads optional `NUGGETS_AMOUNT_MINOR` / `NUGGETS_CURRENCY`; the handler is a no-op and never executes a payment.

## [1.0.0]

First stable release. No functional changes from 0.1.0 — promoted to 1.0.0 after end-to-end validation against a live backend (OIDC token minting, `agent_proof` signing, authority `ALLOW`, and discover-and-pin proof verification all confirmed against the deployed dev environment), plus full parity-test coverage. The public API is now covered by semantic-versioning stability guarantees, matching the Python package.

## [0.1.0]

Initial release — a TypeScript port of the Python `langchain-nuggets` Authority middleware.

### Added

- `NuggetsAuthorityMiddleware` — async `wrapToolCall` / `awrapToolCall` for LangGraph.js `ToolNode`, enforcing Nuggets authority before each tool call: bearer minting (OIDC `private_key_jwt` client-credentials with RFC 8707 `resource`), RS256 `agent_proof` signing, authority evaluation, fail-closed DENY/ERROR, and emitted proof artifacts.
- Consumer-side proof verification, on by default: discover `{issuer, jwks_uri}` from `{apiUrl}/.well-known/authority-configuration`, pin `proof.iss === issuer`, verify the RS256 signature against the discovered JWKS, and bind the proof to the request (SSRF-guarded, fail-closed).
- `createNuggetsAuthorityMiddleware` (exported from `@nuggetslife/langchain-nuggets/agent`) — a LangChain.js `createAgent` `AgentMiddleware` adapter composing the core middleware. `langchain` is an optional peer dependency; the root entry stays `@langchain/core`-only.
- Stable JSON hashing that matches the Python SDK byte-for-byte (sorted keys, compact separators, `ensure_ascii`-equivalent escaping of non-ASCII), so parameter/intent/result hashes are identical across the Python and TypeScript SDKs.
- `test_mode` for local development; `verify_proofs` opt-out; `ca_cert` / `verify_ssl` for self-hosted backends.

### Notes

- Published with npm provenance.
