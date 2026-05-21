"""Integration smoke test against a deployed Nuggets authority backend.

Skipped by default. Set the env vars below to run it against a real
deployed environment (dev / staging / prod). This is the real check
that the SDK works against the partner repo's Next.js route — the
neighbouring `local_authority.py` mock only confirms request/response
shape, not that anything is actually wired up correctly.

Required env (full list + setup notes in
`scripts/smoke_test_authority.py`):

    NUGGETS_AUTHORITY_URL
    NUGGETS_OIDC_ISSUER_URL
    NUGGETS_AGENT_ID
    NUGGETS_CONTROLLER_ID
    NUGGETS_DELEGATION_ID
    NUGGETS_AGENT_PRIVATE_KEY

Run:

    pytest examples/python/cross_org_authority/test_authority_integration.py -s
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REQUIRED_ENV = [
    "NUGGETS_AUTHORITY_URL",
    "NUGGETS_OIDC_ISSUER_URL",
    "NUGGETS_AGENT_ID",
    "NUGGETS_CONTROLLER_ID",
    "NUGGETS_DELEGATION_ID",
    "NUGGETS_AGENT_PRIVATE_KEY",
]


def test_authority_evaluate_against_deployed_backend() -> None:
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        pytest.skip(
            "Deployed-backend integration test skipped — set "
            f"{', '.join(missing)} to run. See "
            "scripts/smoke_test_authority.py for setup details."
        )

    repo_root = Path(__file__).resolve().parents[3]
    script = repo_root / "scripts" / "smoke_test_authority.py"
    if not script.is_file():
        pytest.fail(f"smoke test script missing at {script}")

    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except subprocess.TimeoutExpired as err:
        pytest.fail(
            f"smoke test did not complete within {err.timeout}s — "
            "is the backend reachable?"
        )

    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        pytest.fail(
            f"smoke test exited with code {result.returncode}; "
            "see captured output above"
        )
