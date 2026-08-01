"""
Live Trading Runner — Multi-strategy ML trading via MT5.

Integrates MLB (ML Breakout) + MLMR (ML Mean Reversion) strategies
with regime filtering and risk management.

Usage:
  python live_runner.py                    # Run once (check signals)
  python live_runner.py --loop             # Run continuously (every M15 candle)
  python live_runner.py --paper            # Paper trading mode (no real orders)
  python live_runner.py --symbols XAUUSD,EURUSD  # Specific symbols
  python live_runner.py --status           # Show current state

Requirements:
  - MetaTrader5 package installed
  - MT5 terminal running and logged in
  - Trained models in ml/models/
  - Config in mt5_connector/config.yaml
"""

import argparse
import json
import os
import signal
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import structlog

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graxia.packages.quant_os.strategies.mlb import MLBreakout
from graxia.packages.quant_os.strategies.mlmr import MLMeanReversion

logger = structlog.get_logger(__name__)

# ─── Config ─────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "mt5_connector" / "config.yaml"
STATE_PATH = BASE / "state" / "live_runner_state.json"
TRADE_LOG_PATH = BASE / "reports" / "live_trades.json"

# Default symbols
DEFAULT_SYMBOLS = ["XAUUSD", "EURUSD", "US30", "NAS100", "BTCUSD"]

# Graceful shutdown
_shutdown = False


def _signal_handler(signum, frame):
    global _shutdown
    _shutdown = True
    logger.info("shutdown_requested", signal=signum)


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


