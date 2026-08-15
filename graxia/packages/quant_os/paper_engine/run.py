#!/usr/bin/env python3
"""
CLI entry point for the Parallel Paper Trading Engine.

Usage:
    python -m paper_engine.run --generate 500
    python -m paper_engine.run --run campaigns.json
    python -m paper_engine.run --run campaigns.json --workers 12
    python -m paper_engine.run --report
    python -m paper_engine.run --quick  # 10-campaign smoke test
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Ensure quant_os is on path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from paper_engine.campaign import (
    CampaignConfig,
    estimate_duration,
    generate_campaigns,
    load_campaigns,
    save_campaigns,
)
from paper_engine.engine import run_campaign
from paper_engine.result_store import ResultStore
from paper_engine.analyzer import CampaignAnalyzer
from paper_engine.scheduler import CampaignScheduler


def cmd_generate(args):
    """Generate N campaign configs."""
    print(f"Generating campaigns...")
    campaigns = generate_campaigns(
        strategies=args.strategies,
        symbols=args.symbols,
        timeframes=args.timeframes,
        param_variations=not args.no_params,
    )
    # Filter to requested count
    if args.count and args.count < len(campaigns):
        campaigns = campaigns[:args.count]

    path = save_campaigns(campaigns, args.output)
    est = estimate_duration(campaigns, workers=args.workers)
    print(f"Generated {len(campaigns)} campaigns")
    print(f"Saved to: {path}")
    print(f"Estimated: {est['estimated_parallel_min']} min with {args.workers} workers")
    return path


def cmd_run(args):
    """Run campaigns from a config file."""
    campaigns = load_campaigns(args.campaigns)
    print(f"Loaded {len(campaigns)} campaigns from {args.campaigns}")

    if args.filter_strategy:
        campaigns = [c for c in campaigns if c.strategy_id in args.filter_strategy]
        print(f"Filtered to {len(campaigns)} campaigns for strategy={args.filter_strategy}")
    if args.filter_symbol:
        campaigns = [c for c in campaigns if c.symbol in args.filter_symbol]
        print(f"Filtered to {len(campaigns)} campaigns for symbol={args.filter_symbol}")

    store_path = Path(args.store) if args.store else None

    scheduler = CampaignScheduler(
        campaigns=campaigns,
        workers=args.workers,
        store_path=store_path,
        batch_size=args.batch_size,
    )
    results = scheduler.run_all(progress=True)

    scheduler.print_summary()

    # Save results
    result_store = store_path or ResultStore()
    result_store.save_batch(results)
    ranking = result_store.get_ranking(top_n=40)
    rank_path = result_store.save_ranking(ranking)
    if rank_path:
        print(f"Ranking: {rank_path}")

    # Quick report
    analyzer = CampaignAnalyzer(result_store)
    reports_dir = Path(args.store if args.store else store_path) if (args.store or store_path) else Path("reports/paper_engine")
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "analysis_report.md"
    analyzer.generate_report(str(report_path))
    print(f"Report: {report_path}")

    return results


def cmd_quick(args):
    """Quick 10-campaign smoke test — sequential for debugging."""
    print("=" * 60)
    print("QUICK SMOKE TEST — 10 campaigns, sequential")
    print("=" * 60)

    campaigns = generate_campaigns(
        strategies=["tsm", "rsi_bb", "donchian"],
        symbols=["XAUUSD", "EURUSD"],
        timeframes=["D1", "H4"],
        param_variations=False,
    )[:10]

    print(f"Running {len(campaigns)} campaigns:\n")
    results = []
    for i, c in enumerate(campaigns, 1):
        print(f"  [{i}/{len(campaigns)}] {c.campaign_id}: {c.strategy_id} {c.symbol} {c.timeframe}...", end=" ")
        sys.stdout.flush()
        t0 = time.time()
        r = run_campaign(c)
        elapsed = time.time() - t0
        m = r.metrics
        print(f"done in {elapsed:.1f}s — {m.get('total_trades', 0)} trades, Sharpe={m.get('sharpe', 'N/A')}")
        results.append(r)

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"{'ID':<12} {'Strategy':<16} {'Symbol':<10} {'TF':<6} {'Trades':<8} {'P&L':<12} {'Sharpe':<8} {'WR%':<8}")
    print("-" * 60)
    for r in sorted(results, key=lambda r: r.metrics.get("sharpe", -99), reverse=True):
        m = r.metrics
        print(
            f"{r.config.campaign_id:<12} "
            f"{m.get('strategy', '?'):<16} "
            f"{m.get('symbol', '?'):<10} "
            f"{m.get('timeframe', '?'):<6} "
            f"{m.get('total_trades', 0):<8} "
            f"${m.get('total_pnl', 0):<+9.2f} "
            f"{m.get('sharpe', 0):<8.3f} "
            f"{m.get('win_rate_pct', 0):<8.1f}"
        )

    # Save
    store = ResultStore()
    store.save_batch(results)
    ranking = store.get_ranking(top_n=10)
    store.save_ranking(ranking)
    print(f"\nResults saved to reports/paper_engine/")
    print("=" * 60)


def cmd_report(args):
    """Generate analysis report from existing results."""
    store = ResultStore()
    stats = store.get_stats()
    print(f"\nStats: {json.dumps(stats, indent=2)}")

    analyzer = CampaignAnalyzer(store)
    report = analyzer.generate_report(args.output)
    print(f"Report saved: {args.output}")

    # Print top 10
    print("\nTop 10 Campaigns:")
    rankings = store.get_ranking(top_n=10)
    for i, r in enumerate(rankings, 1):
        print(f"  {i}. {r['campaign_id']}: {r['strategy']} {r['symbol']} {r['timeframe']} "
              f"— Sharpe={r['sharpe']:.3f}, P&L=${r['pnl']:+.0f}, WR={r['win_rate']:.1f}%")


def cmd_list_symbols(args):
    """List available symbols with data."""
    from paper_engine.price_feed import get_available_symbols

    symbols = get_available_symbols()
    print(f"Available symbols ({len(symbols)}):")
    for s in sorted(symbols):
        print(f"  - {s}")


def main():
    parser = argparse.ArgumentParser(description="Parallel Paper Trading Engine")
    sub = parser.add_subparsers(dest="command", help="Command")

    # Generate
    p_gen = sub.add_parser("generate", help="Generate campaign configs")
    p_gen.add_argument("--count", type=int, default=500, help="Number of campaigns")
    p_gen.add_argument("--strategies", nargs="+", default=None, help="Strategies to include")
    p_gen.add_argument("--symbols", nargs="+", default=None, help="Symbols to include")
    p_gen.add_argument("--timeframes", nargs="+", default=None, help="Timeframes")
    p_gen.add_argument("--no-params", action="store_true", help="Skip param variations")
    p_gen.add_argument("--output", type=str, default=None, help="Output JSON path")
    p_gen.add_argument("--workers", type=int, default=8, help="Worker count for estimation")

    # Run
    p_run = sub.add_parser("run", help="Run campaigns from config file")
    p_run.add_argument("campaigns", type=str, help="Campaign config JSON file")
    p_run.add_argument("--workers", type=int, default=None, help="Worker processes")
    p_run.add_argument("--batch-size", type=int, default=50, help="Campaigns per batch")
    p_run.add_argument("--store", type=str, default=None, help="Results directory")
    p_run.add_argument("--filter-strategy", nargs="+", default=None)
    p_run.add_argument("--filter-symbol", nargs="+", default=None)

    # Quick
    p_quick = sub.add_parser("quick", help="Quick 10-campaign smoke test")

    # Report
    p_report = sub.add_parser("report", help="Generate analysis report")
    p_report.add_argument("--output", type=str, default="reports/paper_engine/analysis_report.md")

    # List symbols
    p_list = sub.add_parser("symbols", help="List available symbols")

    args = parser.parse_args()

    if args.command == "generate":
        cmd_generate(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "quick":
        cmd_quick(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "symbols":
        cmd_list_symbols(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
