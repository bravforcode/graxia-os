"""
Trial Ledger B — stopping-rule enforcement
==========================================
Utility functions for Path B trial ledger management.
Import and call from any script that adds trials.
"""
import json
from pathlib import Path

LEDGER_PATH = Path(__file__).resolve().parent.parent / "research" / "trial_ledger_b.json"


def load_ledger() -> dict:
    with open(LEDGER_PATH) as f:
        return json.load(f)


def save_ledger(data: dict) -> None:
    with open(LEDGER_PATH, "w") as f:
        json.dump(data, f, indent=2)


def is_stopped() -> bool:
    """Check if Path B is stopped (3-in-a-row-fail triggered)."""
    ledger = load_ledger()
    rule = ledger.get("stopping_rule", {})
    return rule.get("is_stopped", False)


def record_trial(verdict: str) -> dict:
    """Record a trial verdict and update stopping rule.

    Args:
        verdict: "GO", "MARGINAL", or "REJECTED"

    Returns:
        Updated stopping_rule dict.
    """
    ledger = load_ledger()
    rule = ledger.get("stopping_rule", {"consecutive_fail_count": 0, "is_stopped": False})

    if rule.get("is_stopped", False):
        raise RuntimeError(
            f"Path B is STOPPED (3 consecutive REJECTED). "
            f"consecutive_fail_count={rule['consecutive_fail_count']}. "
            f"Cannot add more trials."
        )

    if verdict == "REJECTED":
        rule["consecutive_fail_count"] = rule.get("consecutive_fail_count", 0) + 1
    else:
        rule["consecutive_fail_count"] = 0

    if rule["consecutive_fail_count"] >= 3:
        rule["is_stopped"] = True

    ledger["stopping_rule"] = rule
    save_ledger(ledger)
    return rule


def add_trial(trial_id: str, verdict: str, note: str = "") -> dict:
    """Add a trial to the lineage and update stopping rule.

    Returns:
        Updated stopping_rule dict.
    """
    ledger = load_ledger()

    # Check if stopped
    rule = ledger.get("stopping_rule", {})
    if rule.get("is_stopped", False):
        raise RuntimeError("Path B is STOPPED. Cannot add more trials.")

    # Check cap
    count = ledger.get("cumulative_trial_count", 0)
    cap = ledger.get("cumulative_trial_cap", 25)
    if count >= cap:
        raise RuntimeError(f"Path B cap reached ({count}/{cap}).")

    # Add to lineage
    next_num = ledger.get("next_available_trial_number", 3001)
    entry = {
        "trial_number": next_num,
        "id": trial_id,
        "result": verdict,
        "note": note,
    }
    ledger["lineage"].append(entry)
    ledger["cumulative_trial_count"] = count + 1
    ledger["next_available_trial_number"] = next_num + 1

    # Update hypothesis count
    if verdict != "REJECTED":
        ledger["new_hypotheses_used"] = ledger.get("new_hypotheses_used", 0) + 1
        ledger["new_hypotheses_remaining"] = ledger.get("new_hypotheses_remaining", 20) - 1

    save_ledger(ledger)

    # Update stopping rule
    return record_trial(verdict)


def get_status() -> dict:
    """Get current Path B status."""
    ledger = load_ledger()
    rule = ledger.get("stopping_rule", {})
    return {
        "trial_count": ledger.get("cumulative_trial_count", 0),
        "cap": ledger.get("cumulative_trial_cap", 25),
        "hypotheses_used": ledger.get("new_hypotheses_used", 0),
        "hypotheses_remaining": ledger.get("new_hypotheses_remaining", 20),
        "consecutive_fail_count": rule.get("consecutive_fail_count", 0),
        "is_stopped": rule.get("is_stopped", False),
        "next_trial_number": ledger.get("next_available_trial_number", 3001),
    }


if __name__ == "__main__":
    status = get_status()
    print("Path B Status:")
    for k, v in status.items():
        print(f"  {k}: {v}")
