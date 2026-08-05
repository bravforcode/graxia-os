"""
Strategy Leaderboard
====================
Ranks all validated strategies by edge quality based on their
edge verification reports.

Metrics used for ranking:
1. Gates Passed (0-5): Primary ranking factor
2. Walk-Forward Sharpe: Risk-adjusted returns out-of-sample
3. PBO Score: Lower is better (less overfitting)
4. Bootstrap CI: Whether CI excludes zero
5. Cost Stress Resilience: Performance under higher costs

Usage:
    python scripts/strategy_leaderboard.py
"""

import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Fix Unicode encoding on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"


@dataclass
class StrategyResult:
    """Parsed result from an edge verification report."""

    name: str
    symbol: str
    timeframe: str
    n_bars: int
    validation_date: str

    # Baseline metrics
    total_trades: int
    win_rate: float
    sharpe_ratio: float
    profit_factor: float
    max_drawdown_pct: float

    # Gate results
    gates_passed: int
    total_gates: int

    # Individual gate verdicts
    wf_pass: bool
    wf_sharpe: float
    wf_positive_folds: str

    dsr_pass: bool
    dsr_sharpe: float
    dsr_p_alpha: float

    pbo_pass: bool
    pbo_score: float

    bootstrap_pass: bool
    bootstrap_sharpe: float
    bootstrap_ci_lower: float
    bootstrap_ci_upper: float

    cost_pass: bool
    cost_degradation: float

    # Final verdict
    verdict: str
    recommendation: str

    @property
    def edge_score(self) -> float:
        """Composite edge quality score (0-100)."""
        score = 0.0

        # Gates passed (40% weight)
        score += (self.gates_passed / max(self.total_gates, 1)) * 40

        # Walk-forward Sharpe (20% weight, normalized)
        if self.wf_sharpe > 0:
            score += min(self.wf_sharpe / 2.0, 1.0) * 20

        # PBO score (15% weight, lower is better)
        if self.pbo_score < 0.05:
            score += 15
        elif self.pbo_score < 0.2:
            score += 10
        elif self.pbo_score < 0.5:
            score += 5

        # Bootstrap (15% weight)
        if self.bootstrap_pass:
            score += 15
        elif self.bootstrap_ci_upper > 0 and self.bootstrap_ci_lower < 0:
            score += 5  # CI includes zero but has positive upper bound

        # Cost resilience (10% weight)
        if self.cost_pass:
            score += 10
        elif self.cost_degradation < 75:
            score += 5

        return round(score, 1)

    @property
    def rank_tier(self) -> str:
        """Rank tier based on edge score."""
        score = self.edge_score
        if score >= 80:
            return "S-TIER"
        elif score >= 60:
            return "A-TIER"
        elif score >= 40:
            return "B-TIER"
        elif score >= 20:
            return "C-TIER"
        else:
            return "D-TIER"


