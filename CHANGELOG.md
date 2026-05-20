# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `agent_private_key` field on `MiddlewareConfig` (PEM string, file path, or JWK dict). The middleware signs an RS256 JWS for every authority evaluation request with claims `{agent_id, nonce, iat, exp}` and sends it as `agent_proof` in the request body. The backend verifies the signature against the agent's registered OIDC public key, proving the request originated from the agent that owns the DID. Required when `test_mode=False`.
- `PyJWT[crypto]` is now a core dependency (was previously only required via the `[langgraph]` extra).
- `Idempotency-Key` header (uuid4) on every authority evaluation request, enabling backend dedupe of cap increments and audit writes on retries.
- `nonce` field on `ActionContext` (uuid4, auto-generated per call) for backend replay protection. Backend pairs this with the existing `timestamp` field for staleness checks and a nonce-uniqueness store. The same nonce value is embedded in the `agent_proof` JWS so the backend can cross-check binding.
- `headers` keyword argument on `NuggetsApiClient.post` and `NuggetsApiClient.apost`.

### Changed

- **Breaking**: `MiddlewareConfig` now requires `agent_private_key` unless `test_mode=True`. Existing 0.1.0 callers will raise a `ValidationError` until they supply a key. Bumps to `0.2.0`.
- `test_mode` flag on `MiddlewareConfig` for local development without a live Nuggets backend. The middleware skips the authority HTTP call and returns a synthetic `ALLOW`. Proof artifacts emitted in test mode are marked `test_mode=True` with `authority_signature="test-mode-unverifiable"` and are not verifiable against production keys.
- Repository governance: `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`.
- GitHub Actions workflows for PyPI and npm release.

### Changed

- `MiddlewareConfig.authority_endpoint` default is now `/api/authority/evaluate` to match the deployed Nuggets backend route.

## [0.1.0] - TBD

Initial public release.

- `langchain-nuggets` Python package (PyPI)
- `@nuggetslife/langchain` TypeScript toolkit (npm)
- `@nuggetslife/mcp-server` MCP server (npm)
- LangGraph auth provider via `langchain-nuggets[langgraph]`
- `NuggetsAuthorityMiddleware` for pre-execution trust enforcement with cryptographic proof artifacts
