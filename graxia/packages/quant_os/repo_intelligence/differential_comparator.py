"""Differential comparator — compare canonical vs oracle outputs."""
from dataclasses import dataclass, field


@dataclass
class ComparisonResult:
    engine_a: str
    engine_b: str
    match: bool
    mismatches: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def add_mismatch(self, field: str, value_a, value_b, severity: str = "critical"):
        self.mismatches.append({
            "field": field,
            "value_a": value_a,
            "value_b": value_b,
            "severity": severity,
        })
        self.match = False

    def add_warning(self, field: str, value_a, value_b, reason: str):
        self.warnings.append({
            "field": field,
            "value_a": value_a,
            "value_b": value_b,
            "reason": reason,
        })


def compare_signal_ledgers(
    canonical_trades: list[dict],
    oracle_trades: list[dict],
    canonical_engine: str = "quant_os",
    oracle_engine: str = "oracle",
    allow_pnl_mismatch: bool = True,
) -> ComparisonResult:
    result = ComparisonResult(engine_a=canonical_engine, engine_b=oracle_engine, match=True)

    if len(canonical_trades) != len(oracle_trades):
        result.add_mismatch("trade_count", len(canonical_trades), len(oracle_trades), "critical")

    for i, (c, o) in enumerate(zip(canonical_trades, oracle_trades)):
        if c.get("side") != o.get("side"):
            result.add_mismatch(f"trade_{i}.side", c.get("side"), o.get("side"))

        if c.get("timestamp_utc") != o.get("timestamp_utc"):
            result.add_mismatch(f"trade_{i}.timestamp", c.get("timestamp_utc"), o.get("timestamp_utc"))

        if c.get("exit_reason") != o.get("exit_reason"):
            result.add_mismatch(f"trade_{i}.exit_reason", c.get("exit_reason"), o.get("exit_reason"))

        if allow_pnl_mismatch:
            c_pnl = c.get("pnl_net", 0)
            o_pnl = o.get("pnl_net", 0)
            if abs(c_pnl - o_pnl) > 0.01:
                result.add_warning(f"trade_{i}.pnl", c_pnl, o_pnl, "P&L difference — investigate if caused by documented semantic difference")

    return result


def compare_metrics(
    canonical_metrics: dict,
    oracle_metrics: dict,
    canonical_engine: str = "quant_os",
    oracle_engine: str = "oracle",
) -> ComparisonResult:
    result = ComparisonResult(engine_a=canonical_engine, engine_b=oracle_engine, match=True)

    for field in ["total_trades", "win_rate", "profit_factor"]:
        c_val = canonical_metrics.get(field)
        o_val = oracle_metrics.get(field)
        if c_val is not None and o_val is not None and c_val != o_val:
            result.add_mismatch(field, c_val, o_val, "critical")

    for field in ["total_pnl", "max_drawdown"]:
        c_val = canonical_metrics.get(field)
        o_val = oracle_metrics.get(field)
        if c_val is not None and o_val is not None and abs(c_val - o_val) > 0.01:
            result.add_warning(field, c_val, o_val, "P&L difference")

    return result
