"""Dukascopy M15 integrity check — run after aggregate_ticks_to_m15.py."""
import sys
import pandas as pd
from pathlib import Path

_QUANT_OS = Path(__file__).resolve().parent.parent
if str(_QUANT_OS.parent) not in sys.path:
    sys.path.insert(0, str(_QUANT_OS.parent))

from quant_os.core.schemas import validate_ohlcv


def full_integrity_check(path: str) -> dict:
    b = pd.read_parquet(path)
    b.index = pd.to_datetime(b.index)

    validate_ohlcv(b, source=path)

    expected_freq = pd.Timedelta("15min")
    diffs = b.index.to_series().diff().dropna()
    long_gaps = diffs[diffs > expected_freq * 4]
    weekend_gaps = diffs[diffs > pd.Timedelta("2 days")]

    null_pct = b.isnull().mean()
    close_rets = b["close"].pct_change().dropna()
    skewness = close_rets.skew()
    kurtosis = close_rets.kurtosis()
    vol_bar_corr = b["volume"].corr(b["high"] - b["low"])

    report = {
        "total_bars": len(b),
        "date_range": f"{b.index[0]} → {b.index[-1]}",
        "null_pct_max": null_pct.max(),
        "non_weekend_gaps": len(long_gaps) - len(weekend_gaps),
        "price_jump_max": close_rets.abs().max(),
        "n_jumps_gt_2pct": (close_rets.abs() > 0.02).sum(),
        "return_skewness": skewness,
        "return_kurtosis": kurtosis,
        "vol_bar_corr": vol_bar_corr,
        "avg_spread_usd": b.get("avg_spread", pd.Series([0])).mean(),
    }

    print("\n=== DUKASCOPY M15 INTEGRITY REPORT ===")
    for k, v in report.items():
        if isinstance(v, float):
            print(f"  {k:<25} {v:>12.6f}")
        else:
            print(f"  {k:<25} {v:>12}")

    assert report["total_bars"] >= 260_000, f"Expected >=260k bars for 10yr M15. Got {report['total_bars']:,}"
    assert report["null_pct_max"] < 0.005, f"Too many nulls: {report['null_pct_max']:.3%}"
    assert report["price_jump_max"] < 0.05, f"Price jump too large: {report['price_jump_max']:.3%}"
    assert report["non_weekend_gaps"] < 100, f"Too many non-weekend gaps: {report['non_weekend_gaps']}"

    print("\n\u2705 ALL INTEGRITY CHECKS PASSED")
    return report


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python {__file__} path/to/m15.parquet")
        sys.exit(1)
    full_integrity_check(sys.argv[1])
