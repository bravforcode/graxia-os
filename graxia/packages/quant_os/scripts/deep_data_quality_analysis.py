"""
Deep Data Quality & Feature Analysis for quant_os features_v3
================================================================
Checks:
  1. Feature-Target Correlation Deep Dive
  2. Feature Importance Sanity Check (swing_high)
  3. Macro Feature Analysis
  4. Walk-Forward Test (5-fold)
  5. Regime-Conditional Analysis
  6. Cross-Asset Analysis
"""

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import joblib
import os
from scipy import stats

# Paths
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FV3 = os.path.join(BASE, "artifacts", "features_v3")
MODELS = os.path.join(BASE, "artifacts", "models")

def load(symbol):
    path = os.path.join(FV3, f"features_v3_{symbol}_M15.parquet")
    return pd.read_parquet(path)

def load_model(symbol):
    path = os.path.join(MODELS, f"{symbol}_direction.pkl")
    return joblib.load(path)

# Feature columns (exclude OHLCV + time)
def feature_cols(df):
    skip = {"time", "open", "high", "low", "close", "volume"}
    return [c for c in df.columns if c not in skip]

# ============================================================
# SECTION 1: Feature-Target Correlation Deep Dive
# ============================================================
def section1_correlations(df, symbol):
    print(f"\n{'='*70}")
    print(f"  SECTION 1: Feature-Target Correlation — {symbol}")
    print(f"{'='*70}")

    close = df["close"].values
    fcols = feature_cols(df)

    # Compute target labels
    # Next-bar direction (1 bar ahead)
    dir_1 = (np.roll(close, -1) > close).astype(float)
    dir_1[-1] = np.nan

    # Next-5-bar direction
    dir_5 = (np.roll(close, -5) > close).astype(float)
    dir_5[-5:] = np.nan

    # Next-20-bar direction
    dir_20 = (np.roll(close, -20) > close).astype(float)
    dir_20[-20:] = np.nan

    # Next-bar return magnitude
    ret_1 = (np.roll(close, -1) - close) / close
    ret_1[-1] = np.nan

    results = []
    for col in fcols:
        vals = df[col].values.astype(float)
        mask = ~(np.isnan(vals) | np.isnan(dir_1) | np.isnan(dir_5) | np.isnan(dir_20) | np.isnan(ret_1))

        if mask.sum() < 100:
            continue

        v = vals[mask]
        d1 = dir_1[mask]
        d5 = dir_5[mask]
        d20 = dir_20[mask]
        r1 = ret_1[mask]

        # Point-biserial correlation (continuous vs binary)
        c1, _ = stats.pointbiserialr(d1, v)
        c5, _ = stats.pointbiserialr(d5, v)
        c20, _ = stats.pointbiserialr(d20, v)
        cr, _ = stats.pearsonr(r1, v)

        results.append({
            "feature": col,
            "corr_dir1": c1,
            "corr_dir5": c5,
            "corr_dir20": c20,
            "corr_magnitude": cr,
            "abs_max": max(abs(c1), abs(c5), abs(c20), abs(cr)),
            "n_valid": int(mask.sum()),
        })

    rdf = pd.DataFrame(results).sort_values("abs_max", ascending=False)

    print(f"\nTotal features analyzed: {len(rdf)}")
    print("\n--- Top 20 features by max |correlation| ---")
    print(f"{'Feature':<35} {'Dir1':>7} {'Dir5':>7} {'Dir20':>7} {'Mag':>8} {'AbsMax':>7}")
    print("-" * 80)

    for _, row in rdf.head(20).iterrows():
        print(f"{row['feature']:<35} {row['corr_dir1']:>7.4f} {row['corr_dir5']:>7.4f} {row['corr_dir20']:>7.4f} {row['corr_magnitude']:>8.5f} {row['abs_max']:>7.4f}")

    # Flag useful and leakage
    useful = rdf[rdf["abs_max"] > 0.1]
    leakage = rdf[rdf["abs_max"] > 0.3]

    print(f"\n--- Potentially Useful (|corr| > 0.1): {len(useful)} features ---")
    for _, row in useful.iterrows():
        print(f"  {row['feature']:<35} max|corr| = {row['abs_max']:.4f}")

    print(f"\n--- POTENTIAL LEAKAGE (|corr| > 0.3): {len(leakage)} features ---")
    if len(leakage) > 0:
        for _, row in leakage.iterrows():
            print(f"  *** {row['feature']:<35} max|corr| = {row['abs_max']:.4f} ***")
    else:
        print("  None found.")

    return rdf

