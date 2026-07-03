#!/usr/bin/env python3
"""
TSM Paper Trade Bot — Multi-Asset Portfolio with Weekly Rebalance
===============================================================

Ensemble TSM (Time-Series Momentum) strategy — DSR+PBO EDGE_CONFIRMED:
  - Equal-weight ensemble: [0.25, 0.25, 0.25, 0.25] at lookbacks [20, 40, 60, 120]
  - Signal: vol-scaled returns (rolling_sum / rolling_std) per lookback
  - 8 assets: XAUUSD, EURUSD, GBPUSD, USDJPY, BTC, ETH, SILVER, OIL
  - Weekly rebalance (Friday close)
  - Portfolio vol-targeting: 10% annualized target, cap 1.5x leverage
  - Per-asset measured costs from config/cost_calibration.json

Modes:
  --dry-run   Compute signals & target positions, log to CSV/JSON, no MT5 orders
  --live      Connect to MT5, place orders on Pepperstone demo account

Kill-switch: checks risk/kill_switch.py before any order execution.

Usage:
    python scripts/tsm_paper_trade.py --dry-run
    python scripts/tsm_paper_trade.py --live
    python scripts/tsm_paper_trade.py --live --force-rebalance

Cron (weekly Friday 22:00 UTC, after NY close):
    0 22 * * 5 cd /path/to/quant_os && python scripts/tsm_paper_trade.py --live
"""

# Load .env before anything else
try:
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

import argparse
import csv
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
# Insert grandparent so `quant_os` is a proper package (enables relative imports in submodules)
_grandparent = BASE.parent
if str(_grandparent) not in sys.path:
    sys.path.insert(0, str(_grandparent))

# OMS imports — all order flow must route through the OMS risk gate
from quant_os.execution.adapters.mt5 import MT5Adapter
from quant_os.execution.oms import OMS
from quant_os.risk.pre_trade_gate import PreTradeRiskGate, symbol_to_asset_class

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

# Ensemble TSM parameters (DSR+PBO EDGE_CONFIRMED)
LOOKBACKS = [20, 40, 60, 120]  # 4-lookback ensemble
WEIGHTS = [0.25, 0.25, 0.25, 0.25]  # Equal-weight
TARGET_VOL = 0.10  # 10% annualized vol target
MAX_LEVERAGE = 1.5  # Cap on per-asset leverage
RVOL_WINDOW = 60  # Realized vol lookback (days)
MIN_LOT = 0.01  # Minimum lot size across all symbols
MAGIC_NUMBER = 202507  # MT5 magic for TSM bot

# Per-asset measured costs (loaded from config/cost_calibration.json)
COST_CALIBRATION_PATH = BASE / "config" / "cost_calibration.json"


def load_cost_calibration() -> dict[str, float]:
    """Load per-asset round-trip cost in bps from measured calibration."""
    if not COST_CALIBRATION_PATH.exists():
        log("⚠️ cost_calibration.json not found, falling back to 10bps default")
        return {}
    with open(COST_CALIBRATION_PATH) as f:
        cal = json.load(f)
    costs = {}
    for mt5_sym, info in cal.get("assets", {}).items():
        rt_bps = info.get("round_trip_bps_measured", 10.0)
        costs[mt5_sym] = rt_bps
    return costs


COST_MAP = load_cost_calibration()  # {mt5_symbol: round_trip_bps}

# Assets in the parquet (yfinance column names)
ASSETS = [
    "XAUUSD",
    "EURUSD_YF",
    "GBPUSD_YF",
    "USDJPY",
    "BTC_YF",
    "ETH_YF",
    "SILVER",
    "OIL",
]

# Map parquet asset names → MT5 symbol names
MT5_SYMBOL_MAP = {
    "XAUUSD": "XAUUSD",
    "EURUSD_YF": "EURUSD",
    "GBPUSD_YF": "GBPUSD",
    "USDJPY": "USDJPY",
    "BTC_YF": "BTCUSD",
    "ETH_YF": "ETHUSD",
    "SILVER": "XAGUSD",
    "OIL": "USOIL",
}

# Contract sizes for lot→notional conversion (Pepperstone defaults)
CONTRACT_SIZES = {
    "XAUUSD": 100,  # 1 lot = 100 troy oz
    "EURUSD": 100_000,  # 1 lot = 100k units
    "GBPUSD": 100_000,
    "USDJPY": 100_000,
    "BTCUSD": 1,  # 1 lot = 1 BTC
    "ETHUSD": 1,  # 1 lot = 1 ETH
    "XAGUSD": 5_000,  # 1 lot = 5000 troy oz
    "USOIL": 1_000,  # 1 lot = 1000 barrels
}

