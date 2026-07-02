"""
TRIPLE-BARRIER LABELLING -- Replace binary target with risk-adjusted labels.

Labels each bar as:
  +1 (long win)  -- upper barrier touched first
  -1 (long loss) -- lower barrier touched first
   0 (neutral)   -- time barrier expired without either

Barriers are volatility-adjusted (ATR-based) so labels are timeframe-agnostic.

Usage:
    python scripts/label_triple_barrier.py --symbol XAUUSD --freq 1min
    python scripts/label_triple_barrier.py --symbol XAUUSD --freq 1min --method dynamic
    python scripts/label_triple_barrier.py --symbols XAUUSD,EURUSD --all-freqs
"""
import argparse
import json
import os
import warnings
from datetime import datetime, UTC
from glob import glob

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

ROOT = os.path.dirname(os.path.dirname(__file__))
FEAT_DIR = os.path.join(ROOT, "artifacts", "features")
OUT_DIR = os.path.join(ROOT, "artifacts", "labels")


# ----------------------------------------------
# CORE: Triple-Barrier Logic
# ----------------------------------------------

def compute_triple_barrier(
    df: pd.DataFrame,
    k_upper: float = 2.0,
    k_lower: float = 2.0,
    max_bars: int = 20,
    atr_col: str = 'atr_5',
    method: str = 'fixed',
    min_return: float = 0.0001,
) -> pd.DataFrame:
    """
    Assign triple-barrier labels to OHLC data.

    For each bar, look ahead up to `max_bars` bars and check:
    - Upper barrier: price >= close + k_upper * atr  ->  label = +1
    - Lower barrier: price <= close - k_lower * atr  ->  label = -1
    - Time barrier: neither hit within max_bars       ->  label =  0

    Barriers are computed from the entry bar's close + ATR.

    Parameters
    ----------
    df : pd.DataFrame
        Must have columns: 'open', 'high', 'low', 'close', and atr_col.
        Index should be DatetimeIndex.
    k_upper, k_lower : float
        Barrier width in ATR units.
    max_bars : int
        Maximum look-ahead bars (time barrier).
    atr_col : str
        Column name for ATR (e.g. 'atr_5', 'atr_15').
    method : str
        'fixed': barriers are fixed at close ± k * atr (standard).
        'dynamic': barriers widen in high-vol regimes, narrow in low-vol.
    min_return : float
        Minimum absolute return for a non-zero label. If return < min_return,
        label = 0 even if barrier appears touched (noise filter).

    Returns
    -------
    pd.DataFrame with added columns:
        tb_label      : int8  -- +1 / -1 / 0
        tb_bar_hit    : int   -- which bar index the barrier was hit (0-based within horizon)
        tb_side       : str   -- 'upper', 'lower', 'timeout'
        tb_ret        : float -- return at barrier hit
        tb_k_upper    : float -- actual upper barrier used (for audit)
        tb_k_lower    : float -- actual lower barrier used
    """
    if atr_col not in df.columns:
        # Fallback: compute rolling ATR if missing
        print(f"  [WARN] {atr_col} not found, computing from OHLC")
        tr = pd.concat([
            df['high'] - df['low'],
            (df['high'] - df['close'].shift(1)).abs(),
            (df['low'] - df['close'].shift(1)).abs(),
        ], axis=1).max(axis=1)
        df = df.copy()
        df[atr_col] = tr.rolling(5).mean()

    n = len(df)
    labels = np.zeros(n, dtype=np.int8)
    bar_hit = np.full(n, -1, dtype=np.int32)
    side = np.full(n, 'none', dtype=object)
    ret_at_hit = np.zeros(n, dtype=np.float64)
    k_used_upper = np.full(n, k_upper, dtype=np.float64)
    k_used_lower = np.full(n, k_lower, dtype=np.float64)

    if 'close' not in df.columns:
        print("  [ERROR] No 'close' column")
        return pd.DataFrame()

    close = df['close'].values
    high = df['high'].values if 'high' in df.columns else close
    low = df['low'].values if 'low' in df.columns else close
    atr = df[atr_col].values

    # For dynamic method: volatility regime multiplier
    if method == 'dynamic' and 'volatility_15' in df.columns:
        vol_regime = df['volatility_15'].values
        vol_median = np.nanmedian(vol_regime) if vol_regime.size > 0 else 1.0
        # Regime multiplier: low vol (0.5x), normal (1x), high vol (1.5x)
        regime_mult = np.where(
            vol_regime > vol_median * 1.5, 1.5,
            np.where(vol_regime < vol_median * 0.5, 0.5, 1.0)
        )
    else:
        regime_mult = np.ones(n)

    # Look-ahead scan for each bar
    for i in range(n - 1):
        if np.isnan(close[i]) or np.isnan(atr[i]) or atr[i] <= 0:
            continue

        # Effective barrier width (volatility adjusted)
        eff_k_upper = k_upper * regime_mult[i] if method == 'dynamic' else k_upper
        eff_k_lower = k_lower * regime_mult[i] if method == 'dynamic' else k_lower
        k_used_upper[i] = eff_k_upper
        k_used_lower[i] = eff_k_lower

        barrier_upper = close[i] + eff_k_upper * atr[i]
        barrier_lower = close[i] - eff_k_lower * atr[i]

        # Scan forward
        upper_bar = max_bars  # which bar hits upper first
        lower_bar = max_bars

        for j in range(1, min(max_bars + 1, n - i)):
            idx = i + j
            # Upper barrier check: any tick high touched it
            if high[idx] >= barrier_upper and upper_bar == max_bars:
                upper_bar = j
            # Lower barrier check: any tick low touched it
            if low[idx] <= barrier_lower and lower_bar == max_bars:
                lower_bar = j
            # Stop scanning both found (time barrier = whichever hit first)
            if upper_bar < max_bars and lower_bar < max_bars:
                break

        # -- Determine label --
        # Whichever barrier hit first wins
        # If neither, it's a timeout
        if upper_bar < max_bars and (upper_bar <= lower_bar or lower_bar == max_bars):
            # Upper hit first (or simultaneously)
            hit_idx = i + upper_bar
            entry_ret = (close[hit_idx] - close[i]) / close[i]
            if abs(entry_ret) >= min_return:
                labels[i] = 1
                bar_hit[i] = upper_bar
                side[i] = 'upper'
                ret_at_hit[i] = entry_ret
        elif lower_bar < max_bars:
            # Lower hit first
            hit_idx = i + lower_bar
            entry_ret = (close[hit_idx] - close[i]) / close[i]
            if abs(entry_ret) >= min_return:
                labels[i] = -1
                bar_hit[i] = lower_bar
                side[i] = 'lower'
                ret_at_hit[i] = entry_ret
        else:
            # Time barrier expired -- label = 0
            # But check the final return at max_bars
            final_idx = min(i + max_bars, n - 1)
            final_ret = (close[final_idx] - close[i]) / close[i]
            labels[i] = 0
            bar_hit[i] = max_bars
            side[i] = 'timeout'
            ret_at_hit[i] = final_ret

    # Build result
    result = df.copy()
    result['tb_label'] = labels
    result['tb_bar_hit'] = bar_hit
    result['tb_side'] = side
    result['tb_ret'] = np.round(ret_at_hit, 6)
    result['tb_k_upper'] = np.round(k_used_upper, 4)
    result['tb_k_lower'] = np.round(k_used_lower, 4)

    return result


