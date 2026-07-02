"""
REGIME ACCURACY DIAGNOSTIC — Check if model accuracy clusters by regime.

54.27% accuracy on every bar loses money (edge ~0.34 pips vs spread ~22 pips).
But if accuracy is 58-62% on a 5-10% subset of high-confidence bars, that subset
may have positive expectancy. This diagnostic finds those regimes.

Decision gate:
  If any regime gives >57% accuracy on >=5% of bars → build regime filter.
  Otherwise → skip regime filter, go directly to meta-label model.

Usage:
    python scripts/diagnose_regime_accuracy.py --symbol XAUUSD --freq 1min \
        --feat-dir artifacts/features_v2
    python scripts/diagnose_regime_accuracy.py --symbol XAUUSD --freq 1min \
        --model-path artifacts/strategy_model/XAUUSD_1min_xgboost.json
"""
import argparse
import os
import sys
import warnings
from glob import glob

import numpy as np
import pandas as pd
import xgboost as xgb

warnings.filterwarnings('ignore')

ROOT = os.path.dirname(os.path.dirname(__file__))
FEAT_DIR = os.path.join(ROOT, "artifacts", "features_v2")
MODEL_DIR = os.path.join(ROOT, "artifacts", "strategy_model")
OUT_DIR = os.path.join(ROOT, "artifacts", "diagnostics")


def load_data(symbol: str, freq: str, feat_dir: str) -> pd.DataFrame:
    """Load v2 features with tb_label."""
    paths = [
        os.path.join(feat_dir, f"features_v2_{symbol}_{freq}.parquet"),
        os.path.join(feat_dir, f"features_{symbol}_{freq}.parquet"),
    ]
    path = None
    for p in paths:
        if os.path.exists(p):
            path = p
            break
    if path is None:
        path = glob(os.path.join(feat_dir, f"*{symbol}*{freq}*.parquet"))
        path = path[0] if path else None
    if path is None:
        print(f"  [ERROR] No features for {symbol} @ {freq}")
        sys.exit(1)

    df = pd.read_parquet(path)
    if 'timestamp' in df.columns:
        df = df.set_index('timestamp')
    elif not isinstance(df.index, pd.DatetimeIndex):
        pass
    df.index = pd.to_datetime(df.index, utc=True)
    print(f"  [OK] Loaded {len(df)} rows from {os.path.basename(path)}")
    print(f"      Range: {df.index.min()} to {df.index.max()}")
    return df


def get_feature_cols(df: pd.DataFrame) -> list[str]:
    """Exclude targets and metadata."""
    exclude = {'target', 'target_return', 'symbol', 'freq',
               'tb_label', 'tb_bar_hit', 'tb_side', 'tb_ret',
               'tb_k_upper', 'tb_k_lower'}
    return [c for c in df.columns if c not in exclude
            and df[c].dtype in (np.float64, np.float32, np.int64, np.int32)]


def train_or_load_model(df, feature_cols, model_path=None):
    """Train XGBoost or load existing. Returns (model, test_mask, oos_accuracy)."""
    y = df['target'].values
    X = df[feature_cols].fillna(0).values
    n = len(X)

    if model_path and os.path.exists(model_path):
        model = xgb.XGBClassifier()
        model.load_model(model_path)
        print(f"  [OK] Loaded model from {model_path}")
        # Estimate: compute oos accuracy on last 30%
        split = int(n * 0.7)
        acc = (model.predict(X[split:]) == y[split:]).mean()
        print(f"      OOS accuracy estimate: {acc:.4f}")
        test_mask = np.zeros(n, dtype=bool)
        test_mask[split:] = True
        test_mask_series = pd.Series(test_mask, index=df.index)
        return model, test_mask_series, acc
    else:
        print(f"  [TRAIN] Training new model on {n} samples...")
        model = xgb.XGBClassifier(
            n_estimators=100, max_depth=5, learning_rate=0.1,
            subsample=0.8, colsample_bytree=0.8,
            random_state=42, eval_metric='logloss',
            use_label_encoder=False, verbosity=0
        )
        # Time-based 70/30 split
        split = int(n * 0.7)
        model.fit(X[:split], y[:split])
        y_pred_oos = model.predict(X[split:])
        acc = (y_pred_oos == y[split:]).mean()
        print(f"      Out-of-sample accuracy: {acc:.4f}")
        # Return test mask
        test_mask = np.zeros(n, dtype=bool)
        test_mask[split:] = True
        test_mask_series = pd.Series(test_mask, index=df.index)
        return model, test_mask_series, acc


