"""
DSR + Label Shuffling (Fast) — Uses logistic regression for null distribution.
"""
import os, sys, json, warnings, time
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
BASE = Path(__file__).parent.parent
WF_DIR = BASE / "artifacts" / "walk_forward"
FEAT_DIR = BASE / "artifacts" / "features_v2"

# Import DSR directly
import importlib.util
spec = importlib.util.spec_from_file_location("ds", str(BASE / "validation" / "deflated_sharpe.py"))
ds_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ds_mod)

def run_dsr_and_shuffle(symbol="XAUUSD", freq="H1", n_perms=10000):
    t0 = time.time()
    
    print("=" * 60)
    print(f"DSR + LABEL SHUFFLING: {symbol} @ {freq} ({n_perms} perms)")
    print("=" * 60)
    
    # --- DSR ---
    wf_path = WF_DIR / f"wf_{symbol}_{freq}_500w_200t_conf0.55.json"
    if wf_path.exists():
        with open(wf_path) as f:
            wf = json.load(f)
        fold_sharpes = [fold["sharpe_ratio"] for fold in wf["folds"]]
        observed_sharpe = np.mean(fold_sharpes)
        n_obs = sum(fold["n_trades"] for fold in wf["folds"])
    else:
        # Fallback: use proper OOS result
        observed_sharpe = 0.0
        n_obs = 500
    
    n_trials = 100
    dsr = ds_mod.deflated_sharpe_ratio(observed_sharpe, n_trials, n_obs)
    min_btl = ds_mod.min_backtest_length(observed_sharpe, n_trials, current_observations=n_obs)
    
    print(f"\n--- DEFLATED SHARPE RATIO ---")
    print(f"  Observed Sharpe: {observed_sharpe:.4f}")
    print(f"  N trials: {n_trials}")
    print(f"  Expected max under null: {dsr.multiple_testing_adjustment:.4f}")
    print(f"  Prob alpha (false positive): {dsr.probability_alpha:.4f}")
    print(f"  Passes: {dsr.passes_threshold}")
    print(f"  Min observations needed: {min_btl.min_observations}")
    print(f"  Current observations: {n_obs}")
    print(f"  Sufficient: {min_btl.sufficient}")
    
    # --- LABEL SHUFFLING (fast: logistic regression) ---
    print(f"\n--- LABEL SHUFFLING ({n_perms} permutations) ---")
    
    path = FEAT_DIR / f"features_{symbol}_{freq}.parquet"
    df = pd.read_parquet(path)
    exclude = {"target", "target_return", "symbol", "freq", "target_3class"}
    feature_cols = [c for c in df.columns if c not in exclude
                    and df[c].dtype in (np.float64, np.float32, np.int64, np.int32)]
    
    X = df[feature_cols].fillna(0).values
    y = df["target"].values
    returns = df["target_return"].values
    closes = df["close"].values
    X, y, returns, closes = X[:-5], y[:-5], returns[:-5], closes[:-5]
    
    split = int(len(X) * 0.6)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    r_test = returns[split:]
    c_test = closes[split:]
    
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)
    
    # Real model
    real_model = LogisticRegression(max_iter=1000, random_state=42)
    real_model.fit(X_train_s, y_train)
    real_preds = real_model.predict(X_test_s)
    real_conf = np.max(real_model.predict_proba(X_test_s), axis=1)
    
    spread_cost = 0.000375
    slippage_p90 = 0.000250
    cost = (spread_cost + slippage_p90) * np.mean(c_test)
    
    mask = real_conf >= 0.55
    direction = 2 * real_preds.astype(float) - 1
    real_net = (direction[mask] * r_test[mask] * c_test[mask]).sum() - cost * mask.sum()
    
    print(f"  Real model: accuracy={real_model.score(X_test_s, y_test):.4f}, trades={mask.sum()}, net=${real_net:+,.2f}")
    
    # Null distribution
    np.random.seed(42)
    null_nets = np.zeros(n_perms)
    
    for i in range(n_perms):
        shuffled_y = np.random.permutation(y_train)
        null_model = LogisticRegression(max_iter=500, random_state=42)
        null_model.fit(X_train_s, shuffled_y)
        null_preds = null_model.predict(X_test_s)
        null_conf = np.max(null_model.predict_proba(X_test_s), axis=1)
        null_mask = null_conf >= 0.55
        null_dir = 2 * null_preds.astype(float) - 1
        null_nets[i] = (null_dir[null_mask] * r_test[null_mask] * c_test[null_mask]).sum() - cost * null_mask.sum()
        
        if (i + 1) % 2000 == 0:
            elapsed = time.time() - t0
            print(f"  Permutation {i+1}/{n_perms} ({elapsed:.0f}s)")
    
    p_value = (null_nets >= real_net).mean()
    
    print(f"\n  Null distribution:")
    print(f"    Mean: ${null_nets.mean():+,.2f}")
    print(f"    Std: ${null_nets.std():,.2f}")
    print(f"    95th pct: ${np.percentile(null_nets, 95):+,.2f}")
    print(f"    99th pct: ${np.percentile(null_nets, 99):+,.2f}")
    print(f"    Max: ${null_nets.max():+,.2f}")
    print(f"    Real: ${real_net:+,.2f}")
    print(f"\n  p-value: {p_value:.4f}")
    
    if p_value < 0.05:
        print(f"  SHUFFLE: PASS (p<0.05)")
    elif p_value < 0.10:
        print(f"  SHUFFLE: MARGINAL (p<0.10)")
    else:
        print(f"  SHUFFLE: FAIL (p>=0.10)")
    
    elapsed = time.time() - t0
    
    # --- COMBINED VERDICT ---
    print(f"\n{'='*60}")
    print(f"COMBINED VERDICT: {symbol} @ {freq}")
    print(f"{'='*60}")
    print(f"  DSR passes: {dsr.passes_threshold}")
    print(f"  DSR p-value: {dsr.probability_alpha:.4f}")
    print(f"  Shuffle p-value: {p_value:.4f}")
    print(f"  Time: {elapsed:.0f}s")
    
    if dsr.passes_threshold and p_value < 0.05:
        print(f"  >>> EDGE CONFIRMED <<<")
    elif p_value < 0.10:
        print(f"  >>> EDGE MARGINAL <<<")
    else:
        print(f"  >>> NO CONFIRMED EDGE <<<")
    
    # Save results
    results = {
        "symbol": symbol, "freq": freq,
        "dsr": {"observed_sharpe": observed_sharpe, "prob_alpha": dsr.probability_alpha,
                "passes": dsr.passes_threshold, "min_observations": min_btl.min_observations},
        "shuffle": {"real_net": float(real_net), "p_value": float(p_value),
                    "null_mean": float(null_nets.mean()), "null_std": float(null_nets.std()),
                    "n_perms": n_perms},
        "elapsed_seconds": elapsed,
    }
    out_path = WF_DIR / f"dsr_shuffle_{symbol}_{freq}.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Saved: {out_path}")


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"
    freq = sys.argv[2] if len(sys.argv) > 2 else "H1"
    n_perms = int(sys.argv[3]) if len(sys.argv) > 3 else 10000
    run_dsr_and_shuffle(symbol, freq, n_perms)
