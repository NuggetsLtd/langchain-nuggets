# Changelog

All notable changes to `@nuggetslife/langchain-nuggets` will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
