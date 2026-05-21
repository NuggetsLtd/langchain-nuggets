#!/usr/bin/env python3
"""Cross-org authority scenarios against a deployed Nuggets backend.

Designed to be run for a screen-recording: each scenario prints a
banner, the request the SDK is making, and the backend's response.
Pauses for keyboard input between scenarios (set `NUGGETS_DEMO_AUTO=1`
to run continuously, e.g. for sanity checks).

Unlike the cross-org demo at `examples/python/cross_org_authority/`,
which runs against an in-process FastAPI mock, this script hits the
real deployed accounts portal — real OIDC, real `agent_proof` JWS,
real signed proofs.

================================================================
Setup (one-time, in the dev accounts portal)
================================================================

1. Create the agent (AI → Agents → Create). Download the JWKS file.

2. Create FOUR delegations granting access to the agent (AI →
   Delegations → Allow Agent):

   (a) NORMAL — capabilities=[check_kyc_status], targets=[kyc-service],
       max_calls=10, no expiry.
       → set as NUGGETS_DELEGATION_ID

   (b) CAP — capabilities=[check_kyc_status], targets=[kyc-service],
       max_calls=1, no expiry. The demo will consume this one's only
       allowance during scenario 4, so the next call fails with
       CAP_EXCEEDED_INVOCATIONS.
       → set as NUGGETS_DELEGATION_ID_CAP

   (c) EXPIRED — same shape as (a) but with Access Expires set to a
       past datetime. (If the portal UI doesn't allow past dates,
       pick "1 minute from now" and wait a minute before recording.)
       → set as NUGGETS_DELEGATION_ID_EXPIRED

   (d) TO-BE-REVOKED — same shape as (a). Leave active for now; the
       demo can either revoke it live during scenario 6 (via the
       portal UI) or you can pre-revoke before running.
       → set as NUGGETS_DELEGATION_ID_REVOKED

3. Export env vars (full list below) and run:

       python scripts/demo_deployed_scenarios.py

================================================================
Env vars
================================================================

Required:
    NUGGETS_AUTHORITY_URL          e.g. https://accounts-dev.internal-nuggets.life
    NUGGETS_OIDC_ISSUER_URL        e.g. https://auth-dev.internal-nuggets.life
    NUGGETS_AGENT_ID               full DID
    NUGGETS_CONTROLLER_ID          full DID
    NUGGETS_AGENT_PRIVATE_KEY      path to JWKS / PEM / JWK file (or inline)
    NUGGETS_DELEGATION_ID          delegation (a)
    NUGGETS_DELEGATION_ID_CAP      delegation (b)
    NUGGETS_DELEGATION_ID_EXPIRED  delegation (c)
    NUGGETS_DELEGATION_ID_REVOKED  delegation (d)

Optional:
    NUGGETS_TOOL                   default check_kyc_status
    NUGGETS_TARGET                 default kyc-service
    NUGGETS_OUT_OF_SCOPE_TOOL      default initiate_payment (for DENY scenario)
    NUGGETS_OUT_OF_SCOPE_TARGET    default unknown-service (for DENY scenario)
    NUGGETS_DEMO_AUTO              set to "1" to skip the press-enter pauses
"""
from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace
from typing import Any, Dict, Optional, Union

from langchain_core.messages import ToolMessage

from langchain_nuggets.middleware import (
    MiddlewareConfig,
    NuggetsAuthorityMiddleware,
    ProofArtifact,
)

REQUIRED_ENV = [
    "NUGGETS_AUTHORITY_URL",
    "NUGGETS_OIDC_ISSUER_URL",
    "NUGGETS_AGENT_ID",
    "NUGGETS_CONTROLLER_ID",
    "NUGGETS_AGENT_PRIVATE_KEY",
    "NUGGETS_DELEGATION_ID",
    "NUGGETS_DELEGATION_ID_CAP",
    "NUGGETS_DELEGATION_ID_EXPIRED",
    "NUGGETS_DELEGATION_ID_REVOKED",
]


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    sys.exit(1)