# ─── MT5 Connection ─────────────────────────────────────────────
class MT5Client:
    """Wrapper for MT5 connection and data fetching."""

    def __init__(self, config: dict[str, Any] | None = None):
        self._mt5 = None
        self._connected = False
        self._config = config or {}

    def connect(self) -> bool:
        """Connect to MT5 terminal."""
        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5

            path = self._config.get("path", "")
            timeout = self._config.get("timeout", 30000)

            if path:
                ok = mt5.initialize(path=path, timeout=timeout)
            else:
                ok = mt5.initialize(timeout=timeout)

            if not ok:
                logger.error("mt5.init_failed", error=mt5.last_error())
                return False

            acct = mt5.account_info()
            if acct:
                logger.info(
                    "mt5.connected",
                    login=acct.login,
                    server=acct.server,
                    balance=acct.balance,
                    leverage=acct.leverage,
                )

            self._connected = True
            return True

        except ImportError:
            logger.error("mt5.package_missing")
            return False
        except Exception as e:
            logger.error("mt5.connect_error", error=str(e))
            return False

    def disconnect(self):
        if self._mt5 and self._connected:
            self._mt5.shutdown()
            self._connected = False

    def get_account_info(self) -> dict[str, Any] | None:
        if not self._connected:
            return None
        acct = self._mt5.account_info()
        if acct is None:
            return None
        return {
            "login": acct.login,
            "balance": acct.balance,
            "equity": acct.equity,
            "margin": acct.margin,
            "free_margin": acct.free_margin,
            "leverage": acct.leverage,
            "currency": acct.currency,
        }

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: int = 16385,  # MT5.TIMEFRAME_M15
        n_bars: int = 300,
    ) -> dict[str, list] | None:
        """Fetch OHLCV data from MT5."""
        if not self._connected:
            return None

        try:
            rates = self._mt5.copy_rates_from_pos(symbol, timeframe, 0, n_bars)
            if rates is None or len(rates) == 0:
                logger.warning("mt5.no_data", symbol=symbol)
                return None

            return {
                "time": [r[0] for r in rates],
                "open": [r[1] for r in rates],
                "high": [r[2] for r in rates],
                "low": [r[3] for r in rates],
                "close": [r[4] for r in rates],
                "volume": [r[5] for r in rates],
            }
        except Exception as e:
            logger.error("mt5.data_error", symbol=symbol, error=str(e))
            return None

    def get_positions(self) -> list[dict[str, Any]]:
        """Get open positions."""
        if not self._connected:
            return []

        try:
            positions = self._mt5.positions_get()
            if positions is None:
                return []

            return [
                {
                    "ticket": p.ticket,
                    "symbol": p.symbol,
                    "type": p.type,  # 0=buy, 1=sell
                    "volume": p.volume,
                    "price_open": p.price_open,
                    "price_current": p.price_current,
                    "sl": p.sl,
                    "tp": p.tp,
                    "profit": p.profit,
                    "magic": p.magic,
                    "comment": p.comment,
                }
                for p in positions
            ]
        except Exception as e:
            logger.error("mt5.positions_error", error=str(e))
            return []

    def send_order(
        self,
        symbol: str,
        order_type: str,  # "buy" or "sell"
        volume: float,
        sl: float = 0.0,
        tp: float = 0.0,
        comment: str = "",
        magic: int = 20260712,
    ) -> dict[str, Any] | None:
        """Send market order to MT5."""
        if not self._connected:
            return None

        try:
            # Get symbol info for filling mode
            info = self._mt5.symbol_info(symbol)
            if info is None:
                logger.error("mt5.symbol_not_found", symbol=symbol)
                return None

            # Ensure symbol is visible
            if not info.visible:
                self._mt5.symbol_select(symbol, True)

            # Get current price
            tick = self._mt5.symbol_info_tick(symbol)
            if tick is None:
                logger.error("mt5.no_tick", symbol=symbol)
                return None

            price = tick.ask if order_type == "buy" else tick.bid

            # Determine filling type
            filling = self._mt5.ORDER_FILLING_IOC
            if info.filling_mode & 1:  # FOK
                filling = self._mt5.ORDER_FILLING_FOK

            request = {
                "action": self._mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": self._mt5.ORDER_TYPE_BUY if order_type == "buy" else self._mt5.ORDER_TYPE_SELL,
                "price": price,
                "sl": sl,
                "tp": tp,
                "deviation": 20,
                "magic": magic,
                "comment": comment,
                "type_time": self._mt5.ORDER_TIME_GTC,
                "type_filling": filling,
            }

            result = self._mt5.order_send(request)
            if result is None:
                logger.error("mt5.order_send_none", symbol=symbol)
                return None

            if result.retcode != self._mt5.TRADE_RETCODE_DONE:
                logger.error(
                    "mt5.order_failed",
                    symbol=symbol,
                    retcode=result.retcode,
                    comment=result.comment,
                )
                return None

            logger.info(
                "mt5.order_placed",
                symbol=symbol,
                type=order_type,
                volume=volume,
                price=result.price,
                ticket=result.order,
                sl=sl,
                tp=tp,
            )

            return {
                "ticket": result.order,
                "price": result.price,
                "volume": result.volume,
                "retcode": result.retcode,
            }

        except Exception as e:
            logger.error("mt5.order_error", symbol=symbol, error=str(e))
            return None


# ─── State Management ───────────────────────────────────────────
class RunnerState:
    """Persistent state for the live runner."""

    def __init__(self, path: Path = STATE_PATH):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        if self._path.exists():
            try:
                with open(self._path) as f:
                    return json.load(f)
            except Exception:
                # ponytail: was bare pass, now logged
                logger.debug("exception_suppressed", exc_info=True)
        return {
            "last_run": None,
            "trades_today": 0,
            "open_positions": {},
            "daily_pnl": 0.0,
            "trade_count": 0,
        }

    def save(self):
        with open(self._path, "w") as f:
            json.dump(self._state, f, indent=2, default=str)

    @property
    def last_run(self) -> str | None:
        return self._state.get("last_run")

    @property
    def trades_today(self) -> int:
        return self._state.get("trades_today", 0)

    def record_trade(self, trade: dict[str, Any]):
        self._state["trades_today"] = self._state.get("trades_today", 0) + 1
        self._state["trade_count"] = self._state.get("trade_count", 0) + 1
        self._state["last_run"] = datetime.now(UTC).isoformat()
        self.save()

    def reset_daily(self):
        self._state["trades_today"] = 0
        self.save()