def parse_report(report_path: Path) -> StrategyResult | None:
    """Parse an edge verification report file."""
    try:
        content = report_path.read_text()

        # Extract strategy name
        name_match = re.search(r"EDGE VERIFICATION REPORT: (.+)", content)
        name = name_match.group(1).strip() if name_match else report_path.stem

        # Extract symbol and timeframe
        symbol_match = re.search(r"Symbol: (\w+) (\w+)", content)
        symbol = symbol_match.group(1) if symbol_match else "UNKNOWN"
        timeframe = symbol_match.group(2) if symbol_match else "D1"

        # Extract data bars
        bars_match = re.search(r"Data: (\d+) bars", content)
        n_bars = int(bars_match.group(1)) if bars_match else 0

        # Extract date
        date_match = re.search(r"Date: (\S+)", content)
        validation_date = date_match.group(1) if date_match else ""

        # Extract baseline metrics
        trades_match = re.search(r"Total Trades: (\d+\.?\d*)", content)
        total_trades = int(float(trades_match.group(1))) if trades_match else 0

        win_rate_match = re.search(r"Win Rate: (\d+\.?\d*)%", content)
        win_rate = float(win_rate_match.group(1)) / 100 if win_rate_match else 0.0

        sharpe_match = re.search(r"Sharpe Ratio: (-?\d+\.?\d*)", content)
        sharpe_ratio = float(sharpe_match.group(1)) if sharpe_match else 0.0

        pf_match = re.search(r"Profit Factor: (\d+\.?\d*)", content)
        profit_factor = float(pf_match.group(1)) if pf_match else 0.0

        dd_match = re.search(r"Max Drawdown Pct: (\d+\.?\d*)", content)
        max_drawdown_pct = float(dd_match.group(1)) if dd_match else 0.0

        # Extract gates passed
        gates_match = re.search(r"FINAL: (\d+)/(\d+) gates passed", content)
        gates_passed = int(gates_match.group(1)) if gates_match else 0
        total_gates = int(gates_match.group(2)) if gates_match else 5

        # Extract walk-forward results
        wf_match = re.search(r"WALK-FORWARD: (\d+/\d+) positive, (\d+) trades, Sharpe=(-?\d+\.?\d*)", content)
        wf_positive_folds = wf_match.group(1) if wf_match else "0/0"
        wf_sharpe = float(wf_match.group(3)) if wf_match else 0.0
        wf_pass = "PASS" in content.split("WALK-FORWARD")[1].split("\n")[1] if "WALK-FORWARD" in content else False

        # Extract DSR results
        dsr_match = re.search(r"DSR: Sharpe=(-?\d+\.?\d*), P\(alpha\)=(-?\d+\.?\d*)", content)
        dsr_sharpe = float(dsr_match.group(1)) if dsr_match else 0.0
        dsr_p_alpha = float(dsr_match.group(2)) if dsr_match else 1.0
        dsr_pass = False
        if "DSR" in content:
            dsr_section = content.split("DSR")[1].split("\n")[1]
            dsr_pass = "PASS" in dsr_section

        # Extract PBO results
        pbo_match = re.search(r"PBO: (-?\d+\.?\d*)", content)
        pbo_score = float(pbo_match.group(1)) if pbo_match else 1.0
        pbo_pass = False
        if "PBO" in content:
            pbo_section = content.split("PBO")[1].split("\n")[1]
            pbo_pass = "PASS" in pbo_section

        # Extract Bootstrap results
        bootstrap_match = re.search(r"BOOTSTRAP: Sharpe=(-?\d+\.?\d*), CI=\[(-?\d+\.?\d*), (-?\d+\.?\d*)\]", content)
        bootstrap_sharpe = float(bootstrap_match.group(1)) if bootstrap_match else 0.0
        bootstrap_ci_lower = float(bootstrap_match.group(2)) if bootstrap_match else 0.0
        bootstrap_ci_upper = float(bootstrap_match.group(3)) if bootstrap_match else 0.0
        bootstrap_pass = False
        if "BOOTSTRAP" in content:
            bootstrap_section = content.split("BOOTSTRAP")[1].split("\n")[1]
            bootstrap_pass = "PASS" in bootstrap_section

        # Extract Cost Stress results
        cost_match = re.search(r"COST STRESS: Base=(-?\d+\.?\d*), 2x=(-?\d+\.?\d*), Degradation=(-?\d+\.?\d*)%", content)
        cost_degradation = float(cost_match.group(3)) if cost_match else 100.0
        cost_pass = False
        if "COST STRESS" in content:
            cost_section = content.split("COST STRESS")[1].split("\n")[1]
            cost_pass = "PASS" in cost_section

        # Extract final verdict
        verdict_match = re.search(r"VERDICT: (.+)", content)
        verdict = verdict_match.group(1).strip() if verdict_match else "UNKNOWN"

        recommendation_match = re.search(r"RECOMMENDATION: (.+)", content)
        recommendation = recommendation_match.group(1).strip() if recommendation_match else ""

        return StrategyResult(
            name=name,
            symbol=symbol,
            timeframe=timeframe,
            n_bars=n_bars,
            validation_date=validation_date,
            total_trades=total_trades,
            win_rate=win_rate,
            sharpe_ratio=sharpe_ratio,
            profit_factor=profit_factor,
            max_drawdown_pct=max_drawdown_pct,
            gates_passed=gates_passed,
            total_gates=total_gates,
            wf_pass=wf_pass,
            wf_sharpe=wf_sharpe,
            wf_positive_folds=wf_positive_folds,
            dsr_pass=dsr_pass,
            dsr_sharpe=dsr_sharpe,
            dsr_p_alpha=dsr_p_alpha,
            pbo_pass=pbo_pass,
            pbo_score=pbo_score,
            bootstrap_pass=bootstrap_pass,
            bootstrap_sharpe=bootstrap_sharpe,
            bootstrap_ci_lower=bootstrap_ci_lower,
            bootstrap_ci_upper=bootstrap_ci_upper,
            cost_pass=cost_pass,
            cost_degradation=cost_degradation,
            verdict=verdict,
            recommendation=recommendation,
        )
    except Exception as e:
        print(f"Error parsing {report_path}: {e}")
        return None


