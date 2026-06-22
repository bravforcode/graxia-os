"""EURUSD validation protocol — clean research foundation.

Preconditions for any EURUSD candidate:
1. Phase 3B has a formal XAU outcome
2. EURUSD MT5 data manifests exist for every required timeframe
3. Contract snapshots exist for EURUSD
4. Dataset overlap and UTC/timezone policy are verified
5. No Yahoo, synthetic, or mixed vendor fallback in final evaluation data
"""
from dataclasses import dataclass, field
from typing import Optional
import hashlib
import json


@dataclass
class EURUSDValidationProtocol:
    """Validation requirements for EURUSD research."""
    
    required_timeframes: list = field(default_factory=lambda: ["D1", "H1", "M15"])
    require_mt5_source: bool = True
    require_no_yahoo: bool = True
    require_no_synthetic: bool = True
    
    require_contract_snapshot: bool = True
    require_fingerprint_match: bool = True
    
    parameter_budget: int = 12
    require_point_in_time: bool = True
    require_no_xauusd_params: bool = True
    
    min_trades: int = 30
    min_oos_trades: int = 15
    require_walk_forward: bool = True
    require_cost_stress: bool = True
    require_regime_analysis: bool = True
    require_oracle_reproduction: bool = False

    def validate_preconditions(self, context: dict) -> tuple[bool, list[str]]:
        """Check all preconditions are met before starting research."""
        issues = []
        
        if not context.get("xau_outcome"):
            issues.append("PHASE_3B_OUTCOME_MISSING: No formal XAU outcome")
        
        for tf in self.required_timeframes:
            key = f"manifest_{tf}"
            if not context.get(key):
                issues.append(f"MANIFEST_MISSING: {tf} data manifest not found")
        
        if self.require_contract_snapshot and not context.get("contract_snapshot"):
            issues.append("CONTRACT_SNAPSHOT_MISSING: No EURUSD contract snapshot")
        
        if not context.get("timezone_verified"):
            issues.append("TIMEZONE_NOT_VERIFIED: UTC/timezone policy not verified")
        
        if self.require_no_yahoo and context.get("vendor") == "yahoo":
            issues.append("YAHOO_VENDOR_FORBIDDEN: Yahoo data not allowed in final evaluation")
        
        if self.require_no_synthetic and context.get("vendor") == "synthetic":
            issues.append("SYNTHETIC_VENDOR_FORBIDDEN: Synthetic data not allowed")
        
        return len(issues) == 0, issues

    def evaluate_metrics(self, metrics: dict) -> tuple[bool, list[str]]:
        """Evaluate strategy metrics against protocol thresholds."""
        issues = []
        if metrics.get("total_trades", 0) < self.min_trades:
            issues.append(f"MIN_TRADES:{metrics.get('total_trades', 0)}<{self.min_trades}")
        if metrics.get("oos_trades", 0) < self.min_oos_trades:
            issues.append(f"MIN_OOS_TRADES:{metrics.get('oos_trades', 0)}<{self.min_oos_trades}")
        if metrics.get("max_drawdown_pct", 100) > 20.0:
            issues.append(f"MAX_DRAWDOWN:{metrics.get('max_drawdown_pct', 100)}%>20%")
        if metrics.get("sharpe_ratio", 0) < 0.5:
            issues.append(f"MIN_SHARPE:{metrics.get('sharpe_ratio', 0)}<0.5")
        if metrics.get("profit_factor", 0) < 1.2:
            issues.append(f"MIN_PF:{metrics.get('profit_factor', 0)}<1.2")
        return len(issues) == 0, issues


@dataclass
class ResearchHypothesis:
    """EURUSD research hypothesis template."""
    
    hypothesis_id: str
    market: str = "EURUSD"
    primary_timeframe: str = "H1"
    rationale: str = ""
    entry_rule: str = ""
    exit_rule: str = ""
    stop_rule: str = ""
    time_stop_rule: str = ""
    expected_frequency: str = ""
    known_failure_regimes: list = field(default_factory=list)
    parameter_budget: int = 12
    feature_availability_policy: str = "Point-in-time only"
    
    def fingerprint(self) -> str:
        """Deterministic fingerprint of hypothesis definition."""
        data = json.dumps({
            "hypothesis_id": self.hypothesis_id,
            "market": self.market,
            "primary_timeframe": self.primary_timeframe,
            "entry_rule": self.entry_rule,
            "exit_rule": self.exit_rule,
            "stop_rule": self.stop_rule,
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()
