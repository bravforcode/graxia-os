"""
Apply DSR/PBO to Walk-Forward Results + Label Shuffling (10,000 permutations)

Tests whether walk-forward Sharpe ratios survive deflation for multiple testing.
"""
import os, sys, json, warnings
import numpy as np
import pandas as pd
from pathlib import Path

warnings.filterwarnings("ignore")
BASE = Path(__file__).parent.parent
WF_DIR = BASE / "artifacts" / "walk_forward"
FEAT_DIR = BASE / "artifacts" / "features_v2"
sys.path.insert(0, str(BASE))
# Import directly to avoid __init__.py chain issues
import importlib.util
spec = importlib.util.spec_from_file_location("deflated_sharpe", str(BASE / "validation" / "deflated_sharpe.py"))
ds_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ds_mod)
deflated_sharpe_ratio = ds_mod.deflated_sharpe_ratio
min_backtest_length = ds_mod.min_backtest_length

def apply_dsr(symbol: str = "XAUUSD", freq: str = "H1"):
    """Apply DSR to walk-forward results."""
    print("=" * 60)
    print(f"DSR/PBO ANALYSIS: {symbol} @ {freq}")
    print("=" * 60)
    
    # Load walk-forward results
    wf_path = WF_DIR / f"wf_{symbol}_{freq}_500w_200t_conf0.55.json"
    if not wf_path.exists():
        print(f"  Walk-forward results not found: {wf_path}")
        return
    
    with open(wf_path) as f:
        wf = json.load(f)
    
    # Extract fold Sharpe ratios
    fold_sharpes = [fold["sharpe_ratio"] for fold in wf["folds"]]
    fold_nets = [fold["net_pnl"] for fold in wf["folds"]]
    fold_trades = [fold["n_trades"] for fold in wf["folds"]]
    
    print(f"\nWalk-Forward Summary:")
    print(f"  Folds: {len(fold_sharpes)}")
    print(f"  Sharpe range: {min(fold_sharpes):.2f} to {max(fold_sharpes):.2f}")
    print(f"  Mean Sharpe: {np.mean(fold_sharpes):.2f}")
    print(f"  Net PnL range: ${min(fold_nets):+,.2f} to ${max(fold_nets):+,.2f}")
    print(f"  Total net: ${sum(fold_nets):+,.2f}")
    
    # DSR for aggregate (assuming we tested ~100 strategy configurations)
    aggregate_sharpe = wf["aggregate"]["total_net"] / (np.std(fold_nets) * np.sqrt(len(fold_nets))) if np.std(fold_nets) > 0 else 0
    
    # Use mean fold Sharpe as the observed Sharpe
    observed_sharpe = np.mean(fold_sharpes)
    n_observations = sum(fold_trades)
    n_trials = 100  # Conservative: assume we tested ~100 configurations
    
    print(f"\n--- DEFLATED SHARPE RATIO ---")
    print(f"  Observed Sharpe: {observed_sharpe:.4f}")
    print(f"  N trials (assumed): {n_trials}")
    print(f"  N observations: {n_observations}")
    
    dsr = deflated_sharpe_ratio(
        observed_sharpe=observed_sharpe,
        n_trials=n_trials,
        n_observations=n_observations,
    )
    
    print(f"  Expected max Sharpe under null: {dsr.multiple_testing_adjustment:.4f}")
    print(f"  Probability alpha (false positive): {dsr.probability_alpha:.4f}")
    print(f"  Passes threshold: {dsr.passes_threshold}")
    
    if dsr.passes_threshold:
        print(f"  DSR VERDICT: PASS — Edge survives multiple testing correction")
    else:
        print(f"  DSR VERDICT: FAIL — Edge does NOT survive multiple testing correction")
    
    # Min backtest length
    print(f"\n--- MINIMUM BACKTEST LENGTH ---")
    min_btl = min_backtest_length(
        observed_sharpe=observed_sharpe,
        n_trials=n_trials,
        current_observations=n_observations,
    )
    print(f"  Minimum observations needed: {min_btl.min_observations}")
    print(f"  Current observations: {n_observations}")
    print(f"  Sufficient: {min_btl.sufficient}")
    
    if not min_btl.sufficient:
        print(f"  Need {min_btl.min_observations - n_observations} more observations for significance")
    
    return dsr


