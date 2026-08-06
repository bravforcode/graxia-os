"""Map mining mechanism_family -> engine-compatible strategy for P4 screening.

Strategy classes are caller-owned via engine.set_strategy() (engine never
instantiates). Unmapped families are reported no_strategy, NOT forced through
a wrong strategy (honesty over coverage).
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

# Monorepo import bootstrap (same as scripts/run_direction_g_trials.py:35-43):
# some modules import `graxia.packages.quant_os...` — both roots must be on path.
_ROOT = Path(__file__).resolve().parent.parent
_GRAXIA_ROOT = _ROOT.parent.parent
_MONOREPO_ROOT = _GRAXIA_ROOT.parent
for _p in (_MONOREPO_ROOT, _GRAXIA_ROOT, _ROOT.parent, _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from quant_os.strategies.donchian import DonchianBreakout  # noqa: E402
from quant_os.strategies.eur_session_breakout import EurSessionBreakout  # noqa: E402
from quant_os.strategies.happy_gold_scalper import HappyGoldScalper  # noqa: E402
from quant_os.strategies.liquidity_sweep_v2 import LiquiditySweepV2  # noqa: E402
from quant_os.strategies.momentum_12m import Momentum12M  # noqa: E402
from quant_os.strategies.path_b_wrappers import CarryStrategy, FOMCDriftStrategy, TSMOMStrategy  # noqa: E402
from quant_os.strategies.rsi_mean_reversion import RSIMeanReversion  # noqa: E402

FAMILY_TO_STRATEGY: dict[str, dict] = {
    "trend_following": {
        "strategy_class": DonchianBreakout,
        "default_params": {"period": 20, "atr_period": 14},
        "default_tf": "D1",
    },
    "breakout": {
        "strategy_class": DonchianBreakout,
        "default_params": {"period": 20, "atr_period": 14},
        "default_tf": "H1",
    },
    "scalper": {
        "strategy_class": HappyGoldScalper,
        "default_params": {"ema_period": 20, "atr_period": 14},
        "default_tf": "M15",
    },
    "mean_reversion": {
        "strategy_class": RSIMeanReversion,
        "default_params": {"rsi_period": 14, "atr_period": 14},
        "default_tf": "H1",
    },
    "momentum": {
        "strategy_class": Momentum12M,
        "default_params": {"lookback": 252, "atr_period": 14},
        "default_tf": "D1",
    },
    "session": {
        "strategy_class": EurSessionBreakout,
        "default_params": {"atr_fast": 8, "atr_slow": 21},
        "default_tf": "M15",
    },
    "orderflow": {
        "strategy_class": LiquiditySweepV2,
        "default_params": {"sweep_lookback": 20, "rsi_period": 14},
        "default_tf": "M15",
    },
    "carry": {"strategy_class": CarryStrategy, "default_params": {"vol_target": 0.10}, "default_tf": "D1"},
    "vol_targeting": {
        "strategy_class": TSMOMStrategy,
        "default_params": {"lookbacks": (120, 240), "vol_target": 0.15},
        "default_tf": "D1",
    },
    "event": {"strategy_class": FOMCDriftStrategy, "default_params": {}, "default_tf": "D1"},
    "regime": {
        "strategy_class": DonchianBreakout,
        "default_params": {"period": 50, "atr_period": 14},
        "default_tf": "D1",
    },
}

DEFAULT_TF_BY_FAMILY: dict[str, str] = {f: v["default_tf"] for f, v in FAMILY_TO_STRATEGY.items()}


def _strategy_param_names(strategy_class) -> set[str]:
    """Params the strategy __init__ actually accepts (account_type etc. filtered)."""
    try:
        sig = inspect.signature(strategy_class.__init__)
    except (TypeError, ValueError):
        return set()
    return {name for name in sig.parameters if name != "self"}


def resolve_candidate(entry: dict) -> dict:
    family = entry.get("mechanism_family", "other")
    mapping = FAMILY_TO_STRATEGY.get(family)
    if mapping is None:
        return {"status": "no_strategy", "reason": f"family '{family}' has no engine strategy"}
    accepted = _strategy_param_names(mapping["strategy_class"])
    merged = {
        **mapping["default_params"],
        **{k: v for k, v in (entry.get("params") or {}).items() if isinstance(v, int | float | str | bool)},
    }
    # whitelist: entry params are EA metadata (account_type, lot, ...) — only
    # pass what the strategy constructor accepts (audit: account_type VOIDs)
    params = {k: v for k, v in merged.items() if k in accepted}
    tf = entry.get("timeframe") if entry.get("timeframe") and entry.get("timeframe") != "ALL" else mapping["default_tf"]
    return {"status": "ok", "strategy_class": mapping["strategy_class"], "params": params, "timeframe": tf}
