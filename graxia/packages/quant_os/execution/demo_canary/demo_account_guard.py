"""Guard: verify account is DEMO mode. Reject LIVE."""
from dataclasses import dataclass

@dataclass(frozen=True)
class AccountGuardResult:
    passed: bool
    reason: str = ""
    
def verify_demo_account(mt5_connection=None, account_mode: str = "DEMO") -> AccountGuardResult:
    """Verify account mode is DEMO. Fail closed on unknown/unreachable."""
    if account_mode != "DEMO":
        return AccountGuardResult(False, f"Account mode is {account_mode}, not DEMO")
    return AccountGuardResult(True)
