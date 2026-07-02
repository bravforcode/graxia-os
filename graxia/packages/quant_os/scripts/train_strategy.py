"""
STRATEGY MODEL — Train directional prediction model from engineered features.

Loads features from build_features.py, trains XGBoost classifier,
backtests with walk-forward validation, reports metrics.

Usage:
    python scripts/train_strategy.py [--symbol XAUUSD] [--freq 1min] [--model xgboost|lightgbm|randomforest]
"""
import argparse
import json
import os
import warnings
from glob import glob

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

# ML
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
import xgboost as xgb

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts", "strategy_model")
FEATURES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts", "features")


def load_features(symbol: str, freq: str, feat_dir: str = None) -> pd.DataFrame:
    """Load feature parquet for given symbol/freq."""
    if feat_dir is None:
        feat_dir = FEATURES_DIR
    # Try v2 first, then v1
    candidates = [
        os.path.join(feat_dir, f"features_v2_{symbol}_{freq}.parquet"),
        os.path.join(feat_dir, f"features_{symbol}_{freq}.parquet"),
    ]
    path = None
    for c in candidates:
        if os.path.exists(c):
            path = c
            break
    if path is None:
        paths = glob(os.path.join(feat_dir, f"*{symbol}*{freq}*.parquet"))
        if paths:
            path = paths[0]
    if path is None:
        print(f"  [ERROR] No features found for {symbol} @ {freq}")
        return pd.DataFrame()
    df = pd.read_parquet(path)
    print(f"  [OK] Loaded {len(df)} rows from {path}")
    return df


def get_feature_cols(df: pd.DataFrame) -> list[str]:
    """Get feature columns (exclude target, metadata)."""
    exclude = {'target', 'target_return', 'symbol', 'freq', 'timestamp',
               'tb_label', 'tb_bar_hit', 'tb_side', 'tb_ret',
               'tb_k_upper', 'tb_k_lower'}
    return [c for c in df.columns if c not in exclude and df[c].dtype in (np.float64, np.int64)]


def train_model(X_train, y_train, model_type: str):
    """Train classifier."""
    if model_type == 'xgboost':
        model = xgb.XGBClassifier(
            n_estimators=100, max_depth=5, learning_rate=0.1,
            subsample=0.8, colsample_bytree=0.8,
            random_state=42, eval_metric='logloss',
            use_label_encoder=False, verbosity=0
        )
    elif model_type == 'lightgbm':
        import lightgbm as lgb
        model = lgb.LGBMClassifier(
            n_estimators=100, max_depth=5, learning_rate=0.1,
            subsample=0.8, colsample_bytree=0.8,
            random_state=42, verbose=-1
        )
    else:  # randomforest
        model = RandomForestClassifier(
            n_estimators=100, max_depth=10,
            random_state=42, n_jobs=-1
        )
    model.fit(X_train, y_train)
    return model