# ─── Main Runner ────────────────────────────────────────────────
class LiveRunner:
    """Multi-strategy live trading runner."""

    def __init__(
        self,
        symbols: list[str] | None = None,
        paper_mode: bool = True,
        mt5_config: dict[str, Any] | None = None,
    ):
        self.symbols = symbols or DEFAULT_SYMBOLS
        self.paper_mode = paper_mode
        self.mt5 = MT5Client(mt5_config)
        self.state = RunnerState()

        # Initialize strategies
        self.strategies = {
            "MLB": MLBreakout(),
            "MLMR": MLMeanReversion(),
        }

        logger.info(
            "runner.initialized",
            symbols=self.symbols,
            paper_mode=paper_mode,
            strategies=list(self.strategies.keys()),
        )

    def run_once(self) -> list[dict[str, Any]]:
        """Run one cycle: check signals for all symbols."""
        signals = []

        for symbol in self.symbols:
            if _shutdown:
                break

            # Fetch data
            ohlcv = self.mt5.get_ohlcv(symbol, n_bars=300)
            if ohlcv is None:
                continue

            # Run each strategy
            for strat_name, strategy in self.strategies.items():
                try:
                    sig = strategy.generate_signal(
                        symbol=symbol,
                        ohlcv_data=ohlcv,
                    )

                    if sig is not None:
                        signal_info = {
                            "strategy": strat_name,
                            "symbol": symbol,
                            "type": sig.signal_type.value,
                            "confidence": sig.confidence,
                            "entry": float(sig.entry_price) if sig.entry_price else 0,
                            "sl": float(sig.stop_loss) if sig.stop_loss else 0,
                            "tp": float(sig.take_profit) if sig.take_profit else 0,
                            "notes": sig.notes,
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                        signals.append(signal_info)

                        logger.info(
                            "signal.generated",
                            strategy=strat_name,
                            symbol=symbol,
                            type=sig.signal_type.value,
                            confidence=round(sig.confidence, 3),
                        )

                        # Execute if not paper mode
                        if not self.paper_mode:
                            self._execute_signal(signal_info)

                except Exception as e:
                    logger.error(
                        "signal.error",
                        strategy=strat_name,
                        symbol=symbol,
                        error=str(e),
                    )

        return signals

    def _execute_signal(self, sig: dict[str, Any]):
        """Execute a trading signal via MT5."""
        symbol = sig["symbol"]
        order_type = "buy" if sig["type"] == "BUY" else "sell"

        # Position sizing: 1% risk
        acct = self.mt5.get_account_info()
        if acct is None:
            return

        balance = acct["balance"]
        risk_amount = balance * 0.01  # 1% risk

        entry = sig["entry"]
        sl = sig["sl"]
        if entry == 0 or sl == 0:
            return

        risk_per_unit = abs(entry - sl)
        if risk_per_unit == 0:
            return

        # Calculate lot size (simplified)
        volume = round(risk_amount / (risk_per_unit * 100), 2)
        volume = max(0.01, min(volume, 10.0))

        result = self.mt5.send_order(
            symbol=symbol,
            order_type=order_type,
            volume=volume,
            sl=sig["sl"],
            tp=sig["tp"],
            comment=f"{sig['strategy']}_ML",
        )

        if result:
            self.state.record_trade(sig)

    def run_loop(self, interval_seconds: int = 900):
        """Run continuously with given interval."""
        logger.info("runner.loop_started", interval=interval_seconds)

        while not _shutdown:
            try:
                signals = self.run_once()

                if signals:
                    # Save signals to report
                    report_path = BASE / "reports" / "latest_signals.json"
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(report_path, "w") as f:
                        json.dump(signals, f, indent=2)

                # Wait for next cycle
                for _ in range(interval_seconds):
                    if _shutdown:
                        break
                    time.sleep(1)

            except Exception as e:
                logger.error("runner.loop_error", error=str(e))
                time.sleep(60)

        logger.info("runner.loop_stopped")

    def get_status(self) -> dict[str, Any]:
        """Get current runner status."""
        positions = self.mt5.get_positions() if self.mt5._connected else []
        acct = self.mt5.get_account_info() if self.mt5._connected else None

        return {
            "paper_mode": self.paper_mode,
            "symbols": self.symbols,
            "strategies": list(self.strategies.keys()),
            "account": acct,
            "open_positions": len(positions),
            "positions": positions,
            "trades_today": self.state.trades_today,
            "total_trades": self.state._state.get("trade_count", 0),
            "last_run": self.state.last_run,
        }


# ─── CLI ────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Live Trading Runner")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    parser.add_argument("--paper", action="store_true", default=True, help="Paper trading mode")
    parser.add_argument("--live", action="store_true", help="Live trading mode (real orders)")
    parser.add_argument("--symbols", type=str, default=None, help="Comma-separated symbols")
    parser.add_argument("--status", action="store_true", help="Show current status")
    parser.add_argument("--interval", type=int, default=900, help="Loop interval in seconds")
    parser.add_argument("--mt5-path", type=str, default=None, help="Path to MT5 terminal")
    parser.add_argument("--mt5-login", type=int, default=None, help="MT5 login")
    parser.add_argument("--mt5-password", type=str, default=None, help="MT5 password")
    parser.add_argument("--mt5-server", type=str, default=None, help="MT5 server")

    args = parser.parse_args()

    if args.live and not os.environ.get("QUANT_OS_ALLOW_UNVALIDATED_LIVE"):
        raise SystemExit(
            "BLOCKED: live_runner.py --live calls MT5 order_send directly, bypassing the "
            "orchestrator/OMS/KillSwitch/PreTradeRiskGate with unvalidated signal logic "
            "(see reports/incident_unvalidated_scripts_20260717.md). "
            "Set QUANT_OS_ALLOW_UNVALIDATED_LIVE=1 to override, or omit --live for paper mode."
        )

    # Load config
    mt5_config = {}
    if args.mt5_path:
        mt5_config["path"] = args.mt5_path

    # Also try env vars
    mt5_config.setdefault("path", os.getenv("MT5_PATH", ""))
    login = args.mt5_login or os.getenv("MT5_LOGIN")
    password = args.mt5_password or os.getenv("MT5_PASSWORD", "")
    server = args.mt5_server or os.getenv("MT5_SERVER", "")

    symbols = args.symbols.split(",") if args.symbols else DEFAULT_SYMBOLS
    paper_mode = not args.live

    # Connect to MT5
    runner = LiveRunner(
        symbols=symbols,
        paper_mode=paper_mode,
        mt5_config=mt5_config,
    )

    # Try to connect (non-fatal in paper mode)
    if not runner.mt5.connect():
        if not paper_mode:
            logger.error("Cannot connect to MT5 in live mode")
            sys.exit(1)
        else:
            logger.warning("MT5 not connected, running in offline paper mode")

    # Login if credentials provided
    if login and password and runner.mt5._connected:
        try:
            import MetaTrader5 as mt5
            mt5.login(login, password=password, server=server)
        except Exception as e:
            logger.warning("mt5.login_failed", error=str(e))

    if args.status:
        status = runner.get_status()
        print(json.dumps(status, indent=2, default=str))
        return

    if args.loop:
        runner.run_loop(interval_seconds=args.interval)
    else:
        signals = runner.run_once()
        print(json.dumps(signals, indent=2, default=str))

    runner.mt5.disconnect()


if __name__ == "__main__":
    main()
