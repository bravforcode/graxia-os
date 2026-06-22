from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import hashlib
import json

class HypothesisStatus(Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    VALIDATED = "validated"
    REJECTED = "rejected"
    ARCHIVED = "archived"

@dataclass
class ValidationProtocol:
    """Validation requirements for a hypothesis."""
    min_trades: int = 30
    min_oos_trades: int = 15
    max_drawdown_pct: float = 20.0
    min_sharpe: float = 0.5
    min_profit_factor: float = 1.2
    require_walk_forward: bool = True
    require_cost_stress: bool = True
    require_regime_analysis: bool = True
    require_oracle_reproduction: bool = False
    
    def evaluate(self, metrics: dict) -> tuple[bool, list[str]]:
        issues = []
        if metrics.get("total_trades", 0) < self.min_trades:
            issues.append(f"MIN_TRADES:{metrics.get('total_trades', 0)}<{self.min_trades}")
        if metrics.get("oos_trades", 0) < self.min_oos_trades:
            issues.append(f"MIN_OOS_TRADES:{metrics.get('oos_trades', 0)}<{self.min_oos_trades}")
        if metrics.get("max_drawdown_pct", 100) > self.max_drawdown_pct:
            issues.append(f"MAX_DRAWDOWN:{metrics.get('max_drawdown_pct', 100)}%>{self.max_drawdown_pct}%")
        if metrics.get("sharpe_ratio", 0) < self.min_sharpe:
            issues.append(f"MIN_SHARPE:{metrics.get('sharpe_ratio', 0)}<{self.min_sharpe}")
        if metrics.get("profit_factor", 0) < self.min_profit_factor:
            issues.append(f"MIN_PF:{metrics.get('profit_factor', 0)}<{self.min_profit_factor}")
        return len(issues) == 0, issues

@dataclass
class EURUSDHypothesis:
    """Single active hypothesis for EURUSD. Only one active at a time."""
    hypothesis_id: str
    market: str = "EURUSD"
    timeframe: str = "H1"
    economic_rationale: str = ""
    entry_logic: str = ""
    exit_logic: str = ""
    stop_logic: str = ""
    take_profit_or_time_stop: str = ""
    expected_trade_frequency: str = ""
    known_failure_regimes: list[str] = field(default_factory=list)
    parameter_budget: int = 12
    data_requirements: list[str] = field(default_factory=list)
    validation_protocol: ValidationProtocol = field(default_factory=ValidationProtocol)
    status: HypothesisStatus = HypothesisStatus.DRAFT
    created_at: str = ""
    
    def fingerprint(self) -> str:
        data = json.dumps({
            "hypothesis_id": self.hypothesis_id,
            "market": self.market,
            "timeframe": self.timeframe,
            "entry_logic": self.entry_logic,
            "exit_logic": self.exit_logic,
            "stop_logic": self.stop_logic,
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()
    
    def is_active(self) -> bool:
        return self.status == HypothesisStatus.ACTIVE
    
    def activate(self) -> None:
        if self.status == HypothesisStatus.DRAFT:
            self.status = HypothesisStatus.ACTIVE
    
    def validate(self) -> tuple[bool, list[str]]:
        issues = []
        if not self.hypothesis_id:
            issues.append("hypothesis_id required")
        if not self.economic_rationale:
            issues.append("economic_rationale required")
        if not self.entry_logic:
            issues.append("entry_logic required")
        if not self.exit_logic:
            issues.append("exit_logic required")
        if not self.stop_logic:
            issues.append("stop_logic required")
        return len(issues) == 0, issues

class HypothesisRegistry:
    """Registry for EURUSD hypotheses. Only one active at a time."""
    
    def __init__(self):
        self._hypotheses: dict[str, EURUSDHypothesis] = {}
    
    def register(self, hypothesis: EURUSDHypothesis) -> tuple[bool, str]:
        valid, issues = hypothesis.validate()
        if not valid:
            return False, "; ".join(issues)
        
        if hypothesis.hypothesis_id in self._hypotheses:
            return False, "DUPLICATE_ID"
        
        # Check only one active
        active = [h for h in self._hypotheses.values() if h.is_active()]
        if active and hypothesis.is_active():
            return False, f"ACTIVE_EXISTS:{active[0].hypothesis_id}"
        
        self._hypotheses[hypothesis.hypothesis_id] = hypothesis
        return True, "REGISTERED"
    
    def get_active(self) -> Optional[EURUSDHypothesis]:
        for h in self._hypotheses.values():
            if h.is_active():
                return h
        return None
    
    def get(self, hypothesis_id: str) -> Optional[EURUSDHypothesis]:
        return self._hypotheses.get(hypothesis_id)
    
    def list_all(self) -> list[EURUSDHypothesis]:
        return list(self._hypotheses.values())
    
    def count_active(self) -> int:
        return sum(1 for h in self._hypotheses.values() if h.is_active())