def compute_regime_breakdown(df: pd.DataFrame, model, feature_cols: list[str],
                              test_mask=None, baseline_oos=None):
    """
    Compute accuracy by regime dimension.

    CRITICAL: Operates on test_mask (OOS) only if provided.
    Otherwise uses full dataset (in-sample — for reference, not decision).

    Returns DataFrame of {regime, n_bars, pct_bars, accuracy, vs_baseline}.
    """
    if test_mask is not None:
        df = df.loc[test_mask].copy()
        print(f"\n  Using OOS subset: {test_mask.sum()} bars")

    X = df[feature_cols].fillna(0).values
    y_true = df['target'].values
    y_pred = model.predict(X)

    if baseline_oos is not None:
        baseline_acc = baseline_oos
    else:
        baseline_acc = (y_pred == y_true).mean()

    print(f"  Baseline accuracy: {baseline_acc:.4f}")
    print(f"  Total bars evaluated: {len(y_true)}")

    results = []

    def evaluate_regime(mask: pd.Series, regime_name: str):
        n = mask.sum()
        if n < 15:
            return
        acc = (y_pred[mask] == y_true[mask]).mean()
        results.append({
            'regime': regime_name,
            'n_bars': n,
            'pct_bars': n / len(y_true),
            'accuracy': round(acc, 4),
            'vs_baseline': round(acc - baseline_acc, 4),
        })

    # -- 1. Confluence score --
    # Count aligned multi-TF indicators
    confluence_cols = [c for c in df.columns if 'trend_align' in c or 'macd_trend_align' in c]
    if confluence_cols:
        df['_confluence_score'] = df[confluence_cols].sum(axis=1)
        for thresh in [1, 2, 3, 4]:
            mask = df['_confluence_score'] >= thresh
            evaluate_regime(mask.fillna(False), f'confluence>={thresh}')

    # -- 2. Volatility regime --
    vol_cols = [c for c in df.columns if 'vol_regime' in c or 'vol_expansion' in c]
    for vc in vol_cols[:2]:  # first 2 vol indicators to avoid combinatorial explosion
        if vc not in df.columns or df[vc].isna().all():
            continue
        v_mean = df[vc].mean()
        v_std = df[vc].std()
        if pd.isna(v_std) or v_std == 0:
            continue

        # Low vol: < mean - 0.5*std
        mask_low = (df[vc] < v_mean - 0.5 * v_std).fillna(False)
        evaluate_regime(mask_low, f'{vc}_low')

        # High vol: > mean + 0.5*std
        mask_high = (df[vc] > v_mean + 0.5 * v_std).fillna(False)
        evaluate_regime(mask_high, f'{vc}_high')

    # -- 3. Spread regime --
    if 'spread_mean' in df.columns:
        s_mean = df['spread_mean'].mean()
        s_std = df['spread_mean'].std()
        if not pd.isna(s_std) and s_std > 0:
            mask_low = (df['spread_mean'] < s_mean - 0.5 * s_std).fillna(False)
            evaluate_regime(mask_low, 'spread_low')
            mask_high = (df['spread_mean'] > s_mean + 0.5 * s_std).fillna(False)
            evaluate_regime(mask_high, 'spread_high')

    # -- 4. Spread volatility regime --
    if 'spread_volatility' in df.columns:
        sv_mean = df['spread_volatility'].mean()
        sv_std = df['spread_volatility'].std()
        if not pd.isna(sv_std) and sv_std > 0:
            mask_low = (df['spread_volatility'] < sv_mean - 0.5 * sv_std).fillna(False)
            evaluate_regime(mask_low, 'spread_vol_low')
            mask_high = (df['spread_volatility'] > sv_mean + 0.5 * sv_std).fillna(False)
            evaluate_regime(mask_high, 'spread_vol_high')

    # -- 5. RSI divergence regime --
    rsi_div_cols = [c for c in df.columns if 'rsi_divergence' in c]
    for rc in rsi_div_cols:
        if rc not in df.columns or df[rc].isna().all():
            continue
        r_mean = df[rc].mean()
        r_std = df[rc].std()
        if pd.isna(r_std) or r_std == 0:
            continue
        # Strong divergence: > mean + 1*std
        mask_strong = (abs(df[rc]) > abs(r_mean) + r_std).fillna(False)
        evaluate_regime(mask_strong, f'{rc}_strong')
        # Weak/neutral: < mean + 0.5*std
        mask_weak = (abs(df[rc]) < abs(r_mean) + 0.5 * r_std).fillna(False)
        evaluate_regime(mask_weak, f'{rc}_weak')

    # -- 6. Cross: confluence + vol --
    if '_confluence_score' in df.columns:
        for thresh in [2, 3]:
            for vc in vol_cols[:1]:
                if vc not in df.columns:
                    continue
                v_mean = df[vc].mean()
                v_std = df[vc].std()
                if pd.isna(v_std) or v_std == 0:
                    continue
                for vol_label, vol_cond in [
                    ('low', df[vc] < v_mean - 0.3 * v_std),
                    ('mid', (df[vc] >= v_mean - 0.3 * v_std) & (df[vc] <= v_mean + 0.3 * v_std)),
                ]:
                    mask = pd.Series((df['_confluence_score'] >= thresh).values & vol_cond.values,
                                     index=df.index)
                    evaluate_regime(mask.fillna(False),
                                    f'conf>={thresh}+{vc}_{vol_label}')

    # -- 7. Time of day (if index is datetime) --
    if isinstance(df.index, pd.DatetimeIndex):
        hour_series = pd.Series(df.index.hour, index=df.index)
        for h in range(24):
            mask = pd.Series(hour_series == h, index=df.index)
            evaluate_regime(mask.fillna(False), f'hour_{h:02d}')

        # Session: Asia, London, NY overlap
        sessions = [
            ('asia', (hour_series >= 1) & (hour_series <= 9)),
            ('london_open', (hour_series >= 7) & (hour_series <= 10)),
            ('london_ny_overlap', (hour_series >= 12) & (hour_series <= 16)),
            ('ny_close', (hour_series >= 19) & (hour_series <= 22)),
        ]
        for sname, smask in sessions:
            evaluate_regime(pd.Series(smask, index=df.index), f'session_{sname}')

    # Cleanup temporary columns
    for c in ['_confluence_score']:
        if c in df.columns:
            del df[c]

    result_df = pd.DataFrame(results).sort_values('accuracy', ascending=False)
    return result_df, baseline_acc


