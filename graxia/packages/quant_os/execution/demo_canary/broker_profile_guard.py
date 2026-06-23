"""Guard: verify broker profile fingerprint matches approved."""
from dataclasses import dataclass

@dataclass(frozen=True)
class ProfileGuardResult:
    passed: bool
    reason: str = ""
    profile_hash: str = ""
    
APPROVED_PROFILE_HASH = "b2a952e42de3af5e5c5e8eecfaec788c794f9cb3bb75d1b407badf26694ef3cb"  # Pepperstone Demo 61547941

def verify_broker_profile(profile_hash: str) -> ProfileGuardResult:
    """Verify broker profile matches the approved Pepperstone Demo account."""
    if not profile_hash:
        return ProfileGuardResult(False, reason="No profile hash provided")
    if profile_hash != APPROVED_PROFILE_HASH:
        return ProfileGuardResult(False, reason=f"Profile hash mismatch")
    return ProfileGuardResult(True, profile_hash=profile_hash)
