"""Standalone proof verification utility.

Verifies a proof artifact independently — does NOT depend on runtime
state, LangChain logs, or cloud IAM.  Only requires the portal's
signing secret (in production, this would be a public key).
"""
import json
import sys

from demo_config import verify_signature


def verify_proof(proof_json: dict) -> dict:
    """Verify a proof artifact and return verification results.

    Returns a dict with:
      - valid: bool
      - who_acted: agent_id
      - under_whose_authority: controller_id + delegation_id
      - what_constraints: constraints_evaluated
      - with_what_intent: intent_hash
      - at_what_time: timestamp
      - decision: ALLOW/DENY
    """
    # Extract proof data that was signed
    proof_data = {
        "proof_id": proof_json["proof_id"],
        "agent_id": proof_json["agent_id"],
        "controller_id": proof_json["controller_id"],
        "delegation_id": proof_json["delegation_id"],
        "tool": proof_json["tool"],
        "parameters_hash": proof_json["parameters_hash"],
        "intent_hash": proof_json.get("intent_hash"),
        "constraints_evaluated": proof_json.get("constraints_evaluated", []),
        "decision": "ALLOW",
    }

    signature = proof_json["authority_signature"]
    valid = verify_signature(proof_data, signature)

    return {
        "valid": valid,
        "who_acted": proof_json["agent_id"],
        "under_whose_authority": f"{proof_json['controller_id']} via delegation {proof_json['delegation_id']}",
        "what_constraints": proof_json.get("constraints_evaluated", []),
        "with_what_intent": proof_json.get("intent_hash", "none"),
        "at_what_time": proof_json["timestamp"],
        "decision": "ALLOW" if valid else "UNVERIFIED",
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python verify_proof.py <proof.json>")
        print("       Verifies a proof artifact independently.")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        proof = json.load(f)

    result = verify_proof(proof)

    print("\n=== Proof Verification ===")
    print(f"  Signature valid:      {result['valid']}")
    print(f"  Who acted:            {result['who_acted']}")
    print(f"  Under whose authority:{result['under_whose_authority']}")
    print(f"  Constraints checked:  {result['what_constraints']}")
    print(f"  Intent hash:          {result['with_what_intent']}")
    print(f"  Timestamp:            {result['at_what_time']}")
    print(f"  Decision:             {result['decision']}")
    print()


if __name__ == "__main__":
    main()