# ============================================================
# SECTION 2: Feature Importance Sanity Check (swing_high)
# ============================================================
def section2_swing_sanity(df, symbol):
    print(f"\n{'='*70}")
    print(f"  SECTION 2: swing_high Sanity Check — {symbol}")
    print(f"{'='*70}")

    close = df["close"].values
    ret_1 = np.roll(close, -1) - close

    # swing_high distribution
    sh = df["swing_high"].values.astype(float)
    sl = df["swing_low"].values.astype(float)

    mask_sh = ~np.isnan(sh)
    mask_sl = ~np.isnan(sl)
    mask_all = ~(np.isnan(sh) | np.isnan(sl))

    n_sh_true = (sh[mask_all] == True).sum() if sh.dtype == bool else (sh[mask_all] == 1).sum()
    n_sl_true = (sl[mask_all] == True).sum() if sl.dtype == bool else (sl[mask_all] == 1).sum()
    n_total = mask_all.sum()

    print(f"\nswing_high=True count: {n_sh_true} ({100*n_sh_true/n_total:.1f}%)")
    print(f"swing_low=True count:  {n_sl_true} ({100*n_sl_true/n_total:.1f}%)")
    print(f"Neither:               {n_total - n_sh_true - n_sl_true} ({100*(n_total - n_sh_true - n_sl_true)/n_total:.1f}%)")

    # After swing_high, what's the next-bar return distribution?
    # Need to shift: bar t has swing_high=True, look at bar t+1 return
    ret_shifted = np.roll(ret_1, -1)  # ret_shifted[t] = close[t+2] - close[t+1], WRONG
    # Actually ret_1[t] = close[t+1] - close[t]
    # So after swing_high at bar t, next-bar return = ret_1[t]

    sh_true_mask = sh == True
    sl_true_mask = sl == True
    neither_mask = (~sh_true_mask) & (~sl_true_mask) & mask_all

    # Filter valid
    valid = ~np.isnan(ret_1) & mask_all

    ret_sh = ret_1[sh_true_mask & valid]
    ret_sl = ret_1[sl_true_mask & valid]
    ret_neither = ret_1[neither_mask & valid]

    print("\n--- Next-bar return distribution after swing_high ---")
    print(f"  Count: {len(ret_sh)}")
    print(f"  Mean:  {np.mean(ret_sh):.4f}")
    print(f"  Std:   {np.std(ret_sh):.4f}")
    print(f"  Median:{np.median(ret_sh):.4f}")
    pct_up = (ret_sh > 0).sum() / len(ret_sh) * 100
    print(f"  Pct up: {pct_up:.1f}%")

    print("\n--- Next-bar return distribution after swing_low ---")
    print(f"  Count: {len(ret_sl)}")
    print(f"  Mean:  {np.mean(ret_sl):.4f}")
    print(f"  Std:   {np.std(ret_sl):.4f}")
    print(f"  Median:{np.median(ret_sl):.4f}")
    pct_up_sl = (ret_sl > 0).sum() / len(ret_sl) * 100
    print(f"  Pct up: {pct_up_sl:.1f}%")

    print("\n--- Next-bar return distribution (baseline / neither) ---")
    print(f"  Count: {len(ret_neither)}")
    print(f"  Mean:  {np.mean(ret_neither):.4f}")
    print(f"  Std:   {np.std(ret_neither):.4f}")
    print(f"  Median:{np.median(ret_neither):.4f}")
    pct_up_base = (ret_neither > 0).sum() / len(ret_neither) * 100
    print(f"  Pct up: {pct_up_base:.1f}%")

    # Statistical tests
    if len(ret_sh) > 10 and len(ret_neither) > 10:
        tstat_sh, pval_sh = stats.mannwhitneyu(ret_sh, ret_neither, alternative="two-sided")
        print(f"\n  Mann-Whitney U test (swing_high vs baseline): U={tstat_sh:.1f}, p={pval_sh:.4f}")
        if pval_sh < 0.05:
            print(f"  -> SIGNIFICANT difference (p < 0.05): swing_high bars have {'higher' if np.mean(ret_sh) > np.mean(ret_neither) else 'LOWER'} next-bar returns")
        else:
            print("  -> No significant difference from baseline")

    # Is it just proxy for "price at extreme"?
    print("\n--- swing_high as 'price at extreme' proxy ---")
    print("  Interpretation: swing_high=True means price just made a local high.")
    print("  If model assigns 32% importance to it, it may be learning:")
    print("  a) Reversal patterns after local highs (useful signal)")
    print("  b) Or just overfitting to a binary indicator that's correlated with recent volatility")

    return {
        "swing_high_count": int(n_sh_true),
        "swing_high_pct_up_next": pct_up,
        "swing_low_count": int(n_sl_true),
        "swing_low_pct_up_next": pct_up_sl,
        "baseline_pct_up_next": pct_up_base,
    }

