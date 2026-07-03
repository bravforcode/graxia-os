"""
Pipeline 10: Ensemble Optimizer → Vault (weekly)
Grid-searches weight combinations for MTM/MRB/MLB ensemble,
evaluates on historical performance, and writes a vault note.
"""

import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# ── Constants ────────────────────────────────────────────────────────────
STRATEGIES = ["mtm", "mrb", "mlb"]

CURRENT_WEIGHTS: dict[str, float] = {
    "mtm": 0.40,
    "mrb": 0.25,
    "mlb": 0.35,
}

VAULT_DIR = Path(
    r"C:\Users\menum\Documents\ObsidianVault\Second Brain\03-resources\trading\ensemble"
)

# Grid search step: 0.05 increments → ~1330 combos (3 steps from 0.05 to 0.95)
GRID_STEP = 0.05
MIN_WEIGHT = 0.05
MAX_WEIGHT = 0.95
WEIGHT_TOLERANCE = 0.001  # sum must be within 1.0 ± tolerance


# ── Data Classes ─────────────────────────────────────────────────────────
@dataclass
class StrategyPerformance:
    """Single strategy backtest result."""

    name: str
    total_trades: int
    win_rate: float  # 0.0–1.0
    profit_factor: float  # gross_profit / gross_loss
    sharpe_ratio: float
    max_drawdown_pct: float  # percentage
    avg_trade_pnl: float
    expectancy: float  # (win_rate * avg_win) - ((1-win_rate) * avg_loss)
    regime_scores: dict[str, float] = field(default_factory=dict)  # regime → score


@dataclass
class WeightCombo:
    """A tested weight combination and its ensemble metrics."""

    mtm: float
    mrb: float
    mlb: float
    sharpe: float
    profit_factor: float
    win_rate: float
    expected_return: float
    max_drawdown: float
    composite_score: float  # weighted blend of metrics


# ── Performance Evaluation ───────────────────────────────────────────────
def evaluate_combo(
    weights: dict[str, float],
    perfs: dict[str, StrategyPerformance],
) -> WeightCombo:
    """Score a weight combo from individual strategy metrics."""
    total_trades = 0
    weighted_sharpe = 0.0
    weighted_pf = 0.0
    weighted_wr = 0.0
    weighted_expect = 0.0
    weighted_dd = 0.0

    for s in STRATEGIES:
        p = perfs[s]
        w = weights[s]
        total_trades += p.total_trades * w
        weighted_sharpe += p.sharpe_ratio * w
        weighted_pf += p.profit_factor * w
        weighted_wr += p.win_rate * w
        weighted_expect += p.expectancy * w
        weighted_dd += p.max_drawdown_pct * w

    # Composite: 0.4×Sharpe + 0.3×PF + 0.2×expectancy − 0.1×drawdown
    composite = (
        0.4 * weighted_sharpe
        + 0.3 * weighted_pf
        + 0.2 * weighted_expect
        - 0.1 * weighted_dd
    )

    return WeightCombo(
        mtm=weights["mtm"],
        mrb=weights["mrb"],
        mlb=weights["mlb"],
        sharpe=round(weighted_sharpe, 4),
        profit_factor=round(weighted_pf, 4),
        win_rate=round(weighted_wr, 4),
        expected_return=round(weighted_expect, 4),
        max_drawdown=round(weighted_dd, 4),
        composite_score=round(composite, 4),
    )


def grid_search(perfs: dict[str, StrategyPerformance]) -> list[WeightCombo]:
    """Exhaustive grid search over weight combos summing to ~1.0."""
    step = GRID_STEP
    combos: list[WeightCombo] = []

    raw = [
        round(MIN_WEIGHT + i * step, 2)
        for i in range(int((MAX_WEIGHT - MIN_WEIGHT) / step) + 1)
    ]

    for mtm_w in raw:
        for mrb_w in raw:
            mlb_w = round(1.0 - mtm_w - mrb_w, 2)
            if mlb_w < MIN_WEIGHT or mlb_w > MAX_WEIGHT:
                continue
            if abs(mtm_w + mrb_w + mlb_w - 1.0) > WEIGHT_TOLERANCE:
                continue
            weights = {"mtm": mtm_w, "mrb": mrb_w, "mlb": mlb_w}
            combos.append(evaluate_combo(weights, perfs))

    combos.sort(key=lambda c: c.composite_score, reverse=True)
    return combos