# Paths
PARQUET_PATH = BASE / "artifacts" / "portfolio" / "d1_multi_asset.parquet"
TRADE_LOG_DIR = BASE / "artifacts" / "portfolio" / "paper_trades"
STATE_PATH = TRADE_LOG_DIR / "tsm_portfolio_state.json"
CSV_LOG_PATH = TRADE_LOG_DIR / "tsm_trade_log.csv"
HEARTBEAT_PATH = BASE / "data" / "tsm_heartbeat.txt"

CSV_HEADERS = [
    "timestamp",
    "asset",
    "mt5_symbol",
    "signal",
    "weight",
    "vol_scale",
    "target_lots",
    "order_type",
    "lot_size",
    "price",
    "status",
    "notes",
]


# ═══════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════


def log(msg: str):
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    safe = msg.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
    try:
        print(f"[{ts}] {safe}")
    except UnicodeEncodeError:
        print(f"[{ts}] {safe.encode('ascii', errors='replace').decode('ascii')}")


def get_notifier():
    from quant_os.core.telegram_notify import TelegramNotifier

    try:
        return TelegramNotifier()
    except RuntimeError as e:
        log(f"Telegram not configured: {e}")
        return None


NOTIFIER = get_notifier()


def tg(msg: str):
    if NOTIFIER:
        NOTIFIER.send(msg)
    log(msg)


# ═══════════════════════════════════════════════════════════════
# KILL SWITCH & AUTO-STOP
# ═══════════════════════════════════════════════════════════════

# Auto-stop threshold: 15% drawdown (conservative, below backtest max DD of 42.11%)
AUTO_STOP_THRESHOLD_PCT = 15.0


def get_kill_switch():
    """Get or create KillSwitch instance."""
    from quant_os.risk.kill_switch import KillSwitch

    return KillSwitch(str(BASE / "data" / "kill_switch_state.json"))


def get_auto_stop(kill_switch=None):
    """Get or create AutoStop instance."""
    from quant_os.risk.auto_stop import AutoStop

    if kill_switch is None:
        kill_switch = get_kill_switch()
    return AutoStop(
        kill_switch=kill_switch,
        threshold_pct=AUTO_STOP_THRESHOLD_PCT,
        state_file=str(BASE / "data" / "auto_stop_state.json"),
    )


def check_kill_switch() -> bool:
    """Return True if trading is allowed (kill switch NOT active)."""
    try:
        ks = get_kill_switch()
        if ks.is_active():
            log("⛔ KILL SWITCH ACTIVE — all trading halted")
            tg("⛔ *TSM Bot*: Kill switch ACTIVE — skipping rebalance")
            return False
        if ks.is_paused():
            log("⏸️ Kill switch PAUSED — no new entries")
            tg("⏸️ *TSM Bot*: Kill switch PAUSED — skipping rebalance")
            return False
        return True
    except Exception as e:
        log(f"⚠️ Kill switch check failed: {e} — proceeding cautiously")
        return True


def check_auto_stop(equity: float) -> bool:
    """
    Check auto-stop drawdown protection.

    Args:
        equity: Current portfolio equity.

    Returns:
        True if trading is allowed (auto-stop NOT triggered).
        False if auto-stop is triggered (should halt trading).
    """
    try:
        ks = get_kill_switch()
        auto_stop = get_auto_stop(ks)

        # Update equity and check drawdown
        status = auto_stop.update_equity(equity)
        dd_pct = status.get("current_drawdown_pct", 0.0)
        hwm = status.get("high_water_mark", 0.0)

        log(
            f"📊 Drawdown check: equity=${equity:,.2f} HWM=${hwm:,.2f} DD={dd_pct:+.2f}% threshold={AUTO_STOP_THRESHOLD_PCT:.1f}%"
        )

        if auto_stop.is_triggered:
            log("🛑 AUTO-STOP TRIGGERED — drawdown exceeded threshold")
            tg(
                f"🛑 *TSM Bot*: AUTO-STOP TRIGGERED\n"
                f"Drawdown: {dd_pct:.2f}% > Threshold: {AUTO_STOP_THRESHOLD_PCT:.1f}%\n"
                f"Equity: ${equity:,.2f} | HWM: ${hwm:,.2f}\n"
                f"Kill switch activated. Manual reset required."
            )
            return False

        return True
    except Exception as e:
        log(f"⚠️ Auto-stop check failed: {e} — proceeding cautiously")
        return True


# ═══════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════


def load_data() -> pd.DataFrame:
    """Load D1 multi-asset data from parquet."""
    if not PARQUET_PATH.exists():
        raise FileNotFoundError(
            f"Portfolio data not found: {PARQUET_PATH}\n" f"Run: python scripts/build_d1_portfolio.py"
        )
    df = pd.read_parquet(PARQUET_PATH)
    df.index = pd.to_datetime(df.index, utc=True)
    return df.sort_index()