# ============================================================
# SECTION 3: Macro Feature Analysis
# ============================================================
def section3_macro(df, symbol):
    print(f"\n{'='*70}")
    print(f"  SECTION 3: Macro Feature Analysis — {symbol}")
    print(f"{'='*70}")

    macro_cols = [c for c in df.columns if c.startswith("fred_") or c.startswith("cot_")]
    print(f"\nMacro features found: {macro_cols}")

    results = {}
    for col in macro_cols:
        vals = df[col].values.astype(float)
        total = len(vals)
        n_valid = (~np.isnan(vals)).sum()
        n_unique = pd.Series(vals[~np.isnan(vals)]).nunique()

        # Count how many times the value actually changes
        valid_series = pd.Series(vals[~np.isnan(vals)])
        n_changes = (valid_series.diff() != 0).sum()

        pct_valid = 100 * n_valid / total
        pct_static = 100 * (1 - n_changes / max(n_valid - 1, 1))

        # Time span
        valid_idx = np.where(~np.isnan(vals))[0]
        if len(valid_idx) > 1:
            bars_span = valid_idx[-1] - valid_idx[0]
            days_span = bars_span / (24 * 4)  # M15 bars to days
        else:
            days_span = 0

        results[col] = {
            "pct_valid": pct_valid,
            "n_unique": n_unique,
            "n_changes": n_changes,
            "pct_static": pct_static,
            "days_span": days_span,
        }

        print(f"\n  {col}:")
        print(f"    Valid: {pct_valid:.1f}% | Unique values: {n_unique} | Changes: {n_changes} | Static: {pct_static:.1f}% | Span: {days_span:.0f} days")

    # Categorize
    static_features = [k for k, v in results.items() if v["pct_static"] > 99]
    varying_features = [k for k, v in results.items() if v["pct_static"] < 90]

    print("\n--- Summary ---")
    print(f"  Static (>99% unchanged): {len(static_features)}")
    for f in static_features:
        print(f"    {f}")
    print(f"  Actually varying (<90% unchanged): {len(varying_features)}")
    for f in varying_features:
        print(f"    {f}")
    print("  These static features are forward-filled daily data repeated 96x per day in M15.")
    print("  They carry NO intraday information. Any 'importance' from these is spurious.")

    return results

