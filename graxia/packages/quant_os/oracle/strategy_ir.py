"""Phase BE-P5 — Canonical strategy IR. Expressible without production engine."""
from dataclasses import dataclass, asdict
import hashlib
import json


@dataclass
class StrategyIR:
    """Strategy Intermediate Representation for oracle reproduction."""
    strategy_snapshot_hash: str = ""
    symbol: str = ""
    timeframe: str = ""
    decision_time_utc: str = ""
    direction: str = ""  # BUY, SELL
    entry_eligibility: str = "NEXT_ELIGIBLE_TICK_OR_BAR"
    stop_rule: str = ""
    take_profit_rule: str = ""
    time_stop_rule: str = ""
    feature_snapshot_hash: str = ""
    parameter_snapshot_hash: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "StrategyIR":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def compute_hash(self) -> str:
        d = self.to_dict()
        return hashlib.sha256(
            json.dumps(d, sort_keys=True).encode()
        ).hexdigest()

    def validate(self) -> tuple[bool, list[str]]:
        issues = []
        if not self.symbol:
            issues.append("symbol required")
        if not self.timeframe:
            issues.append("timeframe required")
        if self.direction not in ("BUY", "SELL", ""):
            issues.append(f"invalid direction: {self.direction}")
        if not self.stop_rule:
            issues.append("stop_rule required")
        return len(issues) == 0, issues


@dataclass
class OracleSignal:
    """Normalized signal from any oracle adapter."""
    signal_id: str = ""
    strategy_ir_hash: str = ""
    direction: str = ""
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    timestamp_utc: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OracleTrade:
    """Normalized trade from any oracle adapter."""
    trade_id: str = ""
    signal_id: str = ""
    direction: str = ""
    entry_price: float = 0.0
    exit_price: float = 0.0
    entry_time_utc: str = ""
    exit_time_utc: str = ""
    pnl_points: float = 0.0
    pnl_after_costs: float = 0.0
    cost_breakdown: dict = None

    def __post_init__(self):
        if self.cost_breakdown is None:
            self.cost_breakdown = {}

    def to_dict(self) -> dict:
        return asdict(self)
