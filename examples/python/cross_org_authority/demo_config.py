"""Demo configuration: orgs, agents, keys, and DIDs."""
import hashlib
import hmac
import json
import time
import uuid

# --- Org A: issues delegation ---
ORG_A = {
    "name": "Acme Corp",
    "id": "org-acme",
}

# --- Org B: remote agent ---
ORG_B = {
    "name": "Partner Inc",
    "id": "org-partner",
}

# --- Agent A: Org A's local agent (exposes capabilities) ---
AGENT_A = {
    "did": "did:nuggets:oidc:agent-acme-local",
    "name": "AcmeKYCAgent",
    "capabilities": ["check_kyc_status", "verify_credential", "initiate_kyc"],
}

# --- Agent B: Org B's remote agent (delegated access) ---
AGENT_B = {
    "did": "did:nuggets:oidc:agent-partner-remote",
    "name": "PartnerVerifyAgent",
}

# Simulated signing secret (in production, this would be an asymmetric keypair)
PORTAL_SIGNING_SECRET = "demo-portal-secret-key-2026"


def sign_proof(data: dict) -> str:
    """Sign proof data with HMAC-SHA256 (demo stand-in for JWS)."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hmac.new(
        PORTAL_SIGNING_SECRET.encode(), canonical.encode(), hashlib.sha256
    ).hexdigest()


def verify_signature(data: dict, signature: str) -> bool:
    """Verify an HMAC-SHA256 signature."""
    expected = sign_proof(data)
    return hmac.compare_digest(expected, signature)


def generate_proof_id() -> str:
    return f"proof-{uuid.uuid4().hex[:12]}"