# ============================================================
# SECTION 4: Walk-Forward Test (5-fold)
# ============================================================
def section4_walkforward(df, symbol):
    print(f"\n{'='*70}")
    print(f"  SECTION 4: Walk-Forward Test (5-fold) — {symbol}")
    print(f"{'='*70}")

    from sklearn.metrics import accuracy_score

    close = df["close"].values
    fcols = feature_cols(df)

    # Target: next-bar direction
    target = (np.roll(close, -1) > close).astype(float)
    target[-1] = np.nan

    X = df[fcols].copy()
    y = pd.Series(target)

    # Drop rows with NaN target
    valid_mask = ~y.isna()
    X = X[valid_mask]
    y = y[valid_mask]

    # Also drop rows with NaN features (use median fill)
    X = X.fillna(X.median())

    n = len(X)
    train_size = int(n * 0.7)
    test_size = n - train_size

    # 5 walk-forward folds (non-overlapping test windows)
    n_folds = 5
    fold_size = test_size // n_folds
    min_train = 5000

    print(f"\nTotal samples: {n}")
    print(f"Fold test size: {fold_size}")
    print()

    results = []
    for i in range(n_folds):
        test_start = train_size + i * fold_size
        test_end = min(test_start + fold_size, n)

        if test_end <= test_start:
            break

        train_end = test_start
        # Ensure enough training data
        train_start = max(0, train_end - 50000)  # cap training window

        X_train = X.iloc[train_start:train_end].values
        y_train = y.iloc[train_start:train_end].values
        X_test = X.iloc[test_start:test_end].values
        y_test = y.iloc[test_start:test_end].values

        if len(X_train) < min_train or len(X_test) < 100:
            continue

        # Train XGBoost
        from xgboost import XGBClassifier
        model = XGBClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            use_label_encoder=False,
            eval_metric="logloss",
            verbosity=0,
            random_state=42,
        )
        model.fit(X_train, y_train)

        train_pred = model.predict(X_train)
        test_pred = model.predict(X_test)

        train_acc = accuracy_score(y_train, train_pred)
        test_acc = accuracy_score(y_test, test_pred)

        # Simulate simple long/short strategy
        # Signal: model.predict = 1 -> long, 0 -> short
        test_close = close[valid_mask.values][test_start:test_end]
        signal = np.where(test_pred == 1, 1, -1)
        actual_dir = np.where(y_test == 1, 1, -1)
        correct = (signal == actual_dir).astype(float)
        returns = np.diff(test_close) / test_close[:-1]
        strategy_returns = signal[:-1] * returns

        # Sharpe (annualized from M15 returns)
        if len(strategy_returns) > 1 and np.std(strategy_returns) > 0:
            sharpe = np.mean(strategy_returns) / np.std(strategy_returns) * np.sqrt(96 * 252)
        else:
            sharpe = 0.0

        total_return = np.sum(strategy_returns) * 100

        # Feature importance for this fold
        fi = dict(zip(fcols, model.feature_importances_))
        top_feat = sorted(fi.items(), key=lambda x: -x[1])[:3]

        results.append({
            "fold": i + 1,
            "train_size": len(X_train),
            "test_size": len(X_test),
            "train_acc": train_acc,
            "test_acc": test_acc,
            "sharpe": sharpe,
            "total_return_pct": total_return,
            "top_features": top_feat,
        })

        print(f"Fold {i+1}: train={len(X_train)}, test={len(X_test)}")
        print(f"  Train acc: {train_acc:.4f} | Test acc: {test_acc:.4f} | Sharpe: {sharpe:.2f} | Return: {total_return:.2f}%")
        print(f"  Top features: {', '.join(f'{n}({v:.3f})' for n,v in top_feat)}")
        print()

    # Summary
    if results:
        avg_test_acc = np.mean([r["test_acc"] for r in results])
        avg_sharpe = np.mean([r["sharpe"] for r in results])
        max_sharpe = max(r["sharpe"] for r in results)
        any_sharpe_gt1 = any(r["sharpe"] > 1.0 for r in results)
        any_acc_gt55 = any(r["test_acc"] > 0.55 for r in results)

        print("--- Walk-Forward Summary ---")
        print(f"  Folds analyzed: {len(results)}")
        print(f"  Avg test accuracy: {avg_test_acc:.4f}")
        print(f"  Avg Sharpe: {avg_sharpe:.2f}")
        print(f"  Max Sharpe (single fold): {max_sharpe:.2f}")
        print(f"  Any fold Sharpe > 1.0? {any_sharpe_gt1}")
        print(f"  Any fold accuracy > 55%? {any_acc_gt55}")

        if avg_sharpe < 0:
            print("\n  VERDICT: NEGATIVE average Sharpe. Strategy LOSES money on average.")
        elif avg_sharpe < 1.0:
            print("\n  VERDICT: Sharpe < 1.0 — NOT tradeable after costs.")
        else:
            print("\n  VERDICT: Sharpe > 1.0 — potentially tradeable, but needs more validation.")

    return results

