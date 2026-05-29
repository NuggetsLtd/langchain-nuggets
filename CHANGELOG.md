# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
