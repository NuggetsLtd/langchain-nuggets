# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.2.0]

Security-hardening release from an adversarial review. Minor bump because one change is a **breaking default** (see Migration).

### ⚠️ Migration

- **LangGraph OIDC auth now requires an `audience`.** If you construct `NuggetsAuth(issuer_url=...)` (or `NuggetsTokenVerifier`) **without** an `audience`, JWT verification now fails closed (HTTP 401) instead of silently skipping the `aud` check (RFC 9068). Note: the Nuggets issuer does not yet define a LangGraph resource-server audience, so a concrete `audience=` value is not available today — that issuer-side contract is tracked in #63. Until it lands, `allow_any_audience=True` is a **temporary migration escape hatch, not a production recommendation**. Do **not** use the authority API resource (`.../api/authority`) as the LangGraph `audience` — it is a different resource.
- **`ownership_filter()` behavior changed.** It now stamps `value["metadata"]["owner"]` (not a top-level `value["owner"]`) and returns an `{"owner": identity}` filter for every operation. If you relied on the previous (broken) shape, re-verify ownership/read-access after upgrading, and register the handler across create/read/search/update/delete.

### Security

- **LangGraph OIDC token verifier hardened** (`NuggetsTokenVerifier` / `NuggetsAuth`):
  - JWT verification now **fails closed when no `audience` is configured** (RFC 9068), instead of silently disabling `aud` checks — so a correctly-signed issuer token minted for a different client/resource is no longer accepted. A deliberate `allow_any_audience=True` opt-out is available. README updated to set `audience`.
  - The verification algorithm is pinned to a fixed `["RS256"]` allowlist rather than taken from the (attacker-controlled) token header, and JWKS key selection filters by `kty`/`use`/`alg`.
- **`ownership_filter()` now implements LangGraph's ownership contract.** It previously wrote a top-level `value["owner"]` and returned the entire payload as the filter, and mis-routed dict-shaped read/search values — which could create unowned resources, produce malformed filters, and (without per-op handlers) expose data across tenants. It now stamps `value["metadata"]["owner"]` on writes, returns the exact-match `{"owner": identity}` filter for every operation, and **fails closed (403)** when there is no authenticated identity or the payload's `metadata` is not a mapping. README shows registering it across create/read/search/update/delete.
- **JS supply-chain hardening.** CI now runs a production-scoped `npm audit` (`--omit=dev --audit-level=low`) so shipped dependencies are gated deterministically; Dependabot now covers the `packages/js` npm ecosystem; and the flagged dev-only `postcss` advisory was cleared via a lockfile bump. (Production npm dependencies were, and remain, advisory-free.)

### Fixed

- **A post-execution proof/callback failure no longer masks a completed tool run** (both SDKs, sync + async). Once the wrapped tool has executed, proof-artifact construction, `on_proof`/`onProof` callback, and result-hashing failures are isolated (logged in Python; swallowed in JS) and the tool's result is still returned — so a completed, possibly non-idempotent side effect can't be misreported as an error and retried.

## [1.1.1]

Security hardening. Fixes #54.

### Security

- **Fail-closed `ERROR` messages no longer echo raw exception text.** The action-context-resolver and authority-evaluation failure paths (both SDKs, sync + async) previously interpolated `str(exc)` / `${exc}` into the `ToolMessage` content, which is surfaced to the LLM/user — a user-supplied resolver or an authority error could leak tool-arg data (amounts, targets, identifiers). The user-facing message now carries only a generic phrase plus the exception's class name; full detail (with traceback in Python) goes to the server-side log.

### Fixed

- Python README "Test mode" section clarified: `action_context_resolver` validation runs before the `test_mode` short-circuit, so invalid money fields fail closed even in test mode.

## [1.1.0]

Payment / approval half of the ACP action contract. Additive — expands the set of possible decisions, so a minor bump. JS and Python stay behaviourally symmetric.

### Added