def get_close_matrix(data: pd.DataFrame) -> pd.DataFrame:
    """Extract close price matrix for all assets."""
    cols = {}
    for asset in ASSETS:
        col = f"{asset}_close"
        if col in data.columns:
            cols[asset] = data[col]
    if not cols:
        raise ValueError("No close columns found in parquet data")
    return pd.DataFrame(cols)


def fetch_live_prices(assets: list[str]) -> dict[str, float]:
    """Fetch latest close prices via yfinance as fallback."""
    import yfinance as yf

    yf_map = {
        "XAUUSD": "GC=F",
        "EURUSD_YF": "EURUSD=X",
        "GBPUSD_YF": "GBPUSD=X",
        "USDJPY": "USDJPY=X",
        "BTC_YF": "BTC-USD",
        "ETH_YF": "ETH-USD",
        "SILVER": "SI=F",
        "OIL": "CL=F",
    }
    prices = {}
    for asset in assets:
        ticker = yf_map.get(asset)
        if not ticker:
            continue
        try:
            data = yf.download(ticker, period="5d", progress=False, auto_adjust=True)
            if not data.empty:
                prices[asset] = float(data["Close"].iloc[-1])
        except Exception as e:
            log(f"⚠️ yfinance fetch failed for {asset}: {e}")
    return prices


# ═══════════════════════════════════════════════════════════════
# ENSEMBLE TSM SIGNAL COMPUTATION
# ═══════════════════════════════════════════════════════════════


def raw_signal(returns: pd.Series, lookback: int) -> pd.Series:
    """Vol-scaled momentum: rolling_sum / rolling_std for a single lookback."""
    r = returns.rolling(lookback, min_periods=lookback).sum()
    vol = returns.rolling(lookback, min_periods=lookback).std()
    return r / vol.replace(0, np.nan)


def ensemble_signal(returns: pd.Series) -> pd.Series:
    """
    Equal-weight ensemble of vol-scaled momentum at [20, 40, 60, 120].
    This is the exact signal that passed DSR+PBO gates (EDGE_CONFIRMED).
    """
    signals = [raw_signal(returns, L) for L in LOOKBACKS]
    return sum(w * s for w, s in zip(WEIGHTS, signals, strict=False))


