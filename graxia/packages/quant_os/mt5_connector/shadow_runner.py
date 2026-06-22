"""
Shadow Mode Runner — collect live MT5 data, run full pipeline, submit NO orders.

Usage:
    cd quant_os
    python mt5_connector/shadow_runner.py [--symbol XAUUSD] [--bars 100] [--interval 60]
"""
import sys
import os
import time
import yaml
import logging
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from mt5_connector.connection import MT5Connection
from shadow.pipeline import ShadowPipeline, ShadowSignal, ShadowSignalOutcome
from shadow.failure_rules import FailureRuleChecker
from shadow.telemetry import ShadowTelemetry

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


class ShadowRunner:
    """Collect live MT5 data through full pipeline, never submit orders."""

    def __init__(self, config_path: str = 'mt5_connector/config.yaml'):
        with open(config_path) as f:
            self._config = yaml.safe_load(f)

        self._mt5 = MT5Connection()
        self._pipeline = ShadowPipeline()
        self._failure_checker = FailureRuleChecker()
        self._telemetry = ShadowTelemetry()

        self._running = False
        self._signal_count = 0
        self._session_id = f"shadow_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    def connect(self) -> bool:
        cfg = self._config['mt5']
        ok = self._mt5.connect(path=cfg.get('path'), timeout=cfg.get('timeout', 10000))
        if ok:
            info = self._mt5.get_account_info()
            logger.info(f"Connected: {info.login}@{info.server} Balance={info.balance}")
        else:
            logger.error("MT5 connection failed")
        return ok

    def disconnect(self):
        self._mt5.disconnect()
        logger.info("Disconnected")

    def _collect_tick(self, symbol: str) -> Optional[dict]:
        tick = self._mt5.get_tick(symbol)
        return tick

    def _evaluate_signal(self, symbol: str, tick: dict, bars: list) -> ShadowSignal:
        self._signal_count += 1
        signal_id = f"SIG-{self._signal_count:06d}"

        # Simple strategy: compare last 2 bar closes
        if len(bars) < 2:
            return ShadowSignal(
                signal_id=signal_id, timestamp=datetime.utcnow(),
                symbol=symbol, direction="BUY", entry_price=tick['ask'],
                stop_loss=0, take_profit=None, outcome=ShadowSignalOutcome.REJECTED_DATA_STALE,
                rejection_reason="INSUFFICIENT_BARS",
            )

        prev_close = bars[-2]['close']
        curr_close = bars[-1]['close']
        spread = tick['ask'] - tick['bid']

        if curr_close > prev_close:
            direction = "BUY"
            entry = tick['ask']
            sl = entry - spread * 10
            tp = entry + spread * 20
        elif curr_close < prev_close:
            direction = "SELL"
            entry = tick['bid']
            sl = entry + spread * 10
            tp = entry - spread * 20
        else:
            return ShadowSignal(
                signal_id=signal_id, timestamp=datetime.utcnow(),
                symbol=symbol, direction="BUY", entry_price=tick['ask'],
                stop_loss=0, take_profit=None, outcome=ShadowSignalOutcome.REJECTED_DATA_STALE,
                rejection_reason="NO_DIRECTION",
            )

        return ShadowSignal(
            signal_id=signal_id, timestamp=datetime.utcnow(),
            symbol=symbol, direction=direction,
            entry_price=entry, stop_loss=sl, take_profit=tp,
            outcome=ShadowSignalOutcome.ACCEPTED,
            event_risk_state="CLEAR",
            market_health_state="HEALTHY",
            sized_volume=0.01,
            hypothetical_fill_price=entry,
            hypothetical_spread_cost=float(spread),
            hypothetical_slippage_cost=float(spread * 0.5),
        )

    def run_cycle(self, symbol: str, bar_count: int = 100) -> dict:
        tick = self._collect_tick(symbol)
        if tick is None:
            return {"error": "NO_TICK"}

        bars = self._mt5.get_bars(symbol, 60, bar_count)

        signal = self._evaluate_signal(symbol, tick, bars)

        self._telemetry.record_signal_created(self._session_id, signal.signal_id)

        result = self._pipeline.process_signal(signal)

        if result.outcome == ShadowSignalOutcome.ACCEPTED:
            self._telemetry.record_signal_accepted(self._session_id, signal.signal_id)
        else:
            self._telemetry.record_signal_rejected(
                self._session_id, signal.signal_id, result.rejection_reason
            )

        return {
            "signal_id": signal.signal_id,
            "direction": signal.direction,
            "entry": signal.entry_price,
            "sl": signal.stop_loss,
            "tp": signal.take_profit,
            "outcome": result.outcome.value,
            "bid": tick['bid'],
            "ask": tick['ask'],
            "spread": tick['ask'] - tick['bid'],
        }

    def run(self, symbol: str = 'XAUUSD', duration_seconds: int = 300, interval_seconds: int = 60):
        if not self.connect():
            return

        self._running = True
        self._telemetry.start(self._session_id)
        self._pipeline.start_session(self._session_id)

        logger.info(f"Shadow mode started: {self._session_id}")
        logger.info(f"Symbol: {symbol}, Duration: {duration_seconds}s, Interval: {interval_seconds}s")
        logger.info("NO ORDERS WILL BE SUBMITTED")

        start = time.time()
        cycle = 0

        while self._running and (time.time() - start) < duration_seconds:
            cycle += 1
            elapsed = time.time() - start
            remaining = duration_seconds - elapsed

            logger.info(f"--- Cycle {cycle} ({elapsed:.0f}s / {duration_seconds}s) ---")

            try:
                result = self.run_cycle(symbol)
                logger.info(f"Result: {result.get('outcome', 'ERROR')} | {result.get('direction', '-')} | {result.get('entry', '-')}")
            except Exception as e:
                logger.error(f"Cycle error: {e}")
                self._telemetry.record_pipeline_error(self._session_id, str(e))

            if remaining > interval_seconds:
                time.sleep(interval_seconds)
            else:
                break

        self._pipeline.end_session()
        self._running = False

        summary = self._telemetry.get_summary(self._session_id)
        logger.info(f"\n=== Shadow Session Complete ===")
        logger.info(f"Signals: {summary.signals_created} | Accepted: {summary.signals_accepted} | Rejected: {summary.signals_rejected}")
        logger.info(f"Errors: {summary.pipeline_errors}")

        self._export_results()
        self.disconnect()

    def _export_results(self):
        os.makedirs('shadow_results', exist_ok=True)
        ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')

        telemetry_path = f'shadow_results/telemetry_{ts}.json'
        with open(telemetry_path, 'w') as f:
            f.write(self._telemetry.export_json(self._session_id))
        logger.info(f"Telemetry saved: {telemetry_path}")

        session = self._pipeline.get_session(self._session_id)
        if session:
            session_path = f'shadow_results/session_{ts}.json'
            with open(session_path, 'w') as f:
                f.write(session.export())
            logger.info(f"Session saved: {session_path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Shadow Mode Runner')
    parser.add_argument('--symbol', default='XAUUSD', help='Symbol to trade')
    parser.add_argument('--bars', type=int, default=100, help='Bar count for analysis')
    parser.add_argument('--interval', type=int, default=60, help='Seconds between cycles')
    parser.add_argument('--duration', type=int, default=300, help='Total duration in seconds')
    args = parser.parse_args()

    runner = ShadowRunner()
    runner.run(
        symbol=args.symbol,
        duration_seconds=args.duration,
        interval_seconds=args.interval,
    )


if __name__ == '__main__':
    main()