- **Opt-in action-context resolver** (`action_context_resolver` / `actionContextResolver`) mapping a tool call to `{target?, amount_minor?, currency?}`, merged into the signed action. Money fields are never inferred from tool args — the resolver is their only source. Validated as a pair (both or neither), `amount_minor` a non-negative integer (bool rejected), `currency` matching `^[A-Z]{3}$`, `target` a non-empty (non-whitespace) string. Invalid output fails **closed** with an `ERROR` `ToolMessage` before the handler runs, in every mode including `test_mode`.
- **`ESCALATE` decision** surfaced as a first-class, non-error `PENDING_APPROVAL` `ToolMessage`. The signed decision is verified exactly as `ALLOW` is; on success the wrapped tool never runs and no proof artifact is emitted. The result carries the verified `proof_id`/`signature` plus the server-issued `approval_id`.
- `approval_id` on `AuthorityEvaluationResponse` (`str | int | null`), preserved verbatim. It is a server-issued handle, **not** part of the signed receipt; applications own polling/redeem out-of-band.
- Smoke scripts read optional `NUGGETS_AMOUNT_MINOR` / `NUGGETS_CURRENCY` to exercise ALLOW / ESCALATE / DENY routing; the handler is a no-op and never executes a payment.

## [1.0.0]

First stable release. The authority middleware is verified in production — enforce flag on, full authenticated adversarial matrix passing, proof verification on by default — so the public API is now covered by semantic-versioning stability guarantees.

### Added

- PyPI Trove `classifiers` (production-stable status, supported Python 3.9–3.12, security topic).

### Notes

- No functional changes from 0.7.0 — this is a stability/maturity promotion.

## [0.7.0]

### Added

- **`NuggetsAuthorityAgentMiddleware` — a first-class LangChain `AgentMiddleware` adapter** for `create_agent(middleware=[...])`. Subclasses `langchain.agents.middleware.AgentMiddleware` and composes the existing `NuggetsAuthorityMiddleware`, so the full verified enforcement path (bearer auth, agent_proof signing, discover-and-pin proof verification, fail-closed DENY/ERROR, proof emission) is reused unchanged. This makes Nuggets Authority usable as a listed LangChain integration.
- New `[agent]` optional extra (`pip install langchain-nuggets[agent]`) pulling `langchain>=1.0`. Import via `from langchain_nuggets.middleware import NuggetsAuthorityAgentMiddleware`; a clear install hint is raised if the extra is missing.

### Notes

- The core `NuggetsAuthorityMiddleware` (`ToolNode(wrap_tool_call=...)`) path is unchanged and still depends only on `langchain-core`. The adapter is purely additive.
- `langchain>=1.0` requires Python >=3.10; on 3.9 the core middleware remains fully usable, only the `create_agent` adapter is unavailable.

## [0.6.0]

### Changed

- **Proof verification now follows a discover-and-pin model (RT-P1).** On each ALLOW the SDK discovers the authority's `issuer` + `jwks_uri` from `{api_url}/.well-known/authority-configuration` (cached, short TTL; honours `verify_ssl`/`ca_cert`), **pins `proof.iss == issuer`** (the VC-idiomatic issuer check — a pinned comparison, not resolve-and-trust), then verifies the RS256 signature against the keys at the discovered `jwks_uri` (by JWS header `kid`, falling back to trying all published keys for rotation / kid-less keys). Both the expected issuer and the keys come from the trusted `api_url` host, so nothing is baked per environment. This closes RT-P1 with no residual: an attacker's proof is rejected at the issuer pin (foreign `iss`) and/or because its key isn't at the discovered `jwks_uri` — even if its `iss` resolves to the attacker's own valid DID.
- The exported `verify_authority_proof()` / `averify_authority_proof()` now take discovered `issuer` + `jwks_uri` (pin + key source) in place of the issuer-URL / DID arguments. New `discover_authority()` / `adiscover_authority()` helpers fetch the authority discovery document. Third-party out-of-band verification discovers the same endpoint (or supplies the known `issuer` + `jwks_uri`).

### Removed

- did:web `iss` resolution, the `authority_issuer_did` config field + issuer-DID pin, the issuer host-pin, and the `did:nuggets:oidc:`→`did:web` fallback — all obsolete under discover-and-pin. Net: less code, no per-env secret, no new required config.

