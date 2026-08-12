"""
Pipeline 10 (simple): Ensemble To Vault
Lightweight grid search + vault markdown output.
"""

import json
from datetime import datetime
from pathlib import Path

STRATEGIES = ["mtm", "mrb", "mlb"]

CURRENT_WEIGHTS = {"mtm": 0.40, "mrb": 0.25, "mlb": 0.35}

VAULT_DIR = Path(
    r"C:\Users\menum\Documents\ObsidianVault\Second Brain\03-resources\trading\ensemble"
)


# ── Sample strategy performance ──────────────────────────────────────────
STRATEGY_PERFS = {
    "mtm": {
        "trades": 312,
        "win_rate": 0.58,
        "pf": 1.72,
        "sharpe": 1.45,
        "max_dd": 12.3,
        "expectancy": 0.42,
    },
    "mrb": {
        "trades": 228,
        "win_rate": 0.63,
        "pf": 1.55,
        "sharpe": 1.18,
        "max_dd": 9.8,
        "expectancy": 0.38,
    },
    "mlb": {
        "trades": 186,
        "win_rate": 0.54,
        "pf": 2.10,
        "sharpe": 1.62,
        "max_dd": 15.1,
        "expectancy": 0.55,
    },
}


def score_combo(w: dict[str, float]) -> dict:
    """Evaluate one weight combination."""
    sharpe = sum(w[s] * STRATEGY_PERFS[s]["sharpe"] for s in STRATEGIES)
    pf = sum(w[s] * STRATEGY_PERFS[s]["pf"] for s in STRATEGIES)
    wr = sum(w[s] * STRATEGY_PERFS[s]["win_rate"] for s in STRATEGIES)
    dd = sum(w[s] * STRATEGY_PERFS[s]["max_dd"] for s in STRATEGIES)
    exp = sum(w[s] * STRATEGY_PERFS[s]["expectancy"] for s in STRATEGIES)
    composite = 0.4 * sharpe + 0.3 * pf + 0.2 * exp - 0.1 * dd
    return {
        "mtm": w["mtm"],
        "mrb": w["mrb"],
        "mlb": w["mlb"],
        "sharpe": round(sharpe, 4),
        "pf": round(pf, 4),
        "wr": round(wr, 4),
        "dd": round(dd, 4),
        "exp": round(exp, 4),
        "score": round(composite, 4),
    }


def grid_search(step: float = 0.10) -> list[dict]:
    """Grid search over weight combos summing to 1.0."""
    vals = [round(i * step, 2) for i in range(1, int(1.0 / step))]
    results = []
    for a in vals:
        for b in vals:
            c = round(1.0 - a - b, 2)
            if c < 0.05 or c > 0.95:
                continue
            results.append(score_combo({"mtm": a, "mrb": b, "mlb": c}))
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def build_markdown(week: int, combos: list[dict]) -> str:
    """Generate vault-compatible markdown."""
    best = combos[0]
    now = datetime.now()

    md = f"""---
type: ensemble-optimize
week: {week}
date: {now.strftime('%Y-%m-%d')}
current_weights: MTM=40%, MRB=25%, MLB=35%
suggested_weights: MTM={best['mtm']:.0%}, MRB={best['mrb']:.0%}, MLB={best['mlb']:.0%}
---

# Ensemble Weights — Week {week}

## Current Weights

| Strategy | Weight |
|----------|--------|
| MTM | {CURRENT_WEIGHTS['mtm']:.0%} |
| MRB | {CURRENT_WEIGHTS['mrb']:.0%} |
| MLB | {CURRENT_WEIGHTS['mlb']:.0%} |

## Grid Search Results (Top 15)

| # | MTM | MRB | MLB | Sharpe | PF | Win% | ExpRet | Drawdown | Score |
|---|-----|-----|-----|--------|-----|------|--------|----------|-------|
"""
    for i, c in enumerate(combos[:15], 1):
        star = " **★**" if i == 1 else ""
        md += (
            f"| {i}{star} | {c['mtm']:.0%} | {c['mrb']:.0%} | {c['mlb']:.0%} "
            f"| {c['sharpe']:.3f} | {c['pf']:.3f} | {c['wr']:.1%} "
            f"| {c['exp']:.3f} | {c['dd']:.1f}% | {c['score']:.4f} |\n"
        )

    md += f"""
## Optimal

- **MTM**: {best['mtm']:.0%} (was {CURRENT_WEIGHTS['mtm']:.0%})
- **MRB**: {best['mrb']:.0%} (was {CURRENT_WEIGHTS['mrb']:.0%})
- **MLB**: {best['mlb']:.0%} (was {CURRENT_WEIGHTS['mlb']:.0%})

Sharpe {best['sharpe']:.3f} | PF {best['pf']:.3f} | Win {best['wr']:.1%} | DD {best['dd']:.1f}%

## Sample Performance Data Used

| Strategy | Trades | Win% | PF | Sharpe | Max DD |
|----------|--------|------|-----|--------|--------|
| MTM | {STRATEGY_PERFS['mtm']['trades']} | {STRATEGY_PERFS['mtm']['win_rate']:.0%} | {STRATEGY_PERFS['mtm']['pf']:.2f} | {STRATEGY_PERFS['mtm']['sharpe']:.2f} | {STRATEGY_PERFS['mtm']['max_dd']:.1f}% |
| MRB | {STRATEGY_PERFS['mrb']['trades']} | {STRATEGY_PERFS['mrb']['win_rate']:.0%} | {STRATEGY_PERFS['mrb']['pf']:.2f} | {STRATEGY_PERFS['mrb']['sharpe']:.2f} | {STRATEGY_PERFS['mrb']['max_dd']:.1f}% |
| MLB | {STRATEGY_PERFS['mlb']['trades']} | {STRATEGY_PERFS['mlb']['win_rate']:.0%} | {STRATEGY_PERFS['mlb']['pf']:.2f} | {STRATEGY_PERFS['mlb']['sharpe']:.2f} | {STRATEGY_PERFS['mlb']['max_dd']:.1f}% |

---
> [!warning] Overfitting
> Weights derived from backtest history. Validate on out-of-sample data before live use.
"""
    return md


def main():
    week = datetime.now().isocalendar()[1]
    combos = grid_search()
    md = build_markdown(week, combos)

    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    out = VAULT_DIR / f"week-{week}.md"
    out.write_text(md, encoding="utf-8")

    print(f"Written: {out}")
    print(f"Combos tested: {len(combos)}")
    print(
        f"Best: MTM={combos[0]['mtm']:.0%} MRB={combos[0]['mrb']:.0%} MLB={combos[0]['mlb']:.0%} -> score={combos[0]['score']:.4f}"
    )
    print(json.dumps(combos[0], indent=2))


if __name__ == "__main__":
    main()