# ============================================================
# SECTION 5: Regime-Conditional Analysis
# ============================================================
def section5_regime(df, symbol):
    print(f"\n{'='*70}")
    print(f"  SECTION 5: Regime-Conditional Analysis — {symbol}")
    print(f"{'='*70}")

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values

    # Define regimes using simple indicators
    # 1. Trend: use 100-bar SMA slope
    sma100 = pd.Series(close).rolling(100).mean().values
    sma_slope = np.zeros_like(close)
    sma_slope[100:] = (sma100[100:] - sma100[:-100]) / sma100[:-100] * 100

    # Normalize slope
    slope_std = np.nanstd(sma_slope[sma_slope != 0])
    if slope_std == 0:
        slope_std = 1

    # 2. Volatility: 20-bar ATR relative to price
    tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
    atr20 = pd.Series(tr).rolling(20).mean().values
    atr_pct = atr20 / close * 100

    atr_median = np.nanmedian(atr_pct[atr_pct > 0])
    if atr_median == 0:
        atr_median = 1

    # Regime definitions
    trending_up = sma_slope > slope_std
    trending_dn = sma_slope < -slope_std
    ranging = ~trending_up & ~trending_dn

    high_vol = atr_pct > atr_median * 1.2
    low_vol = atr_pct < atr_median * 0.8

    # Combined regimes
    regimes = {
        "Trending Up": trending_up,
        "Trending Down": trending_dn,
        "Ranging": ranging,
        "High Vol": high_vol,
        "Low Vol": low_vol,
    }

    # Target
    target = (np.roll(close, -1) > close).astype(float)
    target[-1] = np.nan

    # Base rate (next-bar up probability)
    valid = ~np.isnan(target)
    base_rate = np.nanmean(target[valid])
    print(f"\nBase rate (next bar up): {base_rate:.4f} ({base_rate*100:.1f}%)")

    # Load model for accuracy check
    try:
        model_data = load_model(symbol)
        model = model_data["model"]
        fcols_model = model_data["feature_columns"]
        X_all = df[fcols_model].copy().fillna(0)
        y_all = pd.Series(target)
        valid_mask = ~y_all.isna()
        X_valid = X_all[valid_mask]
        y_valid = y_all[valid_mask]
        model_preds = model.predict(X_valid.values)
        model_correct = (model_preds == y_valid.values).astype(float)
    except Exception as e:
        print(f"  Could not load model: {e}")
        model_correct = None

    print(f"\n{'Regime':<20} {'Count':>8} {'BaseRate':>10} {'ModelAcc':>10} {'Edge':>8}")
    print("-" * 60)

    for name, mask in regimes.items():
        regime_mask = mask & valid
        n = regime_mask.sum()
        if n < 100:
            print(f"{name:<20} {n:>8} (insufficient data)")
            continue

        regime_base = np.mean(target[regime_mask])

        if model_correct is not None:
            regime_model_mask = mask.values if hasattr(mask, 'values') else mask
            # Align indices
            idx = np.where(valid)[0]
            regime_idx = idx[mask[idx] if hasattr(mask[idx], 'sum') else mask.values[idx] if hasattr(mask, 'values') else mask[idx]]
            if len(regime_idx) > 0:
                regime_acc = np.mean(model_correct[regime_idx])
                edge = regime_acc - base_rate
                print(f"{name:<20} {n:>8} {regime_base:>10.4f} {regime_acc:>10.4f} {edge:>+8.4f}")
            else:
                print(f"{name:<20} {n:>8} {regime_base:>10.4f} {'N/A':>10} {'N/A':>8}")
        else:
            print(f"{name:<20} {n:>8} {regime_base:>10.4f} {'N/A':>10} {'N/A':>8}")

    print("\n--- Interpretation ---")
    print("  Base rate = natural next-bar up probability without model")
    print("  Model Acc = model's accuracy in that regime")
    print("  Edge = Model Acc - Base Rate (positive = model adds value)")
    print("  If Edge ~ 0 everywhere, model is NOT adding value beyond base rate")

    return regimes

