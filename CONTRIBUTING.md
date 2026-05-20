# Contributing to langchain-nuggets

Thanks for your interest in contributing. This repo holds the open-source Nuggets integrations for LangChain — TypeScript toolkit, Python toolkit, MCP server, LangGraph auth, and the Authority Middleware.

## Getting started

```bash
git clone https://github.com/nuggets-life/langchain-nuggets
cd langchain-nuggets
pnpm install
pnpm build
pnpm test
```

Python:

```bash
cd packages/python
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,langgraph]"
pytest
```

## Branch + commit conventions

- Branch from `main`. Name branches descriptively (e.g. `fix/proof-timestamp-tz`).
- One logical change per PR. Keep PRs reviewable.
- Commit messages: imperative, lowercase, no trailing period (`fix proof timestamp tz`).

## Pull requests

- Target `main`.
- Include tests for any behaviour change. The Python suite uses `pytest`; the JS suite uses `vitest`.
- Run `pnpm lint` and `pnpm check-types` before opening a PR.
- Describe the change, the motivation, and any breaking implications.

## Code style

- TypeScript: strict mode, no `any` without justification.
- Python: type hints required on public surface. `from __future__ import annotations` at the top of new modules.
- No new dependencies without discussion in the PR.

## Reporting bugs

Open a GitHub issue with:

- What you ran (commands, code snippet)
- What you expected
- What actually happened (logs, stack trace)
- Version of the package and runtime (Node/Python)

For security issues, see [SECURITY.md](./SECURITY.md) — please do not file public issues.

## License

By submitting a contribution you agree it is licensed under the MIT License of this repository.
