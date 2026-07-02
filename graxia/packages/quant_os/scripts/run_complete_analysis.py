#!/usr/bin/env python3
"""
Complete analysis: Walk-forward + deflated Sharpe + buy-and-hold baseline
for XAUUSD/EURUSD/GBPUSD across M15/H1/D1.
"""
import sys, time, numpy as np, pandas as pd, xgboost as xgb
import importlib.util
sys.path.insert(0, '.')
sys.path.insert(0, 'scripts')
from backtest_cost import evaluate_backtest

SYMBOLS = {
    "XAUUSD": {"spread": 5e-05, "slippage": 2.7e-05, "point_value": 0.01},
    "EURUSD": {"spread": 8e-06, "slippage": 1.8e-05, "point_value": 0.00001},
    "GBPUSD": {"spread": 1e-05, "slippage": 4.3e-05, "point_value": 0.00001},
}
TIMEFRAMES = ["M15", "H1"]
CONF_THRESHOLDS = [0.0, 0.55, 0.65, 0.75, 0.85]
N_FOLDS = 5
TRAIN_RATIO = 0.7
MIN_TRADES = 10

def load_data(symbol, tf):
    path = f"data/{symbol}_{tf}.csv"
    try:
        df = pd.read_csv(path)
        if 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'], utc=True)
            df = df.set_index('time')
        return df
    except:
        return None

def compute_features(df):
    close = df['close'].values.astype(float)
    returns = np.diff(close) / close[:-1]
    returns = np.concatenate([[0], returns])
    features = pd.DataFrame(index=df.index)
    features['return_1'] = returns
    features['return_5'] = pd.Series(returns).rolling(5).mean().values
    features['return_10'] = pd.Series(returns).rolling(10).mean().values
    features['return_20'] = pd.Series(returns).rolling(20).mean().values
    features['vol_10'] = pd.Series(returns).rolling(10).std().values
    features['vol_20'] = pd.Series(returns).rolling(20).std().values
    features['vol_ratio'] = features['vol_10'] / (features['vol_20'] + 1e-10)
    features['close'] = close
    features['target'] = (returns > 0).astype(int)
    features['target_return'] = returns
    return features.dropna()

def buy_and_hold(df, lot_mult=1.0, contract_mult=100):
    """Calculate buy-and-hold return."""
    close = df['close'].values.astype(float)
    if len(close) < 2:
        return 0, 0, 0
    entry = close[0]
    exit_p = close[-1]
    gross = (exit_p - entry) * lot_mult * contract_mult
    return gross, entry, exit_p

def run_analysis(symbol, tf):
    """Run walk-forward + deflated sharpe for one symbol/tf."""
    costs = SYMBOLS[symbol]
    df = load_data(symbol, tf)
    if df is None or len(df) < 500:
        return None
    
    features = compute_features(df)
    close_col = 'close'
    feature_cols = [c for c in features.columns if c not in ['target', 'target_return', close_col]]
    X = features[feature_cols].values.astype(np.float32)
    y = features['target'].values
    close_prices = features[close_col].values
    
    fold_size = len(X) // N_FOLDS
    train_size = int(fold_size * TRAIN_RATIO)
    
    # Buy-and-hold baseline
    bh_gross, bh_entry, bh_exit = buy_and_hold(df)
    
    results = {}
    for conf_thresh in CONF_THRESHOLDS:
        fold_results = []
        for fold_idx in range(N_FOLDS):
            start = fold_idx * fold_size
            train_end = start + train_size
            test_start = train_end
            test_end = min(start + fold_size, len(X))
            if test_start >= test_end or test_end - test_start < MIN_TRADES:
                continue
            X_train, X_test = X[start:train_end], X[test_start:test_end]
            y_train = y[start:train_end]
            close_test = close_prices[test_start:test_end]
            
            model = xgb.XGBClassifier(
                n_estimators=100, max_depth=5, learning_rate=0.1,
                subsample=0.8, colsample_bytree=0.8,
                random_state=42, eval_metric='logloss', verbosity=0, n_jobs=-1,
            )
            model.fit(X_train, y_train)
            proba = model.predict_proba(X_test)
            conf = np.max(proba, axis=1)
            
            trade_mask = conf >= conf_thresh
            n_trades = trade_mask.sum()
            if n_trades < MIN_TRADES:
                continue
            
            df_test = features.iloc[test_start:test_end].reset_index(drop=True)
            df_test['close'] = close_test
            filtered = df_test[trade_mask]
            
            result = evaluate_backtest(
                filtered, model, feature_cols,
                pd.Series(True, index=filtered.index),
                spread_cost=costs['spread'], slippage_p90=costs['slippage'], lot_mult=1.0,
                min_confidence=0.0, min_regime=0.0,
            )
            result['fold'] = fold_idx
            fold_results.append(result)
        
        if not fold_results:
            continue
        
        total_trades = sum(r['n_trades'] for r in fold_results)
        total_gross = sum(r['gross_pnl'] for r in fold_results)
        total_cost = sum(r['total_cost'] for r in fold_results)
        total_net = sum(r['net_pnl'] for r in fold_results)
        sharpes = [r['sharpe_ratio'] for r in fold_results if r['n_trades'] > 0 and r['sharpe_ratio'] != 0]
        avg_sharpe = np.mean(sharpes) if sharpes else 0
        fold_nets = [round(r['net_pnl'], 2) for r in fold_results]
        
        # Deflated Sharpe
        try:
            spec = importlib.util.spec_from_file_location('ds', 'validation/deflated_sharpe.py')
            ds_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ds_mod)
            ds = ds_mod.deflated_sharpe_ratio(avg_sharpe, N_FOLDS * len(CONF_THRESHOLDS), total_trades)
            ds_sharpe = ds.deflated_sharpe
            ds_pass = ds.passes_threshold
        except:
            ds_sharpe = avg_sharpe
            ds_pass = False
        
        results[conf_thresh] = {
            'trades': total_trades,
            'gross': total_gross,
            'cost': total_cost,
            'net': total_net,
            'sharpe': avg_sharpe,
            'ds_sharpe': ds_sharpe,
            'ds_pass': ds_pass,
            'fold_nets': fold_nets,
        }
    
    return {
        'symbol': symbol,
        'tf': tf,
        'bars': len(df),
        'period': f"{df.index[0].strftime('%Y-%m-%d')} to {df.index[-1].strftime('%Y-%m-%d')}",
        'bh_gross': bh_gross,
        'bh_entry': bh_entry,
        'bh_exit': bh_exit,
        'results': results,
    }

