# Contributing to langchain-nuggets

Thanks for your interest. This repo holds the Nuggets **Authority Middleware** for LangChain / LangGraph (plus the LangGraph Platform OIDC auth helpers). It is maintained by the Nuggets team; the package is published to PyPI as [`langchain-nuggets`](https://pypi.org/project/langchain-nuggets/).

External issues and PRs are welcome — please read the conventions below first.

## Getting started

```bash
git clone https://github.com/NuggetsLtd/langchain-nuggets
cd langchain-nuggets/packages/python
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,langgraph,agent]"
pytest
ruff check .
```

(The `agent` extra pulls `langchain>=1.0` for the `create_agent` adapter and requires Python ≥3.10; on 3.9 install `.[dev,langgraph]` and those tests skip.)

## End-to-end smoke test against a live backend

Pre-create a delegation with your test tool in `allowed_capabilities`, then run from the repo root:

```bash
export NUGGETS_AUTHORITY_URL="https://accounts-dev.internal-nuggets.life"
export NUGGETS_OIDC_ISSUER_URL="https://auth-dev.internal-nuggets.life"
export NUGGETS_AGENT_ID="did:web:auth-dev.internal-nuggets.life:..."
export NUGGETS_CONTROLLER_ID="did:web:auth-dev.internal-nuggets.life:..."
export NUGGETS_DELEGATION_ID="42"
export NUGGETS_AGENT_PRIVATE_KEY="/path/to/agent-jwks.json"
export NUGGETS_TOOL="your_tool_name"   # any capability listed in the delegation's allowed_capabilities

python scripts/smoke_test_authority.py
```

Exits 0 when the backend returns `ALLOW` and a proof artifact is emitted. See [`scripts/demo_deployed_scenarios.py`](./scripts/demo_deployed_scenarios.py) for the full ALLOW + DENY walkthrough.

## Branch + commit conventions

- Branch from `main`. Name branches descriptively (e.g. `fix/proof-timestamp-tz`).
- One logical change per PR. Keep PRs reviewable.
- Commit messages: imperative, lowercase, no trailing period (`fix proof timestamp tz`).

## Pull requests

- Target `main`.
- Include tests for any behaviour change (`pytest`).
- Run `ruff check .` before opening a PR.
- Describe the change, the motivation, and any breaking implications.
- **Security controls must not be weakened.** Changes that relax authority enforcement, proof verification, or fail-closed behaviour will not be accepted without an explicit, reviewed rationale.

## Code style

- Type hints required on the public surface. `from __future__ import annotations` at the top of new modules.
- No new runtime dependencies without discussion in the PR.

## Reporting bugs

Open a GitHub issue with:

- What you ran (command or code snippet)
- What you expected
- What actually happened (logs, stack trace)
- Package version and Python version

For security issues, see [SECURITY.md](./SECURITY.md) — please do not file public issues.

## License

By submitting a contribution you agree it is licensed under the MIT License of this repository.