def generate_leaderboard(results: list[StrategyResult]) -> str:
    """Generate formatted leaderboard."""
    lines = []

    # Sort by edge score (descending)
    sorted_results = sorted(results, key=lambda r: r.edge_score, reverse=True)

    lines.append("=" * 100)
    lines.append("STRATEGY LEADERBOARD — EDGE QUALITY RANKINGS")
    lines.append(f"Generated: {datetime.now().isoformat()}")
    lines.append(f"Strategies Evaluated: {len(results)}")
    lines.append("=" * 100)

    # Summary table
    lines.append("\n" + "-" * 100)
    lines.append(f"{'Rank':<6} {'Tier':<8} {'Strategy':<35} {'Symbol':<10} {'TF':<5} {'Gates':<7} {'Score':<7} {'Verdict'}")
    lines.append("-" * 100)

    for i, result in enumerate(sorted_results, 1):
        lines.append(
            f"{i:<6} {result.rank_tier:<8} {result.name:<35} {result.symbol:<10} "
            f"{result.timeframe:<5} {result.gates_passed}/{result.total_gates:<5} "
            f"{result.edge_score:<7.1f} {result.verdict}"
        )

    lines.append("-" * 100)

    # Detailed breakdown for each strategy
    lines.append("\n" + "=" * 100)
    lines.append("DETAILED BREAKDOWN")
    lines.append("=" * 100)

    for i, result in enumerate(sorted_results, 1):
        lines.append(f"\n{'─' * 80}")
        lines.append(f"#{i} {result.name} ({result.symbol} {result.timeframe})")
        lines.append(f"   Edge Score: {result.edge_score}/100 | Tier: {result.rank_tier}")
        lines.append(f"   Data: {result.n_bars} bars | Trades: {result.total_trades} | Win Rate: {result.win_rate*100:.1f}%")
        lines.append(f"   Sharpe: {result.sharpe_ratio:.4f} | PF: {result.profit_factor:.2f} | MaxDD: {result.max_drawdown_pct:.1f}%")
        lines.append(f"")
        lines.append(f"   Gate Results:")
        lines.append(f"     Walk-Forward:  {'PASS' if result.wf_pass else 'FAIL'} ({result.wf_positive_folds} positive, Sharpe={result.wf_sharpe:.4f})")
        lines.append(f"     DSR:           {'PASS' if result.dsr_pass else 'FAIL'} (P(alpha)={result.dsr_p_alpha:.4f})")
        lines.append(f"     PBO:           {'PASS' if result.pbo_pass else 'FAIL'} (Score={result.pbo_score:.4f})")
        lines.append(f"     Bootstrap:     {'PASS' if result.bootstrap_pass else 'FAIL'} (CI=[{result.bootstrap_ci_lower:.4f}, {result.bootstrap_ci_upper:.4f}])")
        lines.append(f"     Cost Stress:   {'PASS' if result.cost_pass else 'FAIL'} (Degradation={result.cost_degradation:.1f}%)")
        lines.append(f"")
        lines.append(f"   Verdict: {result.verdict}")
        lines.append(f"   Recommendation: {result.recommendation}")

    lines.append("\n" + "=" * 100)
    lines.append("SCORING METHODOLOGY")
    lines.append("=" * 100)
    lines.append("""
    Edge Score (0-100) is computed from:
    • Gates Passed (40%): Walk-Forward, DSR, PBO, Bootstrap, Cost Stress
    • Walk-Forward Sharpe (20%): Normalized to 0-2.0 range
    • PBO Score (15%): <0.05 = full, <0.2 = partial, <0.5 = minimal
    • Bootstrap CI (15%): Pass = full, includes zero = partial
    • Cost Resilience (10%): Pass = full, <75% degradation = partial

    Tier Rankings:
    • S-TIER (80+): Strong edge, ready for paper trading
    • A-TIER (60-79): Promising edge, needs more validation
    • B-TIER (40-59): Mixed signals, investigate further
    • C-TIER (20-39): Weak edge, not recommended
    • D-TIER (<20): No edge detected, reject
    """)

    return "\n".join(lines)


def main():
    """Generate strategy leaderboard from validation reports."""
    print("=" * 80)
    print("GENERATING STRATEGY LEADERBOARD")
    print("=" * 80)

    # Find all edge verification reports
    report_patterns = [
        "*_edge_verification.txt",
        "*_validation.txt",
    ]

    report_files = []
    for pattern in report_patterns:
        report_files.extend(REPORTS_DIR.glob(pattern))

    if not report_files:
        print("No validation reports found in reports/ directory")
        return

    print(f"Found {len(report_files)} validation reports")

    # Parse all reports
    results = []
    for report_path in sorted(report_files):
        print(f"  Parsing: {report_path.name}")
        result = parse_report(report_path)
        if result:
            results.append(result)

    if not results:
        print("No valid results parsed from reports")
        return

    # Generate leaderboard
    leaderboard = generate_leaderboard(results)

    # Print to console
    print("\n" + leaderboard)

    # Save to file
    output_path = REPORTS_DIR / "strategy_leaderboard.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(leaderboard)

    print(f"\nLeaderboard saved to: {output_path}")

    # Summary
    s_tier = sum(1 for r in results if r.rank_tier == "S-TIER")
    a_tier = sum(1 for r in results if r.rank_tier == "A-TIER")
    b_tier = sum(1 for r in results if r.rank_tier == "B-TIER")
    c_tier = sum(1 for r in results if r.rank_tier == "C-TIER")
    d_tier = sum(1 for r in results if r.rank_tier == "D-TIER")

    print(f"\nTier Distribution: S={s_tier}, A={a_tier}, B={b_tier}, C={c_tier}, D={d_tier}")


if __name__ == "__main__":
    main()