# ============================================================
# SECTION 6: Cross-Asset Analysis
# ============================================================
def section6_cross_asset():
    print(f"\n{'='*70}")
    print("  SECTION 6: Cross-Asset Analysis (BTC, ETH, XAU, EUR)")
    print(f"{'='*70}")

    symbols = ["XAUUSD", "BTCUSD", "ETHUSD", "EURUSD"]
    returns_dict = {}
    for sym in symbols:
        try:
            df = load(sym)
            close = df["close"].values
            ret = np.diff(close) / close[:-1]
            returns_dict[sym] = ret
            print(f"\n  {sym}: {len(close)} bars, {len(ret)} returns")
            print(f"    Mean return: {np.mean(ret):.8f}")
            print(f"    Std: {np.std(ret):.6f}")
            print(f"    Skew: {stats.skew(ret):.4f}")
            print(f"    Kurt: {stats.kurtosis(ret):.4f}")
        except Exception as e:
            print(f"  {sym}: ERROR loading — {e}")

    # Correlation matrix
    if len(returns_dict) >= 2:
        # Trim to common length
        min_len = min(len(v) for v in returns_dict.values())
        ret_df = pd.DataFrame({k: v[:min_len] for k, v in returns_dict.items()})

        print("\n--- Return Correlation Matrix ---")
        corr = ret_df.corr()
        print(corr.to_string())

        print("\n--- BTC-ETH Independence Test ---")
        btc_eth_corr = corr.loc["BTCUSD", "ETHUSD"] if "BTCUSD" in corr.index and "ETHUSD" in corr.columns else None
        if btc_eth_corr is not None:
            print(f"  BTC-ETH return correlation: {btc_eth_corr:.4f}")
            n = min_len
            t_stat = btc_eth_corr * np.sqrt((n - 2) / (1 - btc_eth_corr**2))
            p_val = 2 * (1 - stats.t.cdf(abs(t_stat), df=n - 2))
            print(f"  t-stat: {t_stat:.4f}, p-value: {p_val:.6f}")
            if p_val < 0.05:
                print("  -> CORRELATED (not independent). p < 0.05")
            else:
                print("  -> Cannot reject independence (p >= 0.05)")

    # Portfolio Sharpe
    print("\n--- Equal-Weight Portfolio (all 4 symbols) ---")
    if len(returns_dict) >= 2:
        # Normalize each to unit variance for equal-weight portfolio
        portfolio_ret = np.mean([v[:min_len] / np.std(v[:min_len]) for v in returns_dict.values()], axis=0)

        # Sharpe ratio
        if np.std(portfolio_ret) > 0:
            sharpe_1d = np.mean(portfolio_ret) / np.std(portfolio_ret)
            sharpe_annual = sharpe_1d * np.sqrt(252 * 96)
            print(f"  Portfolio daily Sharpe (15min bar): {sharpe_1d:.4f}")
            print(f"  Portfolio annualized Sharpe: {sharpe_annual:.4f}")
            if sharpe_annual > 1.0:
                print("  -> Above 1.0 annualized, potentially interesting")
            else:
                print("  -> Below 1.0 annualized, NOT tradeable")

        # Also compute individual sharpes
        print("\n--- Individual Sharpe Ratios ---")
        for sym in returns_dict:
            r = returns_dict[sym][:min_len]
            s = np.mean(r) / np.std(r) * np.sqrt(252 * 96) if np.std(r) > 0 else 0
            print(f"  {sym}: {s:.4f}")

    return returns_dict

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("  DEEP DATA QUALITY & FEATURE ANALYSIS")
    print("=" * 70)

    # Load XAUUSD
    df_xau = load("XAUUSD")
    print(f"\nXAUUSD data: {df_xau.shape[0]} rows, {df_xau.shape[1]} columns")
    print(f"Time range: {df_xau['time'].iloc[0]} to {df_xau['time'].iloc[-1]}")

    # Section 1
    corr_results = section1_correlations(df_xau, "XAUUSD")

    # Section 2
    swing_results = section2_swing_sanity(df_xau, "XAUUSD")

    # Section 3
    macro_results = section3_macro(df_xau, "XAUUSD")

    # Section 4
    wf_results = section4_walkforward(df_xau, "XAUUSD")

    # Section 5
    regime_results = section5_regime(df_xau, "XAUUSD")

    # Section 6
    cross_results = section6_cross_asset()

    # FINAL VERDICT
    print(f"\n{'='*70}")
    print("  FINAL VERDICT: DOES ANY EDGE EXIST?")
    print(f"{'='*70}")

    # Collect key metrics
    max_corr = corr_results["abs_max"].max() if len(corr_results) > 0 else 0
    n_useful = len(corr_results[corr_results["abs_max"] > 0.1])
    n_leakage = len(corr_results[corr_results["abs_max"] > 0.3])

    avg_wf_sharpe = np.mean([r["sharpe"] for r in wf_results]) if wf_results else 0
    max_wf_sharpe = max([r["sharpe"] for r in wf_results]) if wf_results else 0
    avg_wf_acc = np.mean([r["test_acc"] for r in wf_results]) if wf_results else 0

    print("\n  1. Feature Correlations:")
    print(f"     Max |corr| with any target: {max_corr:.4f}")
    print(f"     Features with |corr| > 0.1 (useful): {n_useful}")
    print(f"     Features with |corr| > 0.3 (leakage): {n_leakage}")
    if n_leakage > 0:
        print("     WARNING: Potential data leakage detected!")

    print("\n  2. swing_high importance (32%) interpretation:")
    print(f"     swing_high=True -> next-bar up: {swing_results['swing_high_pct_up_next']:.1f}%")
    print(f"     swing_low=True -> next-bar up: {swing_results['swing_low_pct_up_next']:.1f}%")
    print(f"     Baseline (neither) -> next-bar up: {swing_results['baseline_pct_up_next']:.1f}%")

    print("\n  3. Macro features:")
    n_static = sum(1 for v in macro_results.values() if v["pct_static"] > 99)
    print(f"     {n_static}/{len(macro_results)} are effectively static (forward-filled daily)")

    print("\n  4. Walk-Forward (5-fold):")
    print(f"     Avg test accuracy: {avg_wf_acc:.4f}")
    print(f"     Avg Sharpe: {avg_wf_sharpe:.2f}")
    print(f"     Max Sharpe: {max_wf_sharpe:.2f}")

    print("\n  --- CONCLUSION ---")
    issues = []
    if n_leakage > 0:
        issues.append("Data leakage detected in features")
    if avg_wf_sharpe < 1.0:
        issues.append(f"Walk-forward Sharpe < 1.0 (avg={avg_wf_sharpe:.2f})")
    if avg_wf_acc < 0.55:
        issues.append(f"Walk-forward accuracy too low ({avg_wf_acc:.2%})")
    if n_static > 3:
        issues.append(f"{n_static} static macro features adding noise")

    if issues:
        print("  CRITICAL ISSUES:")
        for i, issue in enumerate(issues, 1):
            print(f"    {i}. {issue}")
        print("\n  VERDICT: NO RELIABLE EDGE EXISTS.")
        print("  The model's apparent performance is likely driven by:")
        print("  - Overfitting (train_acc=100% in existing WF)")
        print("  - swing_high/low acting as overfit binary features")
        print("  - Static macro features adding noise")
    else:
        print("  Some edge may exist — needs further validation.")