# ----------------------------------------------
# VARIANT: Meta-Label (secondary model)
# ----------------------------------------------

def compute_meta_label(
    df: pd.DataFrame,
    tb_label_col: str = 'tb_label',
    vol_floor: float = 0.001,
) -> pd.Series:
    """
    Meta-label: 1 = take the trade (primary signal + tb_label != 0), 0 = skip.

    The meta-label model predicts *whether* to act on the primary signal,
    not the direction. Useful for filtering low-conviction signals.
    """
    primary = df.get('target', pd.Series(0, index=df.index))
    tb = df.get(tb_label_col, pd.Series(0, index=df.index))

    # Meta-label = 1 when primary signal is non-zero AND tb_label is non-zero
    # (i.e. there is both a direction signal and a risk-adjusted profit opportunity)
    meta = ((primary != 0) & (tb != 0)).astype(int)
    return meta


# ----------------------------------------------
# LOAD / SAVE
# ----------------------------------------------

def load_ohlc(symbol: str, freq: str) -> pd.DataFrame:
    """Load feature file, return OHLC + ATR columns."""
    path = os.path.join(FEAT_DIR, f"features_{symbol}_{freq}.parquet")
    if not os.path.exists(path):
        paths = glob(os.path.join(FEAT_DIR, f"features_{symbol}*{freq}*.parquet"))
        if not paths:
            print(f"  [ERROR] No features for {symbol} @ {freq}")
            return pd.DataFrame()
        path = paths[0]
    df = pd.read_parquet(path)
    # Ensure timestamp index
    if 'timestamp' in df.columns:
        df = df.set_index('timestamp')
    df.index = pd.to_datetime(df.index, utc=True)
    return df


