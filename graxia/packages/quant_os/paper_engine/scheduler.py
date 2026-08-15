"""
Parallel campaign scheduler — runs N campaigns concurrently using ProcessPoolExecutor.
"""

from __future__ import annotations

import multiprocessing
import os
import signal
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .campaign import CampaignConfig
from .engine import CampaignResult, run_campaign
from .result_store import ResultStore

# Disable signal handlers in worker processes
_initialised = False


def _worker_init():
    """Worker process initialisation — ignore SIGINT so parent handles it."""
    global _initialised
    if not _initialised:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        _initialised = True


def _run_single(cfg_dict: dict) -> dict:
    """Wrapper: run_campaign in worker process. Takes dict for pickling."""
    config = CampaignConfig.from_dict(cfg_dict)
    result = run_campaign(config)
    return result.to_dict()


class CampaignScheduler:
    """Run many campaigns in parallel with progress tracking."""

    def __init__(
        self,
        campaigns: list[CampaignConfig],
        workers: int | None = None,
        store_path: str | Path | None = None,
        batch_size: int = 50,
    ):
        self.campaigns = campaigns
        self.workers = workers or max(1, multiprocessing.cpu_count() - 1)
        self.batch_size = batch_size
        self.store = ResultStore(store_path) if store_path else None

        self.results: list[CampaignResult] = []
        self.errors: list[dict] = []
        self._start_time: float = 0.0
        self._completed = 0
        self._total = len(campaigns)

    def run_all(self, progress: bool = True) -> list[CampaignResult]:
        """Run all campaigns in parallel using ProcessPoolExecutor."""
        self._start_time = time.time()
        self._completed = 0
        total = self._total

        if total == 0:
            print("[SCHEDULER] No campaigns to run")
            return []

        print(f"[SCHEDULER] Running {total} campaigns with {self.workers} workers")
        print(f"[SCHEDULER] Estimated: ~{total / self.workers * 0.5:.0f}s per worker batch")

        # Convert to dicts for pickling across processes
        cfg_dicts = [c.to_dict() for c in self.campaigns]

        # Process in batches to avoid memory issues
        for batch_start in range(0, total, self.batch_size):
            batch = cfg_dicts[batch_start: batch_start + self.batch_size]
            self._run_batch(batch, progress)

        elapsed = time.time() - self._start_time
        print(f"\n[SCHEDULER] Done: {self._completed}/{total} campaigns in {elapsed:.0f}s")

        # Save final results
        if self.store:
            self.store.save_batch(self.results)
            summary = self.store.get_ranking()
            rank_path = self.store.save_ranking(summary)
            if rank_path:
                print(f"[SCHEDULER] Ranking saved: {rank_path}")

        return self.results

    def _run_batch(self, cfg_dicts: list[dict], progress: bool) -> None:
        """Run one batch in parallel."""
        batch_size = len(cfg_dicts)
        
        with ProcessPoolExecutor(max_workers=self.workers, initializer=_worker_init) as executor:
            futures = {executor.submit(_run_single, cd): cd["campaign_id"] for cd in cfg_dicts}

            try:
                for future in as_completed(futures):
                    cid = futures[future]
                    try:
                        result_dict = future.result()
                        result = CampaignResult(
                            CampaignConfig.from_dict(result_dict["config"])
                        )
                        # Reconstruct Trade objects from dict
                        from .engine import Trade
                        from .strategies.base import Signal
                        result.trades = []
                        for td in result_dict.get("trades", []):
                            sig = Signal(
                                timestamp=td.get("entry_time", ""),
                                direction=1 if td.get("direction") == "LONG" else -1,
                                confidence=td.get("confidence", 0),
                                entry_price=td.get("entry_price", 0),
                                stop_loss=td.get("stop_loss"),
                                take_profit=td.get("take_profit"),
                                reason=td.get("exit_reason", ""),
                            )
                            t = Trade(
                                signal=sig,
                                capital=100000,
                                risk_pct=1.0,
                                commission_bps=0,
                                slippage_bps=0,
                                symbol=result_dict["config"]["symbol"],
                            )
                            t.entry_price = td.get("entry_price", 0)
                            t.exit_price = td.get("exit_price")
                            t.exit_time = td.get("exit_time")
                            t.exit_reason = td.get("exit_reason", "")
                            t.gross_pnl = td.get("gross_pnl", 0)
                            t.net_pnl = td.get("net_pnl", 0)
                            t.commission_paid = td.get("commission", 0)
                            t.position_size = td.get("position_size", 0)
                            t.holding_bars = td.get("holding_bars", 0)
                            result.trades.append(t)
                        result.metrics = result_dict.get("metrics", {})
                        result.data_bars = result_dict.get("data_bars", 0)
                        result.error = result_dict.get("error")
                        result.start_time = result_dict.get("start_time", "")
                        result.end_time = result_dict.get("end_time", "")
                        self.results.append(result)
                    except Exception as e:
                        self.errors.append({"campaign_id": cid, "error": str(e)})

                    self._completed += 1
                    if progress:
                        self._print_progress()

            except KeyboardInterrupt:
                print("\n[SCHEDULER] Received Ctrl+C, shutting down workers...")
                executor.shutdown(wait=False, cancel_futures=True)
                raise

    def _print_progress(self) -> None:
        """Print a compact progress line."""
        total = self._total
        done = self._completed
        elapsed = time.time() - self._start_time
        pct = done / total * 100
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate if rate > 0 else 0

        # Count successes vs errors
        errors = len(self.errors)

        msg = f"\r[SCHEDULER] {done}/{total} ({pct:.0f}%) | {rate:.1f}/s | ETA {eta:.0f}s | err={errors}"
        print(msg, end="", flush=True)

    def print_summary(self) -> None:
        """Print final summary table."""
        if not self.results:
            print("\nNo results.")
            return

        print("\n" + "=" * 80)
        print("CAMPAIGN RESULTS SUMMARY")
        print("=" * 80)
        print(f"{'ID':<12} {'Strategy':<18} {'Symbol':<10} {'TF':<6} {'Trades':<8} {'P&L':<12} {'Sharpe':<8} {'WR%':<8}")
        print("-" * 80)

        # Sort by Sharpe descending
        sorted_results = sorted(
            [r for r in self.results if r.metrics.get("sharpe", -99) != -99],
            key=lambda r: r.metrics.get("sharpe", -99),
            reverse=True,
        )

        for r in sorted_results[:40]:  # top 40
            m = r.metrics
            print(
                f"{r.config.campaign_id:<12} "
                f"{m.get('strategy', '?'):<18} "
                f"{m.get('symbol', '?'):<10} "
                f"{m.get('timeframe', '?'):<6} "
                f"{m.get('total_trades', 0):<8} "
                f"${m.get('total_pnl', 0):<+9.2f} "
                f"{m.get('sharpe', 0):<8.3f} "
                f"{m.get('win_rate_pct', 0):<8.1f}"
            )

        if self.errors:
            print(f"\nErrors: {len(self.errors)}")
            for e in self.errors[:5]:
                print(f"  ! {e['campaign_id']}: {e['error']}")
