"""
Triple-Barrier Labeling — Marcos López de Prado method.

Labels each bar as:
  1  = Win (TP hit first)
  -1 = Loss (SL hit first OR both hit in same bar)
  0  = Time-out (max_bars reached)

Intra-bar ambiguity rule: If both TP and SL are touched in the same bar,
label = -1 (assume worst case — conservative risk management).
"""
import os
import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger()


def compute_triple_barrier(
    df: pd.DataFrame,
    tp_mult: float = 1.5,
    sl_mult: float = 1.0,
    max_bars: int = 12,
    atr_col: str = "atr_14",
) -> pd.Series:
    """
    Compute triple-barrier labels for each bar.

    Args:
        df: DataFrame with columns [open, high, low, close, atr_14].
        tp_mult: Take-profit = close + (ATR * tp_mult).
        sl_mult: Stop-loss = close - (ATR * sl_mult).
        max_bars: Maximum holding period in bars.
        atr_col: Column name for ATR values.

    Returns:
        Series of labels: 1 (win), -1 (loss), 0 (timeout).
    """
    required = ["open", "high", "low", "close", atr_col]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    n = len(df)
    labels = pd.Series(0, index=df.index, dtype=np.int8, name="label")

    close_arr = df["close"].values
    high_arr = df["high"].values
    low_arr = df["low"].values
    atr_arr = df[atr_col].values

    labeled = 0
    tp_hits = 0
    sl_hits = 0
    timeouts = 0
    both_hits = 0

    for i in range(n - max_bars):
        current_close = close_arr[i]
        volatility = atr_arr[i]

        if volatility <= 0 or np.isnan(volatility):
            labels.iloc[i] = 0
            timeouts += 1
            continue

        tp_price = current_close + (volatility * tp_mult)
        sl_price = current_close - (volatility * sl_mult)

        outcome = 0  # default = timeout

        for j in range(1, max_bars + 1):
            bar_high = high_arr[i + j]
            bar_low = low_arr[i + j]

            hit_tp = bar_high >= tp_price
            hit_sl = bar_low <= sl_price

            if hit_tp and hit_sl:
                # Intra-bar ambiguity: assume worst case = LOSS
                outcome = -1
                both_hits += 1
                break
            elif hit_sl:
                outcome = -1
                sl_hits += 1
                break
            elif hit_tp:
                outcome = 1
                tp_hits += 1
                break

        labels.iloc[i] = outcome
        labeled += 1
        if outcome == 0:
            timeouts += 1

    logger.info(
        "triple_barrier_complete",
        total_bars=n,
        labeled=labeled,
        tp_hits=tp_hits,
        sl_hits=sl_hits,
        timeouts=timeouts,
        both_hits=both_hits,
        win_rate=round(tp_hits / max(labeled, 1) * 100, 2),
    )

    return labels


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Add ATR column to DataFrame if not present."""
    if "atr_14" in df.columns:
        return df

    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    n = len(df)

    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )

    atr = np.zeros(n)
    atr[:period] = np.nan
    atr[period] = np.mean(tr[1 : period + 1])
    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    df = df.copy()
    df["atr_14"] = atr
    return df


def prepare_labeled_dataset(
    df: pd.DataFrame,
    tp_mult: float = 1.5,
    sl_mult: float = 1.0,
    max_bars: int = 12,
) -> pd.DataFrame:
    """
    Full pipeline: add ATR → compute labels → return clean dataset.

    Args:
        df: OHLCV DataFrame with columns [time, open, high, low, close, symbol].
        tp_mult: Take-profit multiplier.
        sl_mult: Stop-loss multiplier.
        max_bars: Max holding period.

    Returns:
        DataFrame with added columns: atr_14, label, tp_price, sl_price.
    """
    df = add_atr(df)

    # Compute labels
    labels = compute_triple_barrier(df, tp_mult, sl_mult, max_bars)
    df = df.copy()
    df["label"] = labels

    # Add TP/SL prices for reference
    df["tp_price"] = df["close"] + (df["atr_14"] * tp_mult)
    df["sl_price"] = df["close"] - (df["atr_14"] * sl_mult)

    # Drop rows with NaN ATR (first 14 bars)
    df = df.dropna(subset=["atr_14"])

    # Drop last max_bars rows (incomplete labels)
    df = df.iloc[: -max_bars] if max_bars > 0 else df

    logger.info(
        "labeled_dataset_ready",
        rows=len(df),
        label_distribution=df["label"].value_counts().to_dict(),
    )

    return df


def label_from_source(
    symbol: str = "XAUUSD",
    timeframe: str = "H1",
    tp_mult: float = 1.5,
    sl_mult: float = 1.0,
    max_bars: int = 12,
    source: str = "auto",
    **loader_kwargs,
) -> pd.DataFrame:
    """Load OHLCV from any source and run Triple-Barrier labeling.

    This is the unified entry point that bridges data loading -> labeling.

    Args:
        symbol: Trading symbol.
        timeframe: Timeframe (M15, H1, D1, etc.).
        tp_mult: Take-profit ATR multiplier.
        sl_mult: Stop-loss ATR multiplier.
        max_bars: Max holding period.
        source: Data source ("auto", "duckdb", "warehouse", "csv").
                "auto" tries DuckDB -> Warehouse -> CSV in order.
        **loader_kwargs: Passed to load_ohlcv (start_date, end_date, etc.).

    Returns:
        Labeled DataFrame with atr_14, label, tp_price, sl_price columns.
    """
    import importlib.util

    # Direct file import to avoid __init__.py chain with relative imports
    _loader_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "backtest", "data_loader.py"
    )
    _spec = importlib.util.spec_from_file_location("data_loader", _loader_path)
    _dl = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_dl)
    load_ohlcv = _dl.load_ohlcv

    if source == "auto":
        sources = ["duckdb", "warehouse", "csv"]
    else:
        sources = [source]

    df = load_ohlcv(
        symbol=symbol,
        timeframe=timeframe,
        sources=sources,
        **loader_kwargs,
    )

    logger.info("data_loaded", symbol=symbol, timeframe=timeframe, rows=len(df))

    return prepare_labeled_dataset(df, tp_mult=tp_mult, sl_mult=sl_mult, max_bars=max_bars)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Triple-Barrier Labeling")
    parser.add_argument("--symbol", default="XAUUSD", help="Symbol")
    parser.add_argument("--timeframe", default="H1", help="Timeframe (M15, H1, D1)")
    parser.add_argument("--tp-mult", type=float, default=1.5, help="TP ATR multiplier")
    parser.add_argument("--sl-mult", type=float, default=1.0, help="SL ATR multiplier")
    parser.add_argument("--max-bars", type=int, default=12, help="Max holding bars")
    parser.add_argument("--source", default="auto", choices=["auto", "duckdb", "warehouse", "csv"])
    parser.add_argument("--start-date", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default=None, help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    df = label_from_source(
        symbol=args.symbol,
        timeframe=args.timeframe,
        tp_mult=args.tp_mult,
        sl_mult=args.sl_mult,
        max_bars=args.max_bars,
        source=args.source,
        start_date=args.start_date,
        end_date=args.end_date,
    )

    print(f"\nLabeled {len(df)} bars for {args.symbol} {args.timeframe}")
    print("\nLabel distribution:")
    print(df["label"].value_counts().sort_index())

    win_rate = (df["label"] == 1).sum() / len(df) * 100
    loss_rate = (df["label"] == -1).sum() / len(df) * 100
    timeout_rate = (df["label"] == 0).sum() / len(df) * 100

    print(f"\nWin: {win_rate:.1f}%")
    print(f"Loss: {loss_rate:.1f}%")
    print(f"Timeout: {timeout_rate:.1f}%")