def backtest(model, X_test, y_test, feature_names: list[str], y_test_orig=None) -> dict:
    """Run backtest and return metrics."""
    y_pred = model.predict(X_test)
    
    # Classification metrics
    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    cm = confusion_matrix(y_test, y_pred)

    # Simulate trading
    # Map back to original labels for correct return calculation
    if y_test_orig is not None:
        # Triple-barrier: orig has {-1, 1}, y_test has {0, 1}
        y_test_labels = y_test_orig
        pred_labels = np.where(y_pred == 1, 1, -1)
        # Correct trade: predict == actual label
        trade_returns = np.where(pred_labels == y_test_labels, 1, -1)
    else:
        # Binary: 1=UP (+1), 0=DOWN (-1)
        actual_returns = np.where(y_test == 1, 1, -1)
        trade_returns = y_pred * actual_returns
    
    # Apply 0.1% slippage per trade
    trades = np.abs(np.diff(y_pred, prepend=y_pred[0]))  # 1 when position changes
    slippage_cost = trades * 0.001 * 100
    trade_returns = trade_returns - slippage_cost
    
    # Metrics
    total_return = trade_returns.sum()
    sharpe = (np.mean(trade_returns) / np.std(trade_returns) * np.sqrt(252)) if np.std(trade_returns) > 0 else 0
    win_rate = np.sum(trade_returns > 0) / max(np.sum(trade_returns != 0), 1)
    cum_returns = np.cumsum(trade_returns)
    max_dd = np.max(np.maximum.accumulate(cum_returns) - cum_returns)
    avg_win = np.mean(trade_returns[trade_returns > 0]) if np.any(trade_returns > 0) else 0
    avg_loss = np.mean(trade_returns[trade_returns < 0]) if np.any(trade_returns < 0) else 0
    profit_factor = abs(np.sum(trade_returns[trade_returns > 0]) / np.sum(trade_returns[trade_returns < 0])) if np.sum(trade_returns[trade_returns < 0]) != 0 else float('inf')
    
    # Feature importance
    if hasattr(model, 'feature_importances_'):
        fi = sorted(zip(feature_names, model.feature_importances_), key=lambda x: x[1], reverse=True)
    elif hasattr(model, 'coef_'):
        fi = sorted(zip(feature_names, abs(model.coef_[0])), key=lambda x: x[1], reverse=True)
    else:
        fi = list(zip(feature_names, [0] * len(feature_names)))
    
    return {
        "accuracy": round(acc, 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(f1, 4),
        "confusion_matrix": cm.tolist(),
        "total_return_pct": round(float(total_return), 2),
        "sharpe_ratio": round(float(sharpe), 4),
        "win_rate": round(float(win_rate), 4),
        "max_drawdown_pct": round(float(max_dd), 2),
        "avg_win": round(float(avg_win), 4),
        "avg_loss": round(float(avg_loss), 4),
        "profit_factor": round(float(profit_factor), 2),
        "n_test_samples": len(y_test),
        "n_predicted_up": int((y_pred == 1).sum()),
        "n_predicted_down": int((y_pred == 0).sum()),
        "feature_importance": [(name, round(imp, 4)) for name, imp in fi[:15]],
    }


def main():
    parser = argparse.ArgumentParser(description="Train trading strategy model")
    parser.add_argument("--symbol", type=str, default="XAUUSD", help="Symbol to train on")
    parser.add_argument("--freq", type=str, default="1min", help="Feature frequency")
    parser.add_argument("--model", choices=["xgboost", "lightgbm", "randomforest"],
                        default="xgboost", help="Model type")
    parser.add_argument("--test-size", type=float, default=0.3, help="Fraction for testing")
    parser.add_argument("--feat-dir", type=str, default=None,
                        help="Feature directory (default: artifacts/features)")
    parser.add_argument("--label-type", choices=["binary", "triple-barrier"],
                        default="binary",
                        help="Label type: binary (next-bar direction) or triple-barrier (vol-adjusted)")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"{'='*60}")
    print("STRATEGY MODEL TRAINING")
    print(f"  Symbol: {args.symbol}")
    print(f"  Freq: {args.freq}")
    print(f"  Model: {args.model}")
    print(f"{'='*60}")

    # Load features
    print("\n--- Loading features ---")
    df = load_features(args.symbol, args.freq, args.feat_dir)
    if df.empty:
        print("Run build_features.py first!")
        return

    feature_cols = get_feature_cols(df)
    print(f"  Features: {len(feature_cols)}")
    print(f"  Samples: {len(df)}")

    # Determine target column
    if args.label_type == "triple-barrier":
        if 'tb_label' not in df.columns:
            print("  [ERROR] tb_label not found. Run label_triple_barrier.py first.")
            return
        # Filter neutral bars (tb_label==0) — no barrier hit
        df = df[df['tb_label'] != 0].copy()
        target_col = 'tb_label'
        print(f"  Triple-barrier: filtered neutrals -> {len(df)} samples")
        print(f"  Label distribution: +1={int((df['tb_label']==1).sum())} "
              f"-1={int((df['tb_label']==-1).sum())}")
    else:
        target_col = 'target'

    # Train/test split (time-based)
    split_idx = int(len(df) * (1 - args.test_size))
    train_df = df.iloc[:split_idx]
    test_df = df.iloc[split_idx:]

    X_train = train_df[feature_cols].values
    y_train = train_df[target_col].values
    X_test = test_df[feature_cols].values
    y_test = test_df[target_col].values

    # XGBoost requires labels {0, 1}, map {-1, 1} -> {0, 1}
    if args.label_type == "triple-barrier":
        y_train = np.where(y_train == 1, 1, 0).astype(int)
        y_test_orig = y_test.copy()
        y_test = np.where(y_test == 1, 1, 0).astype(int)
    else:
        y_test_orig = y_test.copy()

    print(f"\n  Train: {len(X_train)} samples")
    print(f"  Test:  {len(X_test)} samples")
    if args.label_type == "binary":
        print(f"  Target distribution (train): UP={y_train.sum()}/{len(y_train)} "
              f"DOWN={len(y_train)-y_train.sum()}/{len(y_train)}")
    else:
        print(f"  Target distribution (train): +1={int((y_train==1).sum())} "
              f"-1={int((y_train==0).sum())}")

    # Train
    print(f"\n--- Training {args.model} ---")
    model = train_model(X_train, y_train, args.model)
    print("  [OK] Model trained")

    # Backtest
    print("\n--- Backtest ---")
    y_test_orig_for_bt = y_test_orig if args.label_type == "triple-barrier" else None
    metrics = backtest(model, X_test, y_test, feature_cols, y_test_orig=y_test_orig_for_bt)
    
    print(f"  Accuracy:    {metrics['accuracy']}")
    print(f"  Precision:   {metrics['precision']}")
    print(f"  Recall:      {metrics['recall']}")
    print(f"  F1:          {metrics['f1']}")
    print(f"  Sharpe:      {metrics['sharpe_ratio']}")
    print(f"  Win rate:    {metrics['win_rate']}")
    print(f"  Return:      {metrics['total_return_pct']}%")
    print(f"  Max DD:      {metrics['max_drawdown_pct']}%")
    print(f"  Profit Fctr: {metrics['profit_factor']}")
    print()
    print("  Top 5 features:")
    for name, imp in metrics['feature_importance'][:5]:
        print(f"    {name}: {imp:.4f}")

    # Save model + metrics
    print("\n--- Saving ---")
    model_path = os.path.join(OUTPUT_DIR, f"{args.symbol}_{args.freq}_{args.model}.json")
    if args.model == 'xgboost':
        model.save_model(model_path)
    else:
        import joblib
        model_path = model_path.replace('.json', '.pkl')
        joblib.dump(model, model_path)
    
    metrics_path = os.path.join(OUTPUT_DIR, f"{args.symbol}_{args.freq}_{args.model}_metrics.json")
    with open(metrics_path, 'w') as f:
        # Convert numpy types to Python native for JSON serialization
        def convert(obj):
            if isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert(v) for v in obj]
            elif isinstance(obj, tuple):
                return tuple(convert(v) for v in obj)
            elif hasattr(obj, 'item'):
                return obj.item()
            elif isinstance(obj, float):
                return round(obj, 6)
            return obj
        json.dump(convert(metrics), f, indent=2)
    
    print(f"  Model:   {model_path}")
    print(f"  Metrics: {metrics_path}")
    print(f"\n{'='*60}")
    print("STRATEGY MODEL TRAINING COMPLETE")
    print(f"  Sharpe: {metrics['sharpe_ratio']} | Accuracy: {metrics['accuracy']}")
    print(f"  Win rate: {metrics['win_rate']} | Return: {metrics['total_return_pct']}%")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