# ----------------------------------------------
# DIAGNOSTIC
# ----------------------------------------------

def diagnostic_report(df: pd.DataFrame, symbol: str, freq: str):
    """Print summary of triple-barrier label distribution."""
    if 'tb_label' not in df.columns:
        print("  [ERROR] No tb_label column")
        return

    labels = df['tb_label'].dropna()

    n_win = int((labels == 1).sum())
    n_loss = int((labels == -1).sum())
    n_neutral = int((labels == 0).sum())
    total = len(labels)

    print(f"\n  -- Triple-Barrier Label Distribution ({symbol} @ {freq}) --")
    print(f"    Total labelled bars: {total}")
    print(f"    +1 (win/upper):  {n_win:>6d} ({100*n_win/total:>5.1f}%)")
    print(f"    -1 (loss/lower): {n_loss:>6d} ({100*n_loss/total:>5.1f}%)")
    print(f"     0 (neutral):    {n_neutral:>6d} ({100*n_neutral/total:>5.1f}%)")
    print(f"    Win/Loss ratio:  {n_win/max(n_loss,1):.3f}")

    if 'tb_bar_hit' in df.columns:
        avg_hit = df.loc[labels != 0, 'tb_bar_hit'].mean()
        print(f"    Avg bars to hit:  {avg_hit:.1f}")

    if 'tb_ret' in df.columns:
        win_ret = df.loc[labels == 1, 'tb_ret'].mean() if n_win > 0 else 0
        loss_ret = df.loc[labels == -1, 'tb_ret'].mean() if n_loss > 0 else 0
        print(f"    Avg win return:   {win_ret*100:+.3f}%")
        print(f"    Avg loss return:  {loss_ret*100:+.3f}%")

    # Side distribution
    if 'tb_side' in df.columns:
        sides = df['tb_side'].value_counts()
        for s, c in sides.items():
            print(f"    Hit {s:<10s}: {c:>6d} ({100*c/total:>5.1f}%)")

    return {
        "symbol": symbol,
        "freq": freq,
        "total": int(total),
        "win": n_win,
        "loss": n_loss,
        "neutral": n_neutral,
        "win_rate": round(n_win / max(total, 1), 4),
        "avg_bars_to_hit": round(float(avg_hit), 1) if 'tb_bar_hit' in df.columns else None,
    }