def label_shuffling(symbol: str = "XAUUSD", freq: str = "H1", n_perms: int = 10000):
    """Run label shuffling with 10,000 permutations."""
    print(f"\n{'='*60}")
    print(f"LABEL SHUFFLING: {symbol} @ {freq} ({n_perms} permutations)")
    print(f"{'='*60}")
    
    # Load features
    path = FEAT_DIR / f"features_{symbol}_{freq}.parquet"
    df = pd.read_parquet(path)
    
    exclude = {"target", "target_return", "symbol", "freq", "target_3class"}
    feature_cols = [c for c in df.columns if c not in exclude
                    and df[c].dtype in (np.float64, np.float32, np.int64, np.int32)]
    
    X = df[feature_cols].fillna(0).values
    y = df["target"].values
    returns = df["target_return"].values
    closes = df["close"].values
    
    # Remove last 5 rows
    X, y, returns, closes = X[:-5], y[:-5], returns[:-5], closes[:-5]
    
    # Split: 60% train, 40% test
    split = int(len(X) * 0.6)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    r_test = returns[split:]
    c_test = closes[split:]
    
    print(f"  Train: {len(X_train)}, Test: {len(X_test)}")
    
    # Train model
    import xgboost as xgb
    params = {
        "n_estimators": 100, "max_depth": 5, "learning_rate": 0.1,
        "subsample": 0.8, "colsample_bytree": 0.8, "random_state": 42,
        "eval_metric": "logloss", "verbosity": 0,
    }
    
    model = xgb.XGBClassifier(**params)
    model.fit(X_train, y_train)
    
    # Real predictions
    real_preds = model.predict(X_test)
    real_conf = np.max(model.predict_proba(X_test), axis=1)
    
    # Real PnL
    spread_cost = 0.000375
    slippage_p90 = 0.000250
    cost = (spread_cost + slippage_p90) * np.mean(c_test)
    
    mask = real_conf >= 0.55
    direction = 2 * real_preds.astype(float) - 1
    dir_mask = direction[mask]
    rets = r_test[mask]
    closes_mask = c_test[mask]
    real_net = (dir_mask * rets * closes_mask).sum() - cost * mask.sum()
    
    print(f"\n  Real net PnL: ${real_net:+,.2f}")
    print(f"  Real trades: {mask.sum()}")
    
    # Null distribution
    null_nets = []
    for i in range(n_perms):
        shuffled_y = np.random.permutation(y_train)
        model_null = xgb.XGBClassifier(**params)
        model_null.fit(X_train, shuffled_y)
        
        null_preds = model_null.predict(X_test)
        null_conf = np.max(model_null.predict_proba(X_test), axis=1)
        null_mask = null_conf >= 0.55
        null_dir = 2 * null_preds.astype(float) - 1
        null_dm = null_dir[null_mask]
        null_r = r_test[null_mask]
        null_c = c_test[null_mask]
        null_net = (null_dm * null_r * null_c).sum() - cost * null_mask.sum()
        null_nets.append(null_net)
        
        if (i + 1) % 1000 == 0:
            print(f"  Permutation {i+1}/{n_perms}...")
    
    null_nets = np.array(null_nets)
    p_value = (null_nets >= real_net).mean()
    
    print(f"\n  Null distribution:")
    print(f"    Mean: ${null_nets.mean():+,.2f}")
    print(f"    Std: ${null_nets.std():,.2f}")
    print(f"    95th percentile: ${np.percentile(null_nets, 95):+,.2f}")
    print(f"    99th percentile: ${np.percentile(null_nets, 99):+,.2f}")
    
    print(f"\n  p-value: {p_value:.4f}")
    
    if p_value < 0.05:
        print(f"  SHUFFLE VERDICT: PASS — Real PnL significantly above null (p<0.05)")
    elif p_value < 0.10:
        print(f"  SHUFFLE VERDICT: MARGINAL — Real PnL marginally above null (p<0.10)")
    else:
        print(f"  SHUFFLE VERDICT: FAIL — Real PnL NOT significantly above null (p>=0.10)")
    
    return {"real_net": real_net, "p_value": p_value, "null_mean": null_nets.mean()}


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"
    freq = sys.argv[2] if len(sys.argv) > 2 else "H1"
    n_perms = int(sys.argv[3]) if len(sys.argv) > 3 else 10000
    
    dsr = apply_dsr(symbol, freq)
    shuffle = label_shuffling(symbol, freq, n_perms)
    
    print(f"\n{'='*60}")
    print(f"COMBINED VERDICT: {symbol} @ {freq}")
    print(f"{'='*60}")
    print(f"  DSR passes: {dsr.passes_threshold if dsr else 'N/A'}")
    print(f"  Shuffle p-value: {shuffle['p_value']:.4f}")
    
    if dsr and dsr.passes_threshold and shuffle['p_value'] < 0.05:
        print(f"  OVERALL: EDGE CONFIRMED")
    else:
        print(f"  OVERALL: NO CONFIRMED EDGE")