def compute_target_weights(
    close_matrix: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """
    Compute vol-targeted portfolio weights using ensemble TSM signal.

    Per-asset position = ensemble_signal * (target_vol / realized_vol), capped at MAX_LEVERAGE.

    Returns:
        (final_weights_df, vol_scale_series, port_rvol_series)
    """
    # Forward-fill close prices before computing returns — assets have
    # different listing dates (e.g. XAUUSD starts 2023-12) and the parquet
    # covers 2006-2026.  Without ffill, rolling windows see NaN gaps even in
    # the tail where all assets actually have data.
    filled_close = close_matrix.ffill()

    # Only keep rows where ALL assets have data (intersection of trading calendars)
    all_valid = filled_close.notna().all(axis=1)
    filled_close = filled_close[all_valid]

    daily_ret = filled_close.pct_change(1)

    # Step 1: Compute ensemble signal per asset
    signal_df = daily_ret.apply(ensemble_signal)

    # Step 2: Per-asset realized vol (60-day rolling, annualized)
    asset_rvol = daily_ret.rolling(RVOL_WINDOW, min_periods=30).std() * np.sqrt(252)

    # Step 3: Vol-scale factor per asset
    vol_scale = (TARGET_VOL / asset_rvol).clip(0, MAX_LEVERAGE)

    # Step 4: Raw weights = signal * vol_scale, shift(1) for execution lag
    raw_weights = signal_df.shift(1) * vol_scale.shift(1)

    # Step 5: Normalize so sum(|w|) = 1 across assets
    abs_sum = raw_weights.abs().sum(axis=1).replace(0, np.nan)
    final_weights = raw_weights.div(abs_sum, axis=0)

    # Step 6: Portfolio-level realized vol for logging
    combined_raw_ret = (final_weights * daily_ret).sum(axis=1)
    port_rvol = combined_raw_ret.rolling(RVOL_WINDOW, min_periods=10).std() * np.sqrt(252)

    # Use mean vol_scale across assets for the scalar return
    mean_vol_scale = vol_scale.mean(axis=1)

    return final_weights, mean_vol_scale, port_rvol


# ═══════════════════════════════════════════════════════════════
# POSITION SIZING
# ═══════════════════════════════════════════════════════════════


def weights_to_lots(
    weights: dict[str, float],
    prices: dict[str, float],
    account_equity: float,
) -> dict[str, dict]:
    """
    Convert portfolio weights to MT5 lot sizes.

    Args:
        weights: {asset_name: weight} where weight is fraction of equity
        prices: {asset_name: latest_price}
        account_equity: MT5 account equity in USD

    Returns:
        {asset_name: {"target_lots": float, "notional": float, "mt5_symbol": str}}
    """
    positions = {}
    for asset, weight in weights.items():
        if abs(weight) < 1e-6 or asset not in prices:
            continue

        mt5_sym = MT5_SYMBOL_MAP.get(asset)
        if not mt5_sym:
            continue

        price = prices[asset]
        contract_size = CONTRACT_SIZES.get(mt5_sym, 100_000)

        # Target notional in USD
        target_notional = weight * account_equity

        # Convert to lots
        target_lots = target_notional / (price * contract_size)
        target_lots = round(max(abs(target_lots), 0) * 100) / 100  # round to 0.01
        if target_lots < MIN_LOT:
            target_lots = 0.0

        # Preserve sign for direction
        if weight < 0:
            target_lots = -target_lots

        positions[asset] = {
            "target_lots": target_lots,
            "notional": target_notional,
            "mt5_symbol": mt5_sym,
            "price": price,
            "weight": weight,
        }

    return positions


# ═══════════════════════════════════════════════════════════════
# MT5 CONNECTION & EXECUTION
# ═══════════════════════════════════════════════════════════════

_mt5_initialized = False
_oms: OMS | None = None


def ensure_mt5():
    """Initialize MT5 connection via OMS adapter, verify demo account."""
    global _mt5_initialized, _oms
    import MetaTrader5 as mt5

    if not _mt5_initialized:
        login = int(os.getenv("MT5_LOGIN", "0"))
        password = os.getenv("MT5_PASSWORD", "")
        server = os.getenv("MT5_SERVER", "Pepperstone-Demo")

        initialized = mt5.initialize(login=login, password=password, server=server)
        if not initialized:
            error = mt5.last_error()
            raise RuntimeError(f"MT5 init failed: {error}")

        account_info = mt5.account_info()
        if account_info is None:
            raise RuntimeError("Cannot read MT5 account info")

        server_lower = account_info.server.lower()
        if "demo" not in server_lower and "practice" not in server_lower:
            raise RuntimeError(
                f"LIVE ACCOUNT DETECTED: {account_info.server} "
                f"(login={account_info.login}). TSM bot requires demo server."
            )

        # Initialize OMS with MT5 adapter + risk gate
        mt5_adapter = MT5Adapter(login=login, password=password, server=server)
        mt5_adapter.connect()

        from quant_os.risk.kill_switch import KillSwitch

        ks = KillSwitch(str(BASE / "data" / "kill_switch_state.json"))
        risk_gate = PreTradeRiskGate(kill_switch=ks)

        _oms = OMS(
            adapters={"mt5": mt5_adapter},
            risk_engine=risk_gate,
        )

        _mt5_initialized = True
        log(f"MT5 initialized — {account_info.server} | Equity: ${account_info.equity:,.2f}")
    return mt5


def get_oms() -> OMS:
    """Return the initialized OMS instance."""
    if _oms is None:
        raise RuntimeError("OMS not initialized — call ensure_mt5() first")
    return _oms


def get_account_equity(mt5) -> float:
    """Get current account equity from MT5."""
    info = mt5.account_info()
    if info is None:
        raise RuntimeError("Cannot read MT5 account info")
    return info.equity


def get_current_positions(mt5) -> dict[str, dict]:
    """Get all open positions, keyed by MT5 symbol."""
    positions = {}
    for pos in mt5.positions_get():
        sym = pos.symbol
        if sym not in positions:
            positions[sym] = {"lots": 0.0, "tickets": [], "avg_price": 0.0}
        direction = 1 if pos.type == 0 else -1  # 0=BUY, 1=SELL
        positions[sym]["lots"] += direction * pos.volume
        positions[sym]["tickets"].append(pos.ticket)
        positions[sym]["avg_price"] = pos.price_open
    return positions


def get_latest_price(mt5, symbol: str) -> float | None:
    """Get latest price for a symbol from MT5."""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return None
    return (tick.bid + tick.ask) / 2.0


def close_position(mt5, ticket: int, symbol: str, volume: float, comment: str) -> bool:
    """Close an existing position by ticket via OMS risk gate."""
    oms = get_oms()
    asset_class = symbol_to_asset_class(symbol)
    order = oms.close_position(
        symbol=symbol,
        broker_position_id=str(ticket),
        volume=volume,
        asset_class=asset_class,
        signal_id=f"tsm-close-{ticket}",
    )
    if order.status.value == "FILLED":
        log(f"✅ CLOSED {symbol} ticket={ticket} vol={volume}")
        return True
    else:
        log(f"❌ CLOSE FAILED {symbol} ticket={ticket}: {order.status.value}")
        return False


def place_order(mt5, symbol: str, lots: float, comment: str = "TSM") -> dict | None:
    """Place a market order via OMS risk gate (positive lots=buy, negative=sell)."""
    oms = get_oms()
    side = "BUY" if lots > 0 else "SELL"
    quantity = abs(lots)
    asset_class = symbol_to_asset_class(symbol)

    order = oms.submit_order(
        signal_id=f"tsm-{symbol}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        symbol=symbol,
        asset_class=asset_class,
        side=side,
        quantity=quantity,
        trace_id=comment,
    )

    if order.status.value == "FILLED":
        direction = "BUY" if lots > 0 else "SELL"
        log(f"✅ {direction} {symbol} vol={quantity:.2f} ticket={order.broker_order_id}")
        return {"ticket": order.broker_order_id, "symbol": symbol, "lots": lots, "price": 0.0}
    elif order.status.value == "REJECTED":
        log(f"❌ ORDER REJECTED {symbol} vol={quantity:.2f}: risk gate")
        return None
    else:
        log(f"❌ ORDER FAILED {symbol} vol={quantity:.2f}: {order.status.value}")
        return None


# ═══════════════════════════════════════════════════════════════
# REBALANCE LOGIC
# ═══════════════════════════════════════════════════════════════


def compute_orders(
    target_positions: dict[str, dict],
    current_positions: dict[str, dict],
) -> list[dict]:
    """
    Compare target vs current positions, generate orders to rebalance.

    Returns list of order dicts:
        {"action": "close"|"open"|"adjust", "symbol": str, "lots": float, ...}
    """
    orders = []

    # Build current lots map (MT5 symbol → net lots)
    current_lots = {}
    for mt5_sym, pos_info in current_positions.items():
        current_lots[mt5_sym] = pos_info["lots"]

    # Build target lots map (MT5 symbol → target lots)
    target_lots = {}
    for asset, tpos in target_positions.items():
        mt5_sym = tpos["mt5_symbol"]
        target_lots[mt5_sym] = tpos["target_lots"]

    all_symbols = set(list(current_lots.keys()) + list(target_lots.keys()))

    for mt5_sym in all_symbols:
        cur = current_lots.get(mt5_sym, 0.0)
        tgt = target_lots.get(mt5_sym, 0.0)
        delta = tgt - cur

        if abs(delta) < MIN_LOT:
            continue  # No change needed

        if abs(cur) > 0 and abs(tgt) < MIN_LOT:
            # Close entire position
            orders.append(
                {
                    "action": "close",
                    "symbol": mt5_sym,
                    "lots": -cur,  # close direction opposite to current
                    "current_lots": cur,
                    "target_lots": 0.0,
                }
            )
        elif abs(cur) < MIN_LOT and abs(tgt) >= MIN_LOT:
            # Open new position
            orders.append(
                {
                    "action": "open",
                    "symbol": mt5_sym,
                    "lots": tgt,
                    "current_lots": 0.0,
                    "target_lots": tgt,
                }
            )
        else:
            # Adjust existing position
            orders.append(
                {
                    "action": "adjust",
                    "symbol": mt5_sym,
                    "lots": delta,
                    "current_lots": cur,
                    "target_lots": tgt,
                }
            )

    return orders


def execute_orders(mt5, orders: list[dict]) -> list[dict]:
    """Execute a list of orders via MT5. Returns fill results."""
    fills = []
    for order in orders:
        sym = order["symbol"]
        lots = order["lots"]
        action = order["action"]

        if action == "close":
            # Close existing positions for this symbol
            positions = mt5.positions_get(symbol=sym)
            if positions:
                for pos in positions:
                    ok = close_position(mt5, pos.ticket, sym, pos.volume, f"TSM close {action}")
                    fills.append(
                        {
                            "symbol": sym,
                            "action": "close",
                            "lots": pos.volume,
                            "success": ok,
                            "ticket": pos.ticket,
                        }
                    )
            else:
                log(f"⚠️ No open position to close for {sym}")

        elif action in ("open", "adjust"):
            result = place_order(mt5, sym, lots, f"TSM {action}")
            fills.append(
                {
                    "symbol": sym,
                    "action": action,
                    "lots": lots,
                    "success": result is not None,
                    "ticket": result["ticket"] if result else None,
                    "price": result["price"] if result else None,
                }
            )

    return fills


# ═══════════════════════════════════════════════════════════════
# LOGGING & STATE
# ═══════════════════════════════════════════════════════════════


def init_csv_log():
    """Create CSV log file with headers if it doesn't exist."""
    TRADE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not CSV_LOG_PATH.exists():
        with open(CSV_LOG_PATH, "w", newline="") as f:
            csv.writer(f).writerow(CSV_HEADERS)


def log_to_csv(rows: list[dict]):
    """Append rows to the trade log CSV."""
    init_csv_log()
    with open(CSV_LOG_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        for row in rows:
            writer.writerow(row)


def save_state(
    weights: dict[str, float],
    signals: dict[str, float],
    vol_scale: float,
    port_rvol: float,
    prices: dict[str, float],
    positions: dict[str, dict],
    fills: list[dict] | None = None,
):
    """Save daily portfolio state to JSON."""
    TRADE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    state = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "config": {
            "target_vol": TARGET_VOL,
            "lookbacks": LOOKBACKS,
            "weights": WEIGHTS,
            "max_leverage": MAX_LEVERAGE,
            "rvol_window": RVOL_WINDOW,
            "assets": ASSETS,
            "cost_map": COST_MAP,
        },
        "signals": signals,
        "weights": {k: round(v, 6) for k, v in weights.items()},
        "vol_scale": round(vol_scale, 6),
        "portfolio_rvol_ann": round(port_rvol, 6),
        "prices": {k: round(v, 5) for k, v in prices.items()},
        "positions": positions,
        "fills": fills or [],
    }
    STATE_PATH.write_text(json.dumps(state, indent=2, default=str))
    log(f"State saved: {STATE_PATH}")


def update_heartbeat(
    portfolio_status: str = "ok",
    last_signal: dict | None = None,
    equity: float = 0.0,
    weights: dict[str, float] | None = None,
):
    """Write structured heartbeat JSON with portfolio context.

    Fields:
      - timestamp_utc: ISO-8601 UTC timestamp
      - portfolio_status: "ok" | "degraded" | "halted"
      - last_signal: dict of latest signal info per asset
      - equity: current account equity (0 if dry-run)
      - weights: current portfolio weights
      - kill_switch_active: whether kill switch is currently active
    """
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)

    kill_switch_active = False
    try:
        from quant_os.risk.kill_switch import KillSwitch

        ks = KillSwitch(str(BASE / "data" / "kill_switch_state.json"))
        kill_switch_active = ks.is_active()
    except Exception:
        pass

    heartbeat = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "portfolio_status": portfolio_status,
        "last_signal": last_signal or {},
        "equity": equity,
        "weights": {k: round(v, 6) for k, v in (weights or {}).items()},
        "kill_switch_active": kill_switch_active,
    }
    HEARTBEAT_PATH.write_text(json.dumps(heartbeat, indent=2, default=str))