def fix_unicode(s):
    """Replace unicode box chars for Windows terminal."""
    return s.replace('\u2500', '-').replace('\u2502', '|').replace('\u2550', '=')


def print_report(results: pd.DataFrame, baseline_acc: float):
    """Print formatted regime breakdown and decision."""
    print(f"\n{'='*70}")
    print("REGIME ACCURACY BREAKDOWN")
    print(f"  Baseline: {baseline_acc:.4f}")
    print(f"  Regimes tested: {len(results)}")
    print(f"{'='*70}")

    if results.empty:
        print("  [WARN] No regimes could be evaluated (< 15 bars each)")
        return

    # Format for display
    display = results.copy()
    display['accuracy'] = display['accuracy'].map('{:.4f}'.format)
    display['vs_baseline'] = display['vs_baseline'].map('{:+.4f}'.format)
    display['pct_bars'] = display['pct_bars'].map('{:.1%}'.format)
    print(display.to_string(index=False))

    # -- Decision gate --
    threshold_acc = baseline_acc + 0.03  # >57% if baseline is 54%
    candidates = results[
        (results['accuracy'] >= threshold_acc) &
        (results['pct_bars'] >= 0.05)
    ].sort_values('accuracy', ascending=False)

    print(f"\n{'-'*70}")
    print(f"DECISION GATE: accuracy >= {threshold_acc:.4f} on >= 5% of bars")
    print(f"{'-'*70}")

    if not candidates.empty:
        best = candidates.iloc[0]
        print("\n  [OK] REGIME FILTER WORTH BUILDING")
        print(f"     Best regime:      {best['regime']}")
        print(f"     Accuracy:         {best['accuracy']:.4f} (+{best['vs_baseline']:+.4f} vs baseline)")
        print(f"     Bars in regime:   {int(best['n_bars'])} ({best['pct_bars']:.1%} of total)")
        print(f"     Expected net edge at {best['accuracy']:.1%}:")
        edge_pips = (best['accuracy'] - 0.5) * 2 * 4  # 4 pip avg 1min move
        print(f"       Gross: {edge_pips:.2f} pips")
        print("       Spread: ~22 pips")
        print(f"       Net: {edge_pips - 22:.2f} pips (vs -21.66 baseline)")
        if edge_pips > 22:
            print("       [OK] POSITIVE EXPECTANCY in this regime")
        else:
            print("       [NO] Still negative — need thinner spread or higher accuracy")
        print("\n     Top 5 regimes:")
        for _, row in candidates.head(5).iterrows():
            print(f"       {row['regime']:<30s} acc={row['accuracy']:.4f}  bars={int(row['n_bars']):>5d} ({row['pct_bars']:.1%})")
    else:
        print("\n  [WARN]  NO regime clears the threshold\n")

        # Check if any regime > threshold but < 5% bars
        small = results[results['accuracy'] >= threshold_acc]
        if not small.empty:
            print(f"     {len(small)} regimes have accuracy >= {threshold_acc:.4f} but < 5% of bars:")
            for _, row in small.head(5).iterrows():
                print(f"       {row['regime']:<30s} acc={row['accuracy']:.4f}  bars={int(row['n_bars']):>5d} ({row['pct_bars']:.1%})")
            print("\n     → Consider expanding dataset (more bars may reveal stable regimes)")
        else:
            print(f"     No regime reaches accuracy >= {threshold_acc:.4f} at all.")
            print("     RECOMMENDATION: Skip regime filter. Build meta-label model instead.")

    return candidates


