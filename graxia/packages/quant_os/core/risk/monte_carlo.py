"""
Bootstrap equity path simulation for Monte Carlo risk-of-ruin analysis.

Run this BEFORE every lot increase (Gate 5, 6, 6b...), using the most recent
>=300 trades' actual P&L distribution (paper or live -- whichever the gate is checking).
Never use hypothetical EV/trade tables as simulation input once you have real trades.
"""
import numpy as np


def bootstrap_equity_paths(
    trade_pnls: np.ndarray,
    n_sims: int = 10_000,
    n_trades_forward: int = 540,
    starting_balance: float = 5000.0,
    kill_switch_balance: float = 4500.0,
    lot_multiplier: float = 1.0,
) -> dict:
    """
    Bootstrap equity paths by resampling historical per-trade PnLs.

    Returns a dict with prob_ruin (P of hitting kill_switch within horizon),
    ending balance percentiles, max drawdown percentiles, and optional raw paths.
    """
    if len(trade_pnls) == 0:
        raise ValueError("trade_pnls must be non-empty")

    n = len(trade_pnls)
    paths = np.zeros((n_sims, n_trades_forward))
    for i in range(n_sims):
        sampled = np.random.choice(trade_pnls, size=n_trades_forward, replace=True) * lot_multiplier
        paths[i] = starting_balance + np.cumsum(sampled)

    ruin_mask = (paths <= kill_switch_balance).any(axis=1)
    cummax = np.maximum.accumulate(paths, axis=1)
    drawdowns = (cummax - paths) / np.maximum(cummax, 1e-9)
    max_dd_pct = drawdowns.max(axis=1)

    return {
        "prob_ruin": float(ruin_mask.mean()),
        "median_ending_balance": float(np.median(paths[:, -1])),
        "p5_ending_balance": float(np.percentile(paths[:, -1], 5)),
        "p95_ending_balance": float(np.percentile(paths[:, -1], 95)),
        "median_max_dd_pct": float(np.median(max_dd_pct)),
        "p95_max_dd_pct": float(np.percentile(max_dd_pct, 95)),
        "equity_paths": paths,
    }


def plot_equity_paths(paths: np.ndarray, title: str = "Monte Carlo Equity Paths",
                      save_path: str | None = None) -> None:
    """
    Plot median/p5/p95 equity path bands from bootstrap simulation.

    Requires matplotlib. If not installed, prints a message and returns.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("[monte_carlo] matplotlib not installed -- skipping plot")
        return

    n = paths.shape[1]
    x = range(n)
    median = np.median(paths, axis=0)
    p5 = np.percentile(paths, 5, axis=0)
    p95 = np.percentile(paths, 95, axis=0)

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(x, median, color="black", linewidth=1.5, label="Median")
    ax.fill_between(x, p5, p95, alpha=0.3, color="steelblue", label="P5–P95")
    ax.axhline(y=median[0], color="gray", linestyle="--", linewidth=0.8, label="Starting balance")
    ax.set_xlabel("Trade #")
    ax.set_ylabel("Equity ($)")
    ax.set_title(title)
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    else:
        plt.show()
    plt.close(fig)
