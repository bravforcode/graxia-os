"""Phase 11 — Controlled expansion policy."""
from dataclasses import dataclass, field
from enum import Enum


class ExpansionTier(Enum):
    TIER_1 = "tier_1"  # More evidence before more risk
    TIER_2 = "tier_2"  # More validation before more symbols
    TIER_3 = "tier_3"  # More symbols before more leverage
    TIER_4 = "tier_4"  # More brokers after one proven


@dataclass
class ExpansionPolicy:
    """Expansion order is fixed. No shortcuts."""
    current_tier: ExpansionTier = ExpansionTier.TIER_1
    max_symbols_per_tier: dict = field(default_factory=lambda: {
        ExpansionTier.TIER_1: 1,
        ExpansionTier.TIER_2: 2,
        ExpansionTier.TIER_3: 5,
        ExpansionTier.TIER_4: 5,
    })
    max_leverage_per_tier: dict = field(default_factory=lambda: {
        ExpansionTier.TIER_1: 1,
        ExpansionTier.TIER_2: 1,
        ExpansionTier.TIER_3: 2,
        ExpansionTier.TIER_4: 5,
    })
    require_separate_broker_lifecycle: bool = True
    crypto_separate_program: bool = True
    news_sentiment_only_after_shadow_ablation: bool = True
    ml_only_as_regime_layer: bool = True

    def can_add_symbol(self) -> bool:
        current_max = self.max_symbols_per_tier.get(self.current_tier, 1)
        return current_max > 1

    def can_increase_leverage(self) -> bool:
        current_max = self.max_leverage_per_tier.get(self.current_tier, 1)
        return current_max > 1

    def can_add_broker(self) -> bool:
        return self.current_tier == ExpansionTier.TIER_4

    def validate(self) -> tuple[bool, list[str]]:
        issues = []
        if self.crypto_separate_program is False:
            issues.append("crypto_separate_program must be True")
        if self.ml_only_as_regime_layer is False:
            issues.append("ml_only_as_regime_layer must be True")
        return len(issues) == 0, issues