def load_key_from_env() -> Union[str, Dict[str, Any]]:
    raw = os.environ["NUGGETS_AGENT_PRIVATE_KEY"]
    if raw.lstrip().startswith("{"):
        return json.loads(raw)
    return raw


def banner(title: str) -> None:
    print()
    print("=" * 64)
    print(f"  {title}")
    print("=" * 64)


def pause(prompt: str = "Press Enter to continue") -> None:
    if os.environ.get("NUGGETS_DEMO_AUTO") == "1":
        return
    try:
        input(f"\n  >>> {prompt} <<<\n")
    except EOFError:
        # piped input ran out — fall through
        pass


def make_middleware(delegation_id: str) -> NuggetsAuthorityMiddleware:
    config = MiddlewareConfig(
        api_url=os.environ["NUGGETS_AUTHORITY_URL"],
        oidc_issuer_url=os.environ["NUGGETS_OIDC_ISSUER_URL"],
        agent_id=os.environ["NUGGETS_AGENT_ID"],
        controller_id=os.environ["NUGGETS_CONTROLLER_ID"],
        delegation_id=delegation_id,
        agent_private_key=load_key_from_env(),
    )
    return NuggetsAuthorityMiddleware(config)


def make_request(tool_name: str, target: Optional[str], call_id: str) -> SimpleNamespace:
    args: Dict[str, Any] = {"userId": "demo-user"}
    if target:
        args["target"] = target
    return SimpleNamespace(
        tool_call={"name": tool_name, "args": args, "id": call_id}
    )


def make_handler(call_id: str, content: str = '{"status": "ok"}') -> Any:
    def _handler(_: object) -> ToolMessage:
        return ToolMessage(content=content, tool_call_id=call_id)

    return _handler


def describe_result(result: ToolMessage, middleware: NuggetsAuthorityMiddleware) -> None:
    try:
        payload = json.loads(result.content)
    except json.JSONDecodeError:
        print(f"  Raw result: {result.content!r}")
        return

    status = payload.get("status") or payload.get("decision") or "OK"
    print(f"  Decision:   {status}")
    if "reason_code" in payload and payload["reason_code"]:
        print(f"  Reason:     {payload['reason_code']}")
    if "message" in payload and payload["message"]:
        print(f"  Message:    {payload['message']}")
    if middleware.proofs:
        proof = middleware.proofs[-1]
        print(f"  Proof ID:   {proof.proof_id}")
        print(f"  Signature:  {proof.authority_signature[:48]}...")
        print(f"  Latency:    {proof.latency_ms:.1f}ms")


def scenario_allow(tool: str, target: str) -> Optional[ProofArtifact]:
    banner("Scenario 1: ALLOW — in-scope call against an active delegation")
    mw = make_middleware(os.environ["NUGGETS_DELEGATION_ID"])
    request = make_request(tool, target, "demo-allow")
    print(f"  tool={tool!r} target={target!r}")
    result = mw.wrap_tool_call(request, make_handler("demo-allow"))
    describe_result(result, mw)
    return mw.proofs[-1] if mw.proofs else None


def scenario_deny_tool(out_of_scope_tool: str, target: str) -> None:
    banner("Scenario 2: DENY — tool not in the delegation's allowed_capabilities")
    mw = make_middleware(os.environ["NUGGETS_DELEGATION_ID"])
    request = make_request(out_of_scope_tool, target, "demo-deny-tool")
    print(f"  tool={out_of_scope_tool!r} (not granted)")
    result = mw.wrap_tool_call(request, make_handler("demo-deny-tool"))
    describe_result(result, mw)


def scenario_deny_target(tool: str, out_of_scope_target: str) -> None:
    banner("Scenario 3: DENY — target not in the delegation's allowed_targets")
    mw = make_middleware(os.environ["NUGGETS_DELEGATION_ID"])
    request = make_request(tool, out_of_scope_target, "demo-deny-target")
    print(f"  tool={tool!r} target={out_of_scope_target!r} (not granted)")
    result = mw.wrap_tool_call(request, make_handler("demo-deny-target"))
    describe_result(result, mw)


