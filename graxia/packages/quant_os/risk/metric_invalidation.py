"""Programmatic legacy metric invalidation labels."""
from enum import Enum

class MetricValidity(Enum):
    VALID = "VALID"
    PARTIALLY_VALID = "PARTIALLY_VALID"
    INVALID_FOR_DECISION = "INVALID_FOR_DECISION"
    SIMULATED_ONLY = "SIMULATED_ONLY"
    UNDETERMINED = "UNDETERMINED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"

# Registry of ALL legacy campaign metric classifications
LEGACY_METRIC_REGISTRY = {
    "gross_pnl": MetricValidity.INVALID_FOR_DECISION,
    "net_pnl_after_costs": MetricValidity.INVALID_FOR_DECISION,
    "expectancy": MetricValidity.INVALID_FOR_DECISION,
    "profit_factor": MetricValidity.INVALID_FOR_DECISION,
    "win_rate": MetricValidity.SIMULATED_ONLY,
    "risk_per_trade": MetricValidity.INVALID_FOR_DECISION,
    "max_drawdown": MetricValidity.INVALID_FOR_DECISION,
    "sharpe_ratio": MetricValidity.INVALID_FOR_DECISION,
    "position_sizing": MetricValidity.INVALID_FOR_DECISION,
    "stop_loss_distance": MetricValidity.INVALID_FOR_DECISION,
    "take_profit_distance": MetricValidity.INVALID_FOR_DECISION,
    "risk_reward_ratio": MetricValidity.SIMULATED_ONLY,
    # Operations telemetry (these are VALID/PARTIALLY_VALID)
    "signal_count": MetricValidity.PARTIALLY_VALID,
    "uptime_seconds": MetricValidity.PARTIALLY_VALID,
    "spread_observations": MetricValidity.PARTIALLY_VALID,
    "connectivity_events": MetricValidity.PARTIALLY_VALID,
    "process_restarts": MetricValidity.VALID,
}

def get_metric_validity(metric_name: str) -> MetricValidity:
    """Get the validity classification for a legacy metric."""
    return LEGACY_METRIC_REGISTRY.get(metric_name, MetricValidity.UNDETERMINED)

def is_metric_usable(metric_name: str) -> bool:
    """Check if a metric can be used for decision-making."""
    validity = get_metric_validity(metric_name)
    return validity in (MetricValidity.VALID, MetricValidity.PARTIALLY_VALID)
