"""Phase BE-P7 — Anti-contamination guard. No XAUUSD parameter transfer."""
from dataclasses import dataclass


@dataclass
class ContaminationCheck:
    source_market: str
    target_market: str
    parameter_name: str
    is_contaminated: bool
    reason: str = ""


class AntiContaminationGuard:
    """Prevent XAUUSD parameters from being used in EURUSD without hypothesis."""

    FORBIDDEN_TRANSFERS = [
        "xauusd_to_eurusd_thresholds",
        "xauusd_to_eurusd_parameters",
        "xauusd_to_eurusd_features",
    ]

    def __init__(self):
        self._violations: list[ContaminationCheck] = []

    def check_transfer(self, source: str, target: str,
                       parameter_name: str) -> ContaminationCheck:
        """Check if parameter transfer is allowed."""
        is_forbidden = (
            source.lower() == "xauusd" and
            target.lower() == "eurusd" and
            not parameter_name.startswith("hypothesis_")
        )

        check = ContaminationCheck(
            source_market=source,
            target_market=target,
            parameter_name=parameter_name,
            is_contaminated=is_forbidden,
            reason="XAUUSD->EURUSD transfer forbidden without hypothesis" if is_forbidden else "",
        )

        if is_forbidden:
            self._violations.append(check)

        return check

    def has_violations(self) -> bool:
        return len(self._violations) > 0

    def get_violations(self) -> list[ContaminationCheck]:
        return self._violations.copy()

    def is_clean(self) -> bool:
        return not self.has_violations()
