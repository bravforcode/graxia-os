"""CLI entry point for parallel validation pipeline.

Usage:
    python scripts/run_validation.py                          # Default: XAUUSD + EURUSD
    python scripts/run_validation.py --symbols XAUUSD EURUSD  # Specific symbols
    python scripts/run_validation.py --timeframe D1           # Daily data
    python scripts/run_validation.py --no-live                # Skip live testing
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add monorepo root to path so `graxia.packages.quant_os` resolves
_repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(_repo_root))

from graxia.packages.quant_os.validation.pipeline.config import PipelineConfig
from graxia.packages.quant_os.validation.pipeline.report import ReportGenerator
from graxia.packages.quant_os.validation.pipeline.runner import ValidationRunner


def main():
    parser = argparse.ArgumentParser(description="Parallel Validation Pipeline")
    parser.add_argument("--symbols", nargs="+", default=["XAUUSD", "EURUSD"], help="Symbols to validate")
    parser.add_argument("--timeframe", default="H1", help="Timeframe (H1, D1, etc.)")
    parser.add_argument("--data-dir", default="data", help="Data directory")
    parser.add_argument("--reports-dir", default="reports/validation", help="Reports output directory")
    parser.add_argument("--mc-sims", type=int, default=10000, help="Monte Carlo simulations")
    parser.add_argument("--wfa-windows", type=int, default=8, help="Walk-forward windows")
    parser.add_argument("--no-live", action="store_true", help="Skip live testing")
    parser.add_argument("--max-workers", type=int, default=4, help="Max parallel workers")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    args = parser.parse_args()

    config = PipelineConfig(
        symbols=args.symbols,
        timeframe=args.timeframe,
        data_dir=Path(args.data_dir),
        reports_dir=Path(args.reports_dir),
        mc_n_sims=args.mc_sims,
        wfa_n_windows=args.wfa_windows,
        live_enabled=not args.no_live,
        max_workers=args.max_workers,
    )

    # Validate config
    errors = config.validate()
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if not args.quiet:
        print("=" * 60)
        print("PARALLEL VALIDATION PIPELINE")
        print("=" * 60)
        print(f"Symbols: {', '.join(config.symbols)}")
        print(f"Timeframe: {config.timeframe}")
        print(f"MC Sims: {config.mc_n_sims}")
        print(f"WFA Windows: {config.wfa_n_windows}")
        print(f"Max Workers: {config.max_workers}")
        print("=" * 60)
        print()

    # Run pipeline
    runner = ValidationRunner(config)
    result = runner.run_all()

    # Generate report
    report_gen = ReportGenerator(config.reports_dir)
    md_path, json_path = report_gen.generate(result)

    # Print summary
    if not args.quiet:
        for name, ws in result.results.items():
            status = "[OK]" if ws.success else "[FAIL]"
            print(f"  {status} {name}: {ws.elapsed_sec:.1f}s")
            if not ws.success:
                print(f"     Error: {ws.error}")

        print()
        if result.gate_summary:
            emoji = {"PASS": "[PASS]", "FAIL": "[FAIL]", "WARN": "[WARN]"}.get(result.gate_summary.overall.value, "")
            print(f"Overall: {emoji} {result.gate_summary.overall.value}")
            print(
                f"Gates: {sum(1 for g in result.gate_summary.gates if g.status.value == 'PASS')}/{len(result.gate_summary.gates)} PASS"
            )

        print(f"\nTotal time: {result.total_elapsed_sec:.1f}s")
        print("\nReports saved:")
        print(f"  {md_path}")
        print(f"  {json_path}")

    # Exit code based on gate result
    if result.gate_summary and result.gate_summary.overall.value == "PASS":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