# ═══════════════════════════════════════════════════════════════
# MAIN REBALANCE
# ═══════════════════════════════════════════════════════════════


def run_rebalance(live: bool = False, force: bool = False):
    """
    Main rebalance routine.

    1. Load data & compute TSM signals
    2. Compute vol-targeted weights
    3. Convert to lot sizes
    4. Compare with current positions
    5. Generate & execute orders (if live)
    6. Log everything
    """
    log("=" * 60)
    log(f"TSM Paper Trade Bot — {'LIVE' if live else 'DRY-RUN'}")
    log("=" * 60)

    # ── Step 1: Load data ──
    data = load_data()
    close_matrix = get_close_matrix(data)
    log(f"Data: {len(data)} rows, {data.index.min().date()} → {data.index.max().date()}")
    log(f"Assets: {list(close_matrix.columns)}")

    # ── Step 2: Compute signals & weights ──
    final_weights, vol_scale, port_rvol = compute_target_weights(close_matrix)

    # Get latest complete row (all assets have data)
    complete_mask = final_weights.notna().all(axis=1)
    if not complete_mask.any():
        log("❌ No complete weight rows — check data coverage")
        return
    latest_weights = final_weights[complete_mask].iloc[-1].to_dict()
    latest_vol_scale = float(vol_scale[complete_mask].dropna().iloc[-1])
    latest_rvol = float(port_rvol[complete_mask].dropna().iloc[-1])

    # Compute ensemble signal values for logging (same ffill logic as compute_target_weights)
    _filled = close_matrix.ffill()
    _all_valid = _filled.notna().all(axis=1)
    daily_ret = _filled[_all_valid].pct_change(1)
    signals = {}
    for asset in close_matrix.columns:
        ret = daily_ret[asset]
        sig_vals = [raw_signal(ret, L).dropna() for L in LOOKBACKS]
        if all(not s.empty for s in sig_vals):
            ens = ensemble_signal(ret)
            signals[asset] = {
                "ensemble": float(ens.iloc[-1]),
                "per_lookback": {L: float(s.iloc[-1]) for L, s in zip(LOOKBACKS, sig_vals, strict=False)},
                "weight": float(latest_weights.get(asset, 0.0)),
            }

    # Compute portfolio drawdown for logging
    combined_ret_series = (final_weights * daily_ret).sum(axis=1).dropna()
    if len(combined_ret_series) > 0:
        cumulative = (1 + combined_ret_series).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max
        latest_drawdown = float(drawdown.iloc[-1])
    else:
        latest_drawdown = 0.0

    log("\n--- Portfolio State ---")
    log(f"  Vol scale (mean): {latest_vol_scale:.4f}")
    log(f"  Realized vol (ann): {latest_rvol:.4f}")
    log(f"  Target vol: {TARGET_VOL:.4f}")
    log(f"  Drawdown: {latest_drawdown:.4%}")

    log("\n--- Ensemble Signal & Weights ---")
    log(f"  Lookbacks: {LOOKBACKS}")
    log(f"  Weights:   {WEIGHTS}")
    for asset, sig_info in signals.items():
        w = sig_info["weight"]
        ens = sig_info["ensemble"]
        lbs = " ".join(f"L{L}={sig_info['per_lookback'][L]:+.3f}" for L in LOOKBACKS)
        log(f"  {asset:12s}  ensemble={ens:+.4f}  [{lbs}]  weight={w:+.4f}")

    # ── Step 3: Get prices ──
    prices = {}
    account_equity = 100_000.0  # Default for dry-run

    if live:
        mt5 = ensure_mt5()
        account_equity = get_account_equity(mt5)
        # Get prices from MT5
        for asset in ASSETS:
            mt5_sym = MT5_SYMBOL_MAP.get(asset)
            if mt5_sym:
                p = get_latest_price(mt5, mt5_sym)
                if p:
                    prices[asset] = p
        # Fallback to yfinance for missing prices
        missing = [a for a in ASSETS if a not in prices]
        if missing:
            log(f"Fetching {len(missing)} prices from yfinance fallback...")
            prices.update(fetch_live_prices(missing))
    else:
        # Dry-run: use last close from parquet
        for asset in close_matrix.columns:
            last_close = close_matrix[asset].dropna().iloc[-1]
            prices[asset] = float(last_close)

    log(f"\nAccount equity: ${account_equity:,.2f}")

    # ── Step 4: Convert weights to lots ──
    target_positions = weights_to_lots(latest_weights, prices, account_equity)

    log("\n--- Target Positions ---")
    for asset, tpos in target_positions.items():
        direction = "LONG" if tpos["target_lots"] > 0 else "SHORT" if tpos["target_lots"] < 0 else "FLAT"
        mt5_sym = tpos["mt5_symbol"]
        cost_bps = COST_MAP.get(mt5_sym, 10.0)
        log(
            f"  {tpos['mt5_symbol']:10s}  {direction:6s}  lots={tpos['target_lots']:+.2f}  "
            f"weight={tpos['weight']:+.4f}  notional=${tpos['notional']:,.0f}  cost={cost_bps:.1f}bps"
        )

    # ── Step 5: Generate orders ──
    current_positions = {}
    fills = []

    if live:
        current_positions = get_current_positions(mt5)
        log("\n--- Current Positions ---")
        if current_positions:
            for sym, pos in current_positions.items():
                log(f"  {sym:10s}  lots={pos['lots']:+.2f}  tickets={pos['tickets']}")
        else:
            log("  (none)")

        # ── Auto-stop drawdown check ──
        if not check_auto_stop(account_equity):
            log("🛑 AUTO-STOP ACTIVE — closing all positions")
            # Close all open positions
            if current_positions:
                close_orders = []
                for sym, pos in current_positions.items():
                    close_orders.append(
                        {
                            "action": "close",
                            "symbol": sym,
                            "lots": -pos["lots"],
                            "current_lots": pos["lots"],
                            "target_lots": 0.0,
                        }
                    )
                if close_orders:
                    fills = execute_orders(mt5, close_orders)
                    ok_count = sum(1 for f in fills if f.get("success"))
                    log(f"🛑 Auto-stop close: {ok_count}/{len(fills)} positions closed")
                    tg(f"🛑 *TSM Bot*: Auto-stop closed {ok_count}/{len(fills)} positions")
            log("⛔ Rebalance skipped — auto-stop active, manual reset required")
            return

        orders = compute_orders(target_positions, current_positions)
        log(f"\n--- Orders ({len(orders)}) ---")
        for order in orders:
            log(f"  {order['action']:8s}  {order['symbol']:10s}  lots={order['lots']:+.2f}")

        if orders:
            # Kill switch check before execution
            if not check_kill_switch():
                log("⛔ Rebalance skipped — kill switch active")
            else:
                fills = execute_orders(mt5, orders)
                ok_count = sum(1 for f in fills if f.get("success"))
                log(f"\n--- Fills: {ok_count}/{len(fills)} successful ---")
                for fill in fills:
                    status = "✅" if fill.get("success") else "❌"
                    log(f"  {status} {fill['action']:8s} {fill['symbol']:10s} lots={fill['lots']:+.2f}")

                tg(
                    f"📊 *TSM Rebalance Complete*\n"
                    f"Orders: {len(orders)} | Fills: {ok_count}/{len(fills)}\n"
                    f"Vol scale: {latest_vol_scale:.3f} | RVol: {latest_rvol:.1%}\n"
                    f"Drawdown: {latest_drawdown:.2%}\n"
                    f"Equity: ${account_equity:,.2f}"
                )
    else:
        log("\n--- DRY-RUN: No orders placed ---")
        orders = compute_orders(target_positions, current_positions)
        if orders:
            log(f"  Would execute {len(orders)} orders:")
            for order in orders:
                log(f"    {order['action']:8s}  {order['symbol']:10s}  lots={order['lots']:+.2f}")
        else:
            log("  No rebalance needed")

    # ── Step 6: Log everything ──
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
    csv_rows = []
    for asset, tpos in target_positions.items():
        sig_info = signals.get(asset, {})
        mt5_sym = tpos["mt5_symbol"]
        cost_bps = COST_MAP.get(mt5_sym, 10.0)
        ens_val = sig_info.get("ensemble", 0.0)
        csv_rows.append(
            {
                "timestamp": ts,
                "asset": asset,
                "mt5_symbol": mt5_sym,
                "signal": f"{ens_val:+.4f}",
                "weight": f"{tpos['weight']:+.6f}",
                "vol_scale": f"{latest_vol_scale:.4f}",
                "target_lots": f"{tpos['target_lots']:+.2f}",
                "order_type": "target",
                "lot_size": f"{tpos['target_lots']:+.2f}",
                "price": f"{tpos['price']:.5f}",
                "status": "dry_run" if not live else "target",
                "notes": f"ensemble={ens_val:+.4f} cost={cost_bps:.1f}bps",
            }
        )

    # Log fills
    for fill in fills:
        csv_rows.append(
            {
                "timestamp": ts,
                "asset": fill["symbol"],
                "mt5_symbol": fill["symbol"],
                "signal": "",
                "weight": "",
                "vol_scale": f"{latest_vol_scale:.4f}",
                "target_lots": "",
                "order_type": fill["action"],
                "lot_size": f"{fill['lots']:+.2f}",
                "price": f"{fill.get('price', 0):.5f}" if fill.get("price") else "",
                "status": "filled" if fill.get("success") else "failed",
                "notes": f"ticket={fill.get('ticket', '')}",
            }
        )

    log_to_csv(csv_rows)

    # Save state
    save_state(
        weights=latest_weights,
        signals={k: v.get("ensemble", 0) for k, v in signals.items()},
        vol_scale=latest_vol_scale,
        port_rvol=latest_rvol,
        prices=prices,
        positions={k: v for k, v in current_positions.items()} if live else {},
        fills=fills,
    )

    update_heartbeat(
        portfolio_status="ok",
        last_signal={k: v.get("ensemble", 0) for k, v in signals.items()},
        equity=account_equity,
        weights=latest_weights,
    )
    log(f"\n✅ Rebalance complete ({'LIVE' if live else 'DRY-RUN'})")


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="TSM Paper Trade Bot — Multi-Asset Portfolio Rebalance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/tsm_paper_trade.py --dry-run          # Test without MT5
  python scripts/tsm_paper_trade.py --live              # Execute on demo
  python scripts/tsm_paper_trade.py --live --force      # Force rebalance any day
        """,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Compute signals & log, no orders")
    group.add_argument("--live", action="store_true", help="Connect to MT5 & execute orders")
    parser.add_argument("--force", action="store_true", help="Force rebalance (skip day-of-week check)")
    args = parser.parse_args()

    # Day-of-week check: only rebalance on Friday unless --force
    now = datetime.now(UTC)
    if not args.force and now.weekday() != 4:  # 4 = Friday
        log(f"Today is {now.strftime('%A')} — rebalance only on Friday. Use --force to override.")
        return

    run_rebalance(live=args.live, force=args.force)


if __name__ == "__main__":
    main()