### Notes

- Default-on, fail-closed, claim binding (decision/proof_id/agent_id/controller_id/constraints_evaluated), async path, and TLS threading are unchanged. `test_mode` / `verify_proofs=False` still skip verification. Discovery or JWKS fetch failure → fail closed (DENY).
- Backend contract unchanged (no proof re-issue): verifies today's `did:nuggets:oidc:` and post-#174 `did:web:` proofs identically — the issuer comes from discovery either way.
- Rotation-safe: the JWKS endpoint publishes current + retired authority keys, so proofs signed by a retired-but-published key still verify.
- Requires the authority discovery endpoint (partner #204) deployed on the target environment.

## [0.5.0]

### Added

- **Consumer-side authority proof verification (#161), on by default.** Every ALLOW decision now has its signed proof verified before the tool runs: the proof's `iss` DID is resolved (generic `did:web` → `…/.well-known/did.json`), the RS256 signature is checked against the published key, and the proof is bound to the request (decision, proof_id, agent_id, controller_id, constraints_evaluated). On any failure the call is failed closed as a DENY with `reason_code = PROOF_VERIFICATION_FAILED`. This makes the "independently verifiable decision" guarantee real rather than taken on faith.
- `verify_authority_proof(signature, *, expected, oidc_issuer_url=None, http_client=None)` exported from `langchain_nuggets.middleware` — a standalone verifier so a third party can validate an emitted proof artifact out-of-band. Raises `ProofVerificationError` (also exported) on failure.
- `verify_proofs` field on `MiddlewareConfig` (default `True`). Set to `False` only as a deliberate opt-out (e.g. an offline harness that verifies proofs separately).
- Pre-#174 fallback: when a proof's `iss` is still `did:nuggets:oidc:<id>`, the issuer host is derived from `oidc_issuer_url`. Once the backend issues `did:web` proof issuers, resolution is fully generic.

### Notes

- `test_mode` proofs are intentionally unverifiable and skip verification.
- `action_context_hash` binding is supported by the verifier when supplied, but the middleware does not yet recompute it from the sent request — deferred until it can be byte-matched against the backend's canonical hashing on dev (a mismatch would fail-close legitimate calls). The identity binds above already prevent proof-swapping.

## [0.4.1]

### Fixed

- The OIDC token request now sends an RFC 8707 `resource` indicator (defaulting to `${api_url}/api/authority`). The Nuggets provider only mints a **JWT** access token — required by the authority endpoint's offline bearer verification — when the token request names the authority audience; without it the provider returns an opaque token that fails verification. Previously this happened to work only because the provider defaulted the audience server-side; that default has since been tightened, making the explicit `resource` mandatory.

### Added

- `authority_audience` field on `MiddlewareConfig` (optional). Overrides the derived `${api_url}/api/authority` resource indicator for deployments whose audience differs from that convention.

## [0.4.0]

### Removed

- **Breaking**: `NuggetsToolkit`, `NuggetsApiClient`, `NuggetsApiClientError`, `NuggetsBaseTool`, and all 11 tools under `langchain_nuggets.tools` (KYC, KYA, auth/credentials). The endpoints these tools called (`/partner/auth`, `/kyc/sessions/*`, `/kya/agents/*`, `/auth/status/*`, `/credentials/presentations/*`) don't exist on any deployed Nuggets backend — the toolkit was speculative surface against a REST-shaped product that never shipped. KYC and related flows live on DIDComm in the actual Nuggets product, not on a sync REST API.
- **Breaking**: `NuggetsAuth.api_url` / `partner_id` / `partner_secret` constructor arguments (and the matching env vars `NUGGETS_API_URL` / `NUGGETS_PARTNER_ID` / `NUGGETS_PARTNER_SECRET`) and the `require_kyc` flag. The OIDC token verification path stays intact; only the broken KYC-status enrichment via `NuggetsApiClient` was removed.
- **Breaking**: `require_kyc` authorization helper from `langchain_nuggets.langgraph` — its check relied on the removed `kyc_verified` enrichment.
- **Breaking**: `partner_id`, `partner_secret`, `api_url`, and `require_kyc` fields on `NuggetsAuthConfig`.
- **Breaking**: `packages/js` (JavaScript / TypeScript toolkit) and `packages/mcp-server` (MCP server) removed for the same reason — both targeted the same fictional endpoints.

### Changed

- Package description / keywords reframed around the authority middleware. The package is now a single-feature SDK for runtime authority enforcement, not a multi-surface identity toolkit.
- READMEs (root and `packages/python/`) rewritten to match.

## [0.3.0]

### Added

- `oidc_issuer_url` field on `MiddlewareConfig` — URL of the Nuggets OIDC provider that mints access tokens for `/api/authority/evaluate`. Required when `test_mode=False`.
- `OidcClientCredentialsClient` — internal helper that exchanges a `private_key_jwt` client assertion for a bearer access token, caches it, and uses it to authenticate authority requests. Implements OAuth 2.0 client_credentials grant per RFC 6749 §4.4 / RFC 7521.
- `authority_scope` field on `MiddlewareConfig` (default `"authority.evaluate"`) — scope requested at the OIDC token endpoint.

### Changed

- **Breaking**: removed `partner_id` and `partner_secret` from `MiddlewareConfig`. The middleware no longer calls `/partner/auth` — that endpoint never existed on the deployed Nuggets backend.
- **Breaking**: HTTP auth on `/api/authority/evaluate` is now an OIDC access token in `Authorization: Bearer <token>`. The token is verified by the backend against the OIDC provider's JWKS. The agent's existing private key is reused to sign the `private_key_jwt` client assertion (no new credentials).

## [0.2.0]

### Added

- `agent_private_key` field on `MiddlewareConfig` (PEM string, file path, or JWK dict). The middleware signs an RS256 JWS for every authority evaluation request with claims `{agent_id, nonce, iat, exp}` and sends it as `agent_proof` in the request body. The backend verifies the signature against the agent's registered OIDC public key, proving the request originated from the agent that owns the DID. Required when `test_mode=False`.
- `Idempotency-Key` header (uuid4) on every authority evaluation request, enabling backend dedupe of cap increments and audit writes on retries.
- `nonce` field on `ActionContext` (uuid4, auto-generated per call) for backend replay protection. Backend pairs this with the existing `timestamp` field for staleness checks and a nonce-uniqueness store. The same nonce value is embedded in the `agent_proof` JWS so the backend can cross-check binding.
- `test_mode` flag on `MiddlewareConfig` for local development without a live Nuggets backend. The middleware skips the authority HTTP call and returns a synthetic `ALLOW`. Proof artifacts emitted in test mode are marked `test_mode=True` with `authority_signature="test-mode-unverifiable"` and are not verifiable against production keys.
- `headers` keyword argument on `NuggetsApiClient.post` and `NuggetsApiClient.apost`. SDK-required headers (`Authorization`, `Content-Type`) cannot be overridden by callers.
- Repository governance: `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`.
- GitHub Actions workflows for PyPI and npm release.

### Changed

- **Breaking**: `MiddlewareConfig` now requires `agent_private_key` unless `test_mode=True`. The value is validated at config-construction time (must be a PEM string, an existing file path, or a private RSA JWK dict). Bumps to `0.2.0`.
- `PyJWT[crypto]` is now a core dependency (was previously only required via the `[langgraph]` extra).
- `MiddlewareConfig.authority_endpoint` default is now `/api/authority/evaluate` to match the deployed Nuggets backend route.

## [0.1.0] - TBD

Initial public release.

- `langchain-nuggets` Python package (PyPI)
- `@nuggetslife/langchain` TypeScript toolkit (npm)
- `@nuggetslife/mcp-server` MCP server (npm)
- LangGraph auth provider via `langchain-nuggets[langgraph]`
- `NuggetsAuthorityMiddleware` for pre-execution trust enforcement with cryptographic proof artifacts
