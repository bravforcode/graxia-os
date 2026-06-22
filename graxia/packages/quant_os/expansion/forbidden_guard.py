"""Phase BE-P13 — Forbidden expansion guard."""
from dataclasses import dataclass


FORBIDDEN = [
    ("raising_risk_on_win_streak", "Never raise risk because of recent wins"),
    ("adding_symbols_to_recover_drawdown", "Never add symbols to recover drawdown"),
    ("adding_brokers_to_hide_evidence", "Never add brokers to hide poor evidence"),
    ("adding_llm_to_override_rejects", "Never add LLM to override deterministic rejects"),
    ("mixing_crypto_and_fx", "Never mix crypto and FX execution ledger"),
    ("using_xauusd_on_eurusd", "Never use XAUUSD-tuned strategy on EURUSD"),
]


class ForbiddenExpansionGuard:
    """Guard against forbidden expansion patterns."""
    
    def check(self, description: str) -> tuple[bool, list[str]]:
        violations = []
        desc_lower = description.lower()
        for forbidden_id, reason in FORBIDDEN:
            parts = [p for p in forbidden_id.split("_") if len(p) > 2]
            if all(p in desc_lower for p in parts):
                violations.append(f"{forbidden_id}: {reason}")
        return len(violations) == 0, violations
    
    def is_clean(self, description: str) -> bool:
        ok, _ = self.check(description)
        return ok
