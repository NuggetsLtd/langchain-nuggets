# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