def main():
    print("=" * 120)
    print("COMPLETE WALK-FORWARD ANALYSIS + BUY-AND-HOLD BASELINE")
    print("Symbols: XAUUSD, EURUSD, GBPUSD | Timeframes: M15, H1")
    print("Confidence thresholds: 0.0, 0.55, 0.65, 0.75, 0.85")
    print("=" * 120)
    
    all_results = []
    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            print(f"\n--- {symbol} {tf} ---")
            t0 = time.time()
            result = run_analysis(symbol, tf)
            elapsed = time.time() - t0
            
            if result is None:
                print("  SKIP: no data")
                continue
            
            print(f"  Data: {result['bars']} bars, {result['period']}")
            print(f"  Buy-and-Hold: ${result['bh_gross']:+.2f} (entry={result['bh_entry']:.2f}, exit={result['bh_exit']:.2f})")
            print(f"  Time: {elapsed:.1f}s")
            
            # Print table
            print(f"  {'Conf':>6s} | {'Trades':>7s} | {'Gross':>10s} | {'Cost':>8s} | {'Net':>10s} | {'Sharpe':>7s} | {'DS':>7s} | {'DS?':>4s} | {'vs BH':>10s}")
            print(f"  {'-'*6}-|-{'-'*7}-|-{'-'*10}-|-{'-'*8}-|-{'-'*10}-|-{'-'*7}-|-{'-'*7}-|-{'-'*4}-|-{'-'*10}")
            
            for conf in CONF_THRESHOLDS:
                if conf not in result['results']:
                    continue
                r = result['results'][conf]
                edge = r['net'] - result['bh_gross']
                ds = "PASS" if r['ds_pass'] else "FAIL"
                print(f"  {conf:>6.2f} | {r['trades']:>7d} | ${r['gross']:>+9.2f} | ${r['cost']:>7.2f} | ${r['net']:>+9.2f} | {r['sharpe']:>7.1f} | {r['ds_sharpe']:>7.1f} | {ds:>4s} | ${edge:>+9.2f}")
            
            all_results.append(result)
    
    # Final summary
    print("\n" + "=" * 120)
    print("FINAL SUMMARY — Best conf threshold per symbol/tf")
    print("=" * 120)
    print(f"{'Symbol':10s} {'TF':5s} {'Bars':>7s} {'BH Return':>10s} {'Best Conf':>10s} {'Net':>10s} {'Edge vs BH':>10s} {'Sharpe':>7s} {'DS':>7s} {'DS?':>4s}")
    print("-" * 100)
    
    for r in all_results:
        best_conf = 0
        best_net = -999999
        for conf, data in r['results'].items():
            if data['net'] > best_net:
                best_net = data['net']
                best_conf = conf
        best = r['results'][best_conf]
        edge = best['net'] - r['bh_gross']
        ds = "PASS" if best['ds_pass'] else "FAIL"
        print(f"{r['symbol']:10s} {r['tf']:5s} {r['bars']:>7d} ${r['bh_gross']:>+9.2f} {best_conf:>10.2f} ${best['net']:>+9.2f} ${edge:>+9.2f} {best['sharpe']:>7.1f} {best['ds_sharpe']:>7.1f} {ds:>4s}")

if __name__ == "__main__":
    main()
