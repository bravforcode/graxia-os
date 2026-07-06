"""
Diagnose Target Leakage in Walk-Forward Results

Investigate why training accuracy is 100% and OOS is near-100%.
This could indicate target leakage, overfitting, or trivially easy targets.
"""
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path

BASE = Path(__file__).parent.parent
FEAT_DIR = BASE / "artifacts" / "features_v2"

def diagnose_leakage(symbol: str = "XAUUSD", freq: str = "H1"):
    """Diagnose potential leakage in features."""
    print("=" * 60)
    print(f"DIAGNOSING LEAKAGE: {symbol} @ {freq}")
    print("=" * 60)
    
    # Load features
    path = FEAT_DIR / f"features_{symbol}_{freq}.parquet"
    df = pd.read_parquet(path)
    
    print(f"\n1. DATA OVERVIEW")
    print(f"   Rows: {len(df)}")
    print(f"   Columns: {len(df.columns)}")
    print(f"   Date range: {df.index[0]} to {df.index[-1]}")
    
    # Check target distribution
    print(f"\n2. TARGET DISTRIBUTION")
    if "target" in df.columns:
        target_counts = df["target"].value_counts()
        print(f"   Target values: {target_counts.to_dict()}")
        print(f"   Target mean: {df['target'].mean():.4f}")
        print(f"   Target std: {df['target'].std():.4f}")
    
    if "target_return" in df.columns:
        print(f"   target_return mean: {df['target_return'].mean():.6f}")
        print(f"   target_return std: {df['target_return'].std():.6f}")
        print(f"   target_return min: {df['target_return'].min():.6f}")
        print(f"   target_return max: {df['target_return'].max():.6f}")
    
    # Check for trivially easy targets
    print(f"\n3. TARGET EASE ANALYSIS")
    if "target" in df.columns and "target_return" in df.columns:
        # How many bars have target_return > 0?
        up_pct = (df["target_return"] > 0).mean()
        print(f"   Bars with positive return: {up_pct:.4f}")
        
        # Check if target is just direction of next bar
        next_return = df["close"].pct_change(1).shift(-1)
        same_dir = (df["target"] == (next_return > 0).astype(int)).mean()
        print(f"   Target matches next-bar direction: {same_dir:.4f}")
    
    # Check for feature-target correlation
    print(f"\n4. FEATURE-TARGET CORRELATIONS")
    exclude_cols = {"target", "target_return", "symbol", "freq", "target_3class"}
    feature_cols = [c for c in df.columns if c not in exclude_cols 
                    and df[c].dtype in (np.float64, np.float32, np.int64, np.int32)]
    
    if "target" in df.columns:
        correlations = {}
        for col in feature_cols:
            corr = df[col].corr(df["target"])
            if abs(corr) > 0.01:
                correlations[col] = corr
        
        # Sort by absolute correlation
        sorted_corr = sorted(correlations.items(), key=lambda x: abs(x[1]), reverse=True)
        
        print(f"   Features with |corr| > 0.01: {len(sorted_corr)}")
        print(f"\n   Top 10 most correlated features:")
        for col, corr in sorted_corr[:10]:
            print(f"     {col}: {corr:.4f}")
    
    # Check for look-ahead bias in rolling features
    print(f"\n5. LOOK-AHEAD BIAS CHECK")
    # Check if any feature uses future data
    suspicious_features = []
    for col in feature_cols:
        # Check if feature is perfectly correlated with future price
        future_close = df["close"].shift(-1)
        if col in ["close", "open", "high", "low"]:
            continue
        try:
            corr = df[col].corr(future_close)
            if abs(corr) > 0.99:
                suspicious_features.append((col, corr))
        except:
            pass
    
    if suspicious_features:
        print(f"   SUSPICIOUS: {len(suspicious_features)} features perfectly correlated with future price:")
        for col, corr in suspicious_features:
            print(f"     {col}: {corr:.4f}")
    else:
        print(f"   No features perfectly correlated with future price")
    
    # Simple model test
    print(f"\n6. SIMPLE MODEL TEST")
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    
    X = df[feature_cols].fillna(0).values
    y = df["target"].values if "target" in df.columns else None
    
    if y is not None:
        # Remove last 5 rows (NaN from target creation)
        X = X[:-5]
        y = y[:-5]
        
        # Split: 80% train, 20% test (sequential, not random)
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]
        
        # Train simple model
        model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
        model.fit(X_train, y_train)
        
        train_acc = (model.predict(X_train) == y_train).mean()
        test_acc = (model.predict(X_test) == y_test).mean()
        
        print(f"   Train accuracy: {train_acc:.4f}")
        print(f"   Test accuracy: {test_acc:.4f}")
        print(f"   Overfitting gap: {train_acc - test_acc:.4f}")
        
        if train_acc > 0.99 and test_acc > 0.95:
            print(f"   WARNING: High accuracy suggests potential target leakage!")
        elif train_acc > 0.99 and test_acc < 0.6:
            print(f"   OK: High train accuracy but low test accuracy = overfitting (normal)")
        else:
            print(f"   OK: Accuracy levels look reasonable")

if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"
    freq = sys.argv[2] if len(sys.argv) > 2 else "H1"
    diagnose_leakage(symbol, freq)
