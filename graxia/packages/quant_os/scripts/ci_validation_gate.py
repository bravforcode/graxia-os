"""CI/CD validation gate — runs validation pipeline and fails if gates don't pass.

Usage in CI:
    python scripts/ci_validation_gate.py --symbols XAUUSD EURUSD --timeframe H1

Exit codes:
    0 = All gates PASS
    1 = One or more gates FAIL
    2 = Pipeline error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add monorepo root to path
_repo_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_repo_root))

from graxia.packages.quant_os.validation.pipeline.config import PipelineConfig
from graxia.packages.quant_os.validation.pipeline.report import ReportGenerator
from graxia.packages.quant_os.validation.pipeline.runner import ValidationRunner


def main():
    parser = argparse.ArgumentParser(description="CI Validation Gate")
    parser.add_argument("--symbols", nargs="+", default=["XAUUSD", "EURUSD"])
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--mc-sims", type=int, default=10000)
    parser.add_argument("--wfa-windows", type=int, default=8)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--output-dir", default="reports/validation")
    parser.add_argument("--strict", action="store_true", help="Fail on WARN gates too (default: only FAIL)")
    args = parser.parse_args()

    config = PipelineConfig(
        symbols=args.symbols,
        timeframe=args.timeframe,
        mc_n_sims=args.mc_sims,
        wfa_n_windows=args.wfa_windows,
        max_workers=args.max_workers,
        reports_dir=Path(args.output_dir),
    )

    # Validate config
    errors = config.validate()
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    # Run pipeline
    print(f"Running validation: {args.symbols} {args.timeframe}")
    runner = ValidationRunner(config)
    result = runner.run_all()

    # Generate report
    report_gen = ReportGenerator(config.reports_dir)
    md_path, json_path = report_gen.generate(result)

    # Print results
    print(f"\nResults ({result.total_elapsed_sec:.1f}s):")
    for name, ws in result.results.items():
        status = "[OK]" if ws.success else "[FAIL]"
        print(f"  {status} {name}")

    # Check gates
    if result.gate_summary:
        for gate in result.gate_summary.gates:
            icon = {"PASS": "[PASS]", "FAIL": "[FAIL]", "WARN": "[WARN]"}.get(gate.status.value, "")
            print(f"  {icon} {gate.name}: {gate.details}")

        print(f"\nOverall: {result.gate_summary.overall.value}")
        print(f"Reports: {md_path}")

        # Exit code
        if (
            result.gate_summary.overall.value == "PASS"
            or result.gate_summary.overall.value == "WARN"
            and not args.strict
        ):
            sys.exit(0)
        else:
            sys.exit(1)
    else:
        print("No gate evaluation available")
        sys.exit(2)


if __name__ == "__main__":
    main()