# ── Regime-Dependent Weights ─────────────────────────────────────────────
def regime_weights(
    perfs: dict[str, StrategyPerformance],
) -> dict[str, dict[str, float]]:
    """Suggest weights per regime based on strategy regime_scores."""
    regimes = ["trending", "ranging", "volatile"]
    suggestions: dict[str, dict[str, float]] = {}

    for regime in regimes:
        scores = {}
        for s in STRATEGIES:
            scores[s] = perfs[s].regime_scores.get(regime, 0.5)

        total = sum(scores.values()) or 1.0
        suggestions[regime] = {s: round(scores[s] / total, 2) for s in STRATEGIES}

    return suggestions


# ── Overfitting Risk ─────────────────────────────────────────────────────
def overfitting_risk(
    combos: list[WeightCombo], current: dict[str, float]
) -> dict[str, Any]:
    """Simple heuristic: how far is the optimal from current, and how flat is the surface."""
    if len(combos) < 10:
        return {"level": "unknown", "detail": "insufficient combos"}

    best = combos[0]
    worst = combos[-1]
    median_idx = len(combos) // 2
    median = combos[median_idx]

    # Distance from current weights to optimal
    dist = math.sqrt(
        (best.mtm - current["mtm"]) ** 2
        + (best.mrb - current["mrb"]) ** 2
        + (best.mlb - current["mlb"]) ** 2
    )

    # Score spread: how much does score vary across all combos
    score_range = best.composite_score - worst.composite_score

    # Top 10% average score vs next 10%
    top_n = max(1, len(combos) // 10)
    top_avg = sum(c.composite_score for c in combos[:top_n]) / top_n
    next_avg = (
        sum(c.composite_score for c in combos[top_n : 2 * top_n]) / top_n
        if len(combos) >= 2 * top_n
        else median.composite_score
    )
    peakiness = top_avg - next_avg

    if dist > 0.3:
        level = "high"
        reason = f"Optimal far from current (dist={dist:.3f}); large rebalance needed"
    elif peakiness < 0.01 and score_range < 0.05:
        level = "high"
        reason = "Flat scoring surface — most combos similar; optimization may be noise"
    elif peakiness < 0.05:
        level = "medium"
        reason = "Moderate peakiness; small edge over random combos"
    else:
        level = "low"
        reason = f"Clear peak at optimal (peakiness={peakiness:.4f})"

    return {
        "level": level,
        "distance": round(dist, 4),
        "score_range": round(score_range, 4),
        "peakiness": round(peakiness, 4),
        "reason": reason,
    }


# ── Impact Analysis ──────────────────────────────────────────────────────
def impact_analysis(
    current: dict[str, float],
    optimal: WeightCombo,
    perfs: dict[str, StrategyPerformance],
) -> dict[str, Any]:
    """What changes if we rebalance from current → optimal."""
    current_combo = evaluate_combo(current, perfs)
    delta_sharpe = optimal.sharpe - current_combo.sharpe
    delta_pf = optimal.profit_factor - current_combo.profit_factor
    delta_wr = optimal.win_rate - current_combo.win_rate
    delta_dd = optimal.max_drawdown - current_combo.max_drawdown

    return {
        "current": {
            "mtm": current["mtm"],
            "mrb": current["mrb"],
            "mlb": current["mlb"],
            "sharpe": current_combo.sharpe,
            "pf": current_combo.profit_factor,
            "win_rate": current_combo.win_rate,
            "drawdown": current_combo.max_drawdown,
        },
        "optimal": {
            "mtm": optimal.mtm,
            "mrb": optimal.mrb,
            "mlb": optimal.mlb,
            "sharpe": optimal.sharpe,
            "pf": optimal.profit_factor,
            "win_rate": optimal.win_rate,
            "drawdown": optimal.max_drawdown,
        },
        "deltas": {
            "sharpe": round(delta_sharpe, 4),
            "pf": round(delta_pf, 4),
            "win_rate": round(delta_wr, 4),
            "drawdown": round(delta_dd, 4),
        },
    }


# ── Vault Note Generation ────────────────────────────────────────────────
def generate_vault_note(
    week_num: int,
    current: dict[str, float],
    combos: list[WeightCombo],
    regime_w: dict[str, dict[str, float]],
    overfit: dict[str, Any],
    impact: dict[str, Any],
) -> str:
    """Build the Obsidian-compatible markdown vault note."""
    now = datetime.now()
    best = combos[0]
    top_n = combos[:20]

    lines = [
        "---",
        "type: ensemble-optimize",
        f"week: {week_num}",
        f"date: {now.strftime('%Y-%m-%d')}",
        f"current_weights: MTM={current['mtm']}, MRB={current['mrb']}, MLB={current['mlb']}",
        f"suggested_weights: MTM={best.mtm}, MRB={best.mrb}, MLB={best.mlb}",
        "---",
        "",
        f"# Ensemble Optimizer — Week {week_num}",
        f"*Generated {now.strftime('%Y-%m-%d %H:%M')}*",
        "",
        "## Current Weights",
        "",
        "| Strategy | Weight |",
        "|----------|--------|",
        f"| MTM | {current['mtm']:.0%} |",
        f"| MRB | {current['mrb']:.0%} |",
        f"| MLB | {current['mlb']:.0%} |",
        "",
        "## Grid Search Results (Top 20)",
        "",
        "| # | MTM | MRB | MLB | Sharpe | PF | Win Rate | Exp Ret | Max DD | Score |",
        "|---|-----|-----|-----|--------|-----|----------|---------|--------|-------|",
    ]

    for i, c in enumerate(top_n, 1):
        marker = " **★**" if i == 1 else ""
        lines.append(
            f"| {i}{marker} | {c.mtm:.0%} | {c.mrb:.0%} | {c.mlb:.0%} "
            f"| {c.sharpe:.3f} | {c.profit_factor:.3f} | {c.win_rate:.1%} "
            f"| {c.expected_return:.3f} | {c.max_drawdown:.1f}% | {c.composite_score:.4f} |"
        )

    lines += [
        "",
        f"*Tested {len(combos):,} weight combinations (step={GRID_STEP})",
        "",
        "## Optimal Weights",
        "",
        f"- **MTM**: {best.mtm:.0%}  (was {current['mtm']:.0%})",
        f"- **MRB**: {best.mrb:.0%}  (was {current['mrb']:.0%})",
        f"- **MLB**: {best.mlb:.0%}  (was {current['mlb']:.0%})",
        "",
        f"- Sharpe: {best.sharpe:.3f}",
        f"- Profit Factor: {best.profit_factor:.3f}",
        f"- Win Rate: {best.win_rate:.1%}",
        f"- Max Drawdown: {best.max_drawdown:.1f}%",
        f"- Composite Score: {best.composite_score:.4f}",
        "",
        "## Regime-Dependent Weight Suggestions",
        "",
        "| Regime | MTM | MRB | MLB |",
        "|--------|-----|-----|-----|",
    ]

    for regime, w in regime_w.items():
        lines.append(
            f"| {regime.title()} | {w['mtm']:.0%} | {w['mrb']:.0%} | {w['mlb']:.0%} |"
        )

    lines += [
        "",
        "## Impact Analysis (Current → Optimal)",
        "",
        "| Metric | Current | Optimal | Delta |",
        "|--------|---------|---------|-------|",
        f"| Sharpe | {impact['current']['sharpe']:.3f} | {impact['optimal']['sharpe']:.3f} | {impact['deltas']['sharpe']:+.3f} |",
        f"| Profit Factor | {impact['current']['pf']:.3f} | {impact['optimal']['pf']:.3f} | {impact['deltas']['pf']:+.3f} |",
        f"| Win Rate | {impact['current']['win_rate']:.1%} | {impact['optimal']['win_rate']:.1%} | {impact['deltas']['win_rate']:+.1%} |",
        f"| Max Drawdown | {impact['current']['drawdown']:.1f}% | {impact['optimal']['drawdown']:.1f}% | {impact['deltas']['drawdown']:+.1f}% |",
        "",
        "## Overfitting Risk",
        "",
        f"- **Level**: {overfit['level'].upper()}",
        f"- **Reason**: {overfit['reason']}",
        f"- Distance (current→optimal): {overfit['distance']:.4f}",
        f"- Score range across all combos: {overfit['score_range']:.4f}",
        f"- Peakiness: {overfit['peakiness']:.4f}",
        "",
        "---",
        "",
        "> [!warning] Overfitting Caution",
        "> These weights are derived from backtest data on a specific historical window.",
        "> Always validate on out-of-sample data before live deployment.",
        "> Regime-dependent weights are heuristic estimates, not optimized values.",
    ]

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────
def run_optimizer(
    perfs: dict[str, StrategyPerformance] | None = None,
    week_num: int | None = None,
    write_vault: bool = True,
) -> dict[str, Any]:
    """Full pipeline: grid search → vault note → summary dict."""
    if perfs is None:
        perfs = _sample_performance_data()

    if week_num is None:
        week_num = datetime.now().isocalendar()[1]

    combos = grid_search(perfs)
    regime_w = regime_weights(perfs)
    overfit = overfitting_risk(combos, CURRENT_WEIGHTS)
    impact = impact_analysis(CURRENT_WEIGHTS, combos[0], perfs)

    note = generate_vault_note(
        week_num, CURRENT_WEIGHTS, combos, regime_w, overfit, impact
    )

    if write_vault:
        VAULT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = VAULT_DIR / f"week-{week_num}.md"
        out_path.write_text(note, encoding="utf-8")
        print(f"Vault note written: {out_path}")

    return {
        "week": week_num,
        "combos_tested": len(combos),
        "best": {
            "mtm": combos[0].mtm,
            "mrb": combos[0].mrb,
            "mlb": combos[0].mlb,
            "composite": combos[0].composite_score,
        },
        "overfitting": overfit,
        "impact": impact,
        "regime_weights": regime_w,
    }


# ── Sample Data (for testing) ───────────────────────────────────────────
def _sample_performance_data() -> dict[str, StrategyPerformance]:
    """Realistic sample performance data for testing the optimizer."""
    return {
        "mtm": StrategyPerformance(
            name="MTM",
            total_trades=312,
            win_rate=0.58,
            profit_factor=1.72,
            sharpe_ratio=1.45,
            max_drawdown_pct=12.3,
            avg_trade_pnl=18.50,
            expectancy=0.42,
            regime_scores={"trending": 0.85, "ranging": 0.40, "volatile": 0.55},
        ),
        "mrb": StrategyPerformance(
            name="MRB",
            total_trades=228,
            win_rate=0.63,
            profit_factor=1.55,
            sharpe_ratio=1.18,
            max_drawdown_pct=9.8,
            avg_trade_pnl=14.20,
            expectancy=0.38,
            regime_scores={"trending": 0.35, "ranging": 0.90, "volatile": 0.50},
        ),
        "mlb": StrategyPerformance(
            name="MLB",
            total_trades=186,
            win_rate=0.54,
            profit_factor=2.10,
            sharpe_ratio=1.62,
            max_drawdown_pct=15.1,
            avg_trade_pnl=24.80,
            expectancy=0.55,
            regime_scores={"trending": 0.70, "ranging": 0.45, "volatile": 0.75},
        ),
    }


if __name__ == "__main__":
    result = run_optimizer()
    print(json.dumps(result, indent=2, default=str))
