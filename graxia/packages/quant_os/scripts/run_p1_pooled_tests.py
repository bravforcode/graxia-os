"""
P1 runner — pooled DK-test for the 3 comprehensive_edge_search.py candidates
(donchian_20, donchian_vol_filter, tsm_dxy_divergence) via the generic
strategies/ Strategy-ABC ports (donchian_p1.py, tsm_dxy_divergence.py).

Usage: python scripts/run_p1_pooled_tests.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # C:\Users\menum\graxia os
sys.path.insert(0, str(ROOT))

from graxia.packages.quant_os.scripts.pooled_strategy_test import run_strategy
from graxia.packages.quant_os.strategies.donchian_p1 import DonchianBandStop
from graxia.packages.quant_os.strategies.tsm_dxy_divergence import TSMDXYDivergence


def main():
    run_strategy(
        strategy_name="DonchianP1",
        variants={
            "donchian_20": lambda: DonchianBandStop(vol_filter_mode="none"),
            "donchian_vol_filter": lambda: DonchianBandStop(vol_filter_mode="skip_high_vol"),
        },
        variant_params={
            "donchian_20": {"period": 20, "vol_filter_mode": "none"},
            "donchian_vol_filter": {"period": 20, "vol_filter_mode": "skip_high_vol"},
        },
    )

    run_strategy(
        strategy_name="TSMDXYDivergence",
        variants={
            "tsm_dxy_divergence": lambda: TSMDXYDivergence(),
        },
        variant_params={
            "tsm_dxy_divergence": {"lookbacks": [20, 40, 60, 120], "atr_sl_mult": 4.0},
        },
    )


if __name__ == "__main__":
    main()
