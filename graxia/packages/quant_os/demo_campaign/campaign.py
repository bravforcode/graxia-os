"""
Demo Campaign Runner — 5-day demo campaign with daily monitoring.

Usage:
    cd quant_os
    python demo_campaign/campaign.py --symbol XAUUSD --days 5
"""
import sys
import os
import time
import yaml
import json
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from mt5_connector.connection import MT5Connection
from mt5_connector.shadow_runner import ShadowRunnerV2

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


class CampaignStatus(Enum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    COMPLETED = "completed"
    PAUSED = "paused"
    ABORTED = "aborted"


@dataclass
class DailyReport:
    date: str
    signals_total: int = 0
    signals_accepted: int = 0
    signals_rejected: int = 0
    sl_hits: int = 0
    tp_hits: int = 0
    time_stops: int = 0
    hypothetical_pnl: float = 0.0
    hypothetical_costs: float = 0.0
    net_pnl: float = 0.0
    max_drawdown: float = 0.0
    peak_equity: float = 0.0
    connection_uptime: float = 0.0
    mt5_disconnects: int = 0
    spread_shocks: int = 0
    pipeline_errors: int = 0

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "signals_total": self.signals_total,
            "signals_accepted": self.signals_accepted,
            "signals_rejected": self.signals_rejected,
            "sl_hits": self.sl_hits,
            "tp_hits": self.tp_hits,
            "time_stops": self.time_stops,
            "hypothetical_pnl": self.hypothetical_pnl,
            "hypothetical_costs": self.hypothetical_costs,
            "net_pnl": self.net_pnl,
            "max_drawdown": self.max_drawdown,
            "peak_equity": self.peak_equity,
            "connection_uptime": self.connection_uptime,
            "mt5_disconnects": self.mt5_disconnects,
            "spread_shocks": self.spread_shocks,
            "pipeline_errors": self.pipeline_errors,
        }


@dataclass
class CampaignResult:
    campaign_id: str
    status: CampaignStatus
    start_date: str
    end_date: str
    symbol: str
    daily_reports: list = field(default_factory=list)
    incidents: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "campaign_id": self.campaign_id,
            "status": self.status.value,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "symbol": self.symbol,
            "daily_reports": [r.to_dict() for r in self.daily_reports],
            "incidents": self.incidents,
        }