def scenario_deny_cap(tool: str, target: str) -> None:
    banner("Scenario 4: DENY — invocation cap exhausted")
    mw = make_middleware(os.environ["NUGGETS_DELEGATION_ID_CAP"])
    print("  First call consumes the only invocation in this delegation:")
    first = mw.wrap_tool_call(
        make_request(tool, target, "demo-cap-1"),
        make_handler("demo-cap-1"),
    )
    describe_result(first, mw)

    print()
    print("  Second call should hit the cap:")
    second = mw.wrap_tool_call(
        make_request(tool, target, "demo-cap-2"),
        make_handler("demo-cap-2"),
    )
    describe_result(second, mw)


def scenario_deny_expired(tool: str, target: str) -> None:
    banner("Scenario 5: DENY — delegation past its expires_at")
    mw = make_middleware(os.environ["NUGGETS_DELEGATION_ID_EXPIRED"])
    request = make_request(tool, target, "demo-expired")
    print(f"  Using delegation that has already expired")
    result = mw.wrap_tool_call(request, make_handler("demo-expired"))
    describe_result(result, mw)


def scenario_deny_revoked(tool: str, target: str) -> None:
    banner("Scenario 6: DENY — delegation revoked")
    mw = make_middleware(os.environ["NUGGETS_DELEGATION_ID_REVOKED"])
    request = make_request(tool, target, "demo-revoked")
    print(f"  Using a revoked delegation")
    print(f"  (revoke in the portal UI before running, or live during the demo)")
    result = mw.wrap_tool_call(request, make_handler("demo-revoked"))
    describe_result(result, mw)


def scenario_verify(proof: Optional[ProofArtifact]) -> None:
    banner("Scenario 7: Accountability — the proof artifact")
    if proof is None:
        print("  (no ALLOW proof captured; skipping)")
        return
    print("  The portal returned a signed proof for the ALLOW call. It contains:")
    print(f"    proof_id           = {proof.proof_id}")
    print(f"    agent_id           = {proof.agent_id}")
    print(f"    controller_id      = {proof.controller_id}")
    print(f"    delegation_id      = {proof.delegation_id}")
    print(f"    tool               = {proof.tool}")
    print(f"    parameters_hash    = {proof.parameters_hash[:32]}...")
    print(f"    constraints        = {proof.constraints_evaluated}")
    print(f"    authority_signature= {proof.authority_signature[:48]}...")
    print()
    print("  The signature is an RS256 JWS issued by the portal's signing key.")
    print("  Any party with the portal's public JWKS can verify it without")
    print("  contacting Nuggets at all.")


def main() -> None:
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        fail(f"missing env vars: {', '.join(missing)}")

    tool = os.environ.get("NUGGETS_TOOL", "check_kyc_status")
    target = os.environ.get("NUGGETS_TARGET", "kyc-service")
    out_of_scope_tool = os.environ.get("NUGGETS_OUT_OF_SCOPE_TOOL", "initiate_payment")
    out_of_scope_target = os.environ.get("NUGGETS_OUT_OF_SCOPE_TARGET", "unknown-service")

    banner("Nuggets Authority — Cross-Org Demo (deployed backend)")
    print(f"  authority   = {os.environ['NUGGETS_AUTHORITY_URL']}")
    print(f"  oidc issuer = {os.environ['NUGGETS_OIDC_ISSUER_URL']}")
    print(f"  agent       = {os.environ['NUGGETS_AGENT_ID']}")
    print(f"  controller  = {os.environ['NUGGETS_CONTROLLER_ID']}")

    pause("Start the demo")
    allow_proof = scenario_allow(tool, target)
    pause()
    scenario_deny_tool(out_of_scope_tool, target)
    pause()
    scenario_deny_target(tool, out_of_scope_target)
    pause()
    scenario_deny_cap(tool, target)
    pause()
    scenario_deny_expired(tool, target)
    pause()
    scenario_deny_revoked(tool, target)
    pause()
    scenario_verify(allow_proof)
    print()
    print("  Demo complete.")


if __name__ == "__main__":
    main()