def main():
    parser = argparse.ArgumentParser(description="Regime accuracy diagnostic")
    parser.add_argument("--symbol", type=str, default="XAUUSD")
    parser.add_argument("--freq", type=str, default="1min")
    parser.add_argument("--feat-dir", type=str, default=FEAT_DIR)
    parser.add_argument("--model-path", type=str, default=None,
                        help="Path to pre-trained model (optional, trains new if omitted)")
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"{'='*70}")
    print("REGIME ACCURACY DIAGNOSTIC")
    print(f"  Symbol: {args.symbol} @ {args.freq}")
    print(f"  Feature dir: {args.feat_dir}")
    print(f"  Model: {'auto-train' if not args.model_path else args.model_path}")
    print(f"{'='*70}")

    # Load
    df = load_data(args.symbol, args.freq, args.feat_dir)
    if 'target' not in df.columns:
        print("  [ERROR] No 'target' column — run build_features.py first")
        sys.exit(1)

    feature_cols = get_feature_cols(df)
    print(f"  Features: {len(feature_cols)}")

    # Model
    model, test_mask, oos_acc = train_or_load_model(df, feature_cols, args.model_path)

    # Regime breakdown (OOS only)
    print("\n--- Computing regime breakdown (OOS only) ---")
    results, baseline = compute_regime_breakdown(
        df, model, feature_cols,
        test_mask=test_mask, baseline_oos=oos_acc
    )

    # Report
    candidates = print_report(results, baseline)

    # Save
    save_path = os.path.join(OUT_DIR, f"regime_accuracy_{args.symbol}_{args.freq}.csv")
    results.to_csv(save_path, index=False)
    print(f"\n  Saved: {save_path}")

    # Decision record
    decision = {
        "symbol": args.symbol,
        "freq": args.freq,
        "baseline_accuracy": round(baseline, 4),
        "threshold_acc": round(baseline + 0.03, 4),
        "n_regimes_tested": len(results),
        "n_candidates": len(candidates) if candidates is not None else 0,
        "best_regime": candidates.iloc[0]['regime'] if candidates is not None and len(candidates) > 0 else None,
        "best_accuracy": float(candidates.iloc[0]['accuracy']) if candidates is not None and len(candidates) > 0 else None,
        "best_pct_bars": float(candidates.iloc[0]['pct_bars']) if candidates is not None and len(candidates) > 0 else None,
        "recommendation": "regime_filter" if candidates is not None and len(candidates) > 0 else "meta_label",
    }
    decision_path = os.path.join(OUT_DIR, f"regime_decision_{args.symbol}_{args.freq}.json")
    import json
    with open(decision_path, 'w') as f:
        json.dump(decision, f, indent=2)
    print(f"  Decision: {decision_path}")
    print(f"  Recommendation: {decision['recommendation']}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