class DemoCampaign:
    """Run a multi-day demo campaign with monitoring."""

    def __init__(self, config_path: str = 'mt5_connector/config.yaml'):
        with open(config_path) as f:
            self._config = yaml.safe_load(f)

        self._mt5 = MT5Connection()
        self._runner = ShadowRunnerV2(config_path)
        self._campaign_id = f"campaign_{datetime.utcnow().strftime('%Y%m%d')}"
        self._status = CampaignStatus.NOT_STARTED
        self._daily_reports: list[DailyReport] = []
        self._incidents: list[dict] = []
        self._peak_equity = 100000.0
        self._running_pnl = 0.0

    def run(self, symbol: str = 'XAUUSD', days: int = 5, session_minutes: int = 390):
        """Run campaign for N days, 6.5 hours per day (390 min = one trading session)."""
        self._status = CampaignStatus.RUNNING
        logger.info(f"{'='*60}")
        logger.info(f"DEMO CAMPAIGN: {self._campaign_id}")
        logger.info(f"Symbol: {symbol}, Days: {days}, Session: {session_minutes}min")
        logger.info("NO ORDERS WILL BE SUBMITTED")
        logger.info(f"{'='*60}")

        start_date = datetime.utcnow()

        for day in range(days):
            day_start = datetime.utcnow()
            logger.info(f"\n--- Day {day+1}/{days} ({day_start.strftime('%Y-%m-%d')}) ---")

            daily = self._run_day(symbol, session_minutes, day+1)
            self._daily_reports.append(daily)

            logger.info(f"Day {day+1} complete:")
            logger.info(f"  Signals: {daily.signals_total} | Accepted: {daily.signals_accepted} | Rejected: {daily.signals_rejected}")
            logger.info(f"  SL: {daily.sl_hits} | TP: {daily.tp_hits} | Time: {daily.time_stops}")
            logger.info(f"  P&L: {daily.net_pnl:.2f}")

            # Wait until next trading day
            if day < days - 1:
                next_day = day_start + timedelta(days=1)
                wait_seconds = max(0, (next_day - datetime.utcnow()).total_seconds())
                if wait_seconds > 0:
                    logger.info(f"Waiting {wait_seconds/3600:.1f}h until next session...")
                    time.sleep(min(wait_seconds, 60))  # Cap wait for testing

        self._status = CampaignStatus.COMPLETED
        self._print_final_report()
        self._export_results()

        self._mt5.disconnect()

    def _run_day(self, symbol: str, session_minutes: int, day_num: int) -> DailyReport:
        """Run one day of the campaign."""
        daily = DailyReport(date=datetime.utcnow().strftime('%Y-%m-%d'))

        if not self._runner.connect():
            daily.pipeline_errors += 1
            self._incidents.append({
                "type": "MT5_CONNECT_FAILED",
                "date": daily.date,
                "details": "Failed to connect to MT5",
            })
            return daily

        start_time = time.time()
        cycle = 0
        interval = 30  # seconds between signals

        while (time.time() - start_time) < session_minutes * 60:
            cycle += 1
            try:
                result = self._runner.run_cycle(symbol)

                daily.signals_total += 1

                outcome = result.get('outcome', 'ERROR')
                if outcome.startswith('rejected_'):
                    daily.signals_rejected += 1
                    if 'spread_shock' in outcome:
                        daily.spread_shocks += 1
                else:
                    daily.signals_accepted += 1
                    if outcome == 'hit_sl':
                        daily.sl_hits += 1
                    elif outcome == 'hit_tp':
                        daily.tp_hits += 1
                    elif outcome == 'time_stop':
                        daily.time_stops += 1

                # Track P&L
                net = result.get('net_pnl', 0)
                daily.hypothetical_pnl += result.get('hypothetical_pnl', 0)
                daily.hypothetical_costs += result.get('hypothetical_costs', 0)
                self._running_pnl += net

                # Track drawdown
                equity = 100000 + self._running_pnl
                if equity > self._peak_equity:
                    self._peak_equity = equity
                daily.peak_equity = self._peak_equity

                if self._peak_equity > 0:
                    dd = (self._peak_equity - equity) / self._peak_equity * 100
                    if dd > daily.max_drawdown:
                        daily.max_drawdown = dd

            except Exception as e:
                daily.pipeline_errors += 1
                self._incidents.append({
                    "type": "PIPELINE_ERROR",
                    "date": daily.date,
                    "cycle": cycle,
                    "error": str(e),
                })

            time.sleep(interval)

        daily.net_pnl = daily.hypothetical_pnl - daily.hypothetical_costs
        daily.connection_uptime = session_minutes * 60

        self._runner.disconnect()
        return daily

    def _print_final_report(self):
        total_signals = sum(d.signals_total for d in self._daily_reports)
        total_accepted = sum(d.signals_accepted for d in self._daily_reports)
        total_rejected = sum(d.signals_rejected for d in self._daily_reports)
        total_sl = sum(d.sl_hits for d in self._daily_reports)
        total_tp = sum(d.tp_hits for d in self._daily_reports)
        total_pnl = sum(d.net_pnl for d in self._daily_reports)
        total_costs = sum(d.hypothetical_costs for d in self._daily_reports)
        max_dd = max((d.max_drawdown for d in self._daily_reports), default=0)

        logger.info(f"\n{'='*60}")
        logger.info(f"CAMPAIGN FINAL REPORT: {self._campaign_id}")
        logger.info(f"{'='*60}")
        logger.info(f"Total signals:  {total_signals}")
        logger.info(f"Accepted:       {total_accepted}")
        logger.info(f"Rejected:       {total_rejected}")
        logger.info(f"SL hits:        {total_sl}")
        logger.info(f"TP hits:        {total_tp}")
        logger.info(f"Total P&L:      {total_pnl:.2f}")
        logger.info(f"Total costs:    {total_costs:.2f}")
        logger.info(f"Net P&L:        {total_pnl - total_costs:.2f}")
        logger.info(f"Max drawdown:   {max_dd:.2f}%")
        logger.info(f"Incidents:      {len(self._incidents)}")
        logger.info(f"{'='*60}")

        # Verdict
        if total_accepted < 50:
            verdict = "INSUFFICIENT_DATA"
        elif max_dd > 10:
            verdict = "DRAWDOWN_EXCEEDED"
        elif len(self._incidents) > 5:
            verdict = "TOO_MANY_INCIDENTS"
        else:
            verdict = "ELIGIBLE_FOR_GUARDED_MICRO_LIVE_REVIEW"

        logger.info(f"VERDICT: {verdict}")
        logger.info(f"{'='*60}")

    def _export_results(self):
        os.makedirs('shadow_results', exist_ok=True)
        ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')

        # Campaign summary
        path = f'shadow_results/campaign_{ts}.json'
        result = CampaignResult(
            campaign_id=self._campaign_id,
            status=self._status,
            start_date=datetime.utcnow().strftime('%Y-%m-%d'),
            end_date=datetime.utcnow().strftime('%Y-%m-%d'),
            symbol='XAUUSD',
            daily_reports=self._daily_reports,
            incidents=self._incidents,
        )
        with open(path, 'w') as f:
            json.dump(result.to_dict(), f, indent=2)
        logger.info(f"Campaign results saved: {path}")

        # Daily reports
        for i, daily in enumerate(self._daily_reports):
            daily_path = f'shadow_results/daily_{ts}_{i+1}.json'
            with open(daily_path, 'w') as f:
                json.dump(daily.to_dict(), f, indent=2)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Demo Campaign Runner')
    parser.add_argument('--symbol', default='XAUUSD', help='Symbol to trade')
    parser.add_argument('--days', type=int, default=5, help='Campaign duration in days')
    parser.add_argument('--session', type=int, default=390, help='Session duration in minutes')
    args = parser.parse_args()

    campaign = DemoCampaign()
    campaign.run(symbol=args.symbol, days=args.days, session_minutes=args.session)


if __name__ == '__main__':
    main()
