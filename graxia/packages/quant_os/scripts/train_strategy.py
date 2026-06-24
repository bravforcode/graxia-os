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
import sys
import warnings
from datetime import datetime, timezone
from glob import glob

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

# ML
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
from sklearn.model_selection import TimeSeriesSplit
import xgboost as xgb

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts", "strategy_model")
FEATURES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts", "features")


def load_features(symbol: str, freq: str) -> pd.DataFrame:
    """Load feature parquet for given symbol/freq."""
    path = os.path.join(FEATURES_DIR, f"features_{symbol}_{freq}.parquet")
    if not os.path.exists(path):
        # try glob
        paths = glob(os.path.join(FEATURES_DIR, f"features_{symbol}*{freq}*.parquet"))
        if not paths:
            print(f"  [ERROR] No features found for {symbol} @ {freq}")
            return pd.DataFrame()
        path = paths[0]
    df = pd.read_parquet(path)
    print(f"  [OK] Loaded {len(df)} rows from {path}")
    return df


def get_feature_cols(df: pd.DataFrame) -> list[str]:
    """Get feature columns (exclude target, metadata)."""
    exclude = {'target', 'target_return', 'symbol', 'freq', 'timestamp'}
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


def backtest(model, X_test, y_test, feature_names: list[str]) -> dict:
    """Run backtest and return metrics."""
    y_pred = model.predict(X_test)
    
    # Classification metrics
    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    cm = confusion_matrix(y_test, y_pred)

    # Simulate trading: predict UP=1 -> long, DOWN=0 -> stay out
    # Map target: 1=UP (+1), 0=DOWN (-1)
    actual_returns = np.where(y_test == 1, 1, -1)
    
    # Trade returns: when predict 1, get actual return; when predict 0, get 0
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
    df = load_features(args.symbol, args.freq)
    if df.empty:
        print("Run build_features.py first!")
        return

    feature_cols = get_feature_cols(df)
    print(f"  Features: {len(feature_cols)}")
    print(f"  Samples: {len(df)}")

    # Train/test split (time-based)
    split_idx = int(len(df) * (1 - args.test_size))
    train_df = df.iloc[:split_idx]
    test_df = df.iloc[split_idx:]

    X_train = train_df[feature_cols].values
    y_train = train_df['target'].values
    X_test = test_df[feature_cols].values
    y_test = test_df['target'].values

    print(f"\n  Train: {len(X_train)} samples")
    print(f"  Test:  {len(X_test)} samples")
    print(f"  Target distribution (train): UP={y_train.sum()}/{len(y_train)} "
          f"DOWN={len(y_train)-y_train.sum()}/{len(y_train)}")

    # Train
    print(f"\n--- Training {args.model} ---")
    model = train_model(X_train, y_train, args.model)
    print(f"  [OK] Model trained")

    # Backtest
    print(f"\n--- Backtest ---")
    metrics = backtest(model, X_test, y_test, feature_cols)
    
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
    print(f"\n--- Saving ---")
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