# ----------------------------------------------
# MAIN
# ----------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Triple-barrier labelling")
    parser.add_argument("--symbol", type=str, default="XAUUSD",
                        help="Single symbol")
    parser.add_argument("--symbols", type=str, default="",
                        help="Comma-separated symbols (overrides --symbol)")
    parser.add_argument("--freq", type=str, default="1min",
                        help="Frequency (used alone or as default)")
    parser.add_argument("--all-freqs", action="store_true",
                        help="Process all available frequencies for each symbol")
    parser.add_argument("--method", choices=["fixed", "dynamic"], default="fixed",
                        help="Barrier method: fixed (std) or dynamic (vol-adjusted)")
    parser.add_argument("--k-upper", type=float, default=2.0,
                        help="Upper barrier width in ATR units")
    parser.add_argument("--k-lower", type=float, default=2.0,
                        help="Lower barrier width in ATR units")
    parser.add_argument("--max-bars", type=int, default=20,
                        help="Time barrier: max look-ahead bars")
    parser.add_argument("--atr-col", type=str, default="atr_5",
                        help="ATR column to use")
    parser.add_argument("--output", type=str, default=OUT_DIR)
    parser.add_argument("--diagnose", action="store_true",
                        help="Print diagnostic report")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    # Resolve symbols
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",")]
    else:
        symbols = [args.symbol]

    # Resolve frequencies
    available_freqs = ["1min", "5min", "15min"]
    if args.all_freqs:
        freqs = available_freqs
    else:
        freqs = [args.freq]

    print(f"{'='*60}")
    print("TRIPLE-BARRIER LABELLING")
    print(f"  Symbols: {symbols}")
    print(f"  Frequencies: {freqs}")
    print(f"  Method: {args.method}")
    print(f"  Barriers: ±{args.k_upper}/{args.k_lower} ATR, time={args.max_bars}bars")
    print(f"  Output: {args.output}")
    print(f"{'='*60}")

    all_results = []
    label_files = []

    for sym in symbols:
        for freq in freqs:
            print(f"\n--- {sym} @ {freq} ---")
            df = load_ohlc(sym, freq)
            if df.empty:
                continue

            # Ensure OHLC columns
            needed = ['close']
            missing = [c for c in needed if c not in df.columns]
            if missing:
                print(f"  [SKIP] Missing columns: {missing}")
                continue

            labelled = compute_triple_barrier(
                df, k_upper=args.k_upper, k_lower=args.k_lower,
                max_bars=args.max_bars, atr_col=args.atr_col,
                method=args.method
            )

            if labelled.empty:
                continue

            # Add metadata
            labelled['symbol'] = sym
            labelled['freq'] = freq

            # Save
            out_path = os.path.join(args.output, f"labels_{sym}_{freq}.parquet")
            labelled.to_parquet(out_path)
            label_files.append(out_path)
            print(f"  Saved: {len(labelled)} labelled bars -> {out_path}")

            # Also save a label-only file (small, fast to load for training)
            label_cols = ['tb_label', 'tb_bar_hit', 'tb_side', 'tb_ret',
                          'tb_k_upper', 'tb_k_lower']
            label_only = labelled[label_cols].copy()
            label_only_path = os.path.join(args.output, f"tb_only_{sym}_{freq}.parquet")
            label_only.to_parquet(label_only_path)
            label_files.append(label_only_path)
            print(f"  Saved labels-only: {label_only_path}")

            # Diagnostic
            if args.diagnose:
                diag = diagnostic_report(labelled, sym, freq)
                if diag:
                    all_results.append(diag)

    # Run record
    record = {
        "run_time_utc": datetime.now(UTC).isoformat(),
        "symbols": symbols,
        "freqs": freqs,
        "method": args.method,
        "k_upper": args.k_upper,
        "k_lower": args.k_lower,
        "max_bars": args.max_bars,
        "atr_col": args.atr_col,
        "output_files": label_files,
        "diagnostics": all_results,
    }
    with open(os.path.join(args.output, "triple_barrier_run.json"), 'w') as f:
        json.dump(record, f, indent=2)

    print(f"\n{'='*60}")
    print("TRIPLE-BARRIER LABELLING COMPLETE")
    print(f"  Files: {len(label_files)}")
    print(f"  Run record: {os.path.join(args.output, 'triple_barrier_run.json')}")

    if all_results:
        print("\n  Summary:")
        for d in all_results:
            print(f"    {d['symbol']} @ {d['freq']}: "
                  f"W={d['win']} L={d['loss']} N={d['neutral']} "
                  f"WR={d['win_rate']:.1%} avg_bars={d['avg_bars_to_hit']}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
