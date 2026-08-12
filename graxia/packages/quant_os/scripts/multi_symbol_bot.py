"""
multi_symbol_bot.py — Trade 5 symbols with individual XGBoost models
Run: python -u scripts/multi_symbol_bot.py
"""
import sys, pickle, time, csv, warnings
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
warnings.filterwarnings('ignore')

from graxia.packages.quant_os.core.safe_pickle import safe_load_model

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
DATA_DIR = BASE / 'data'
MODEL_DIR = BASE / 'ml' / 'models'
LOG_PATH = DATA_DIR / 'multi_symbol_log.csv'

SYMBOLS = [
    {'name': 'XAUUSD', 'lot': 0.01, 'stop_dollars': 6.30, 'min_conf': 0.85},
    {'name': 'EURUSD', 'lot': 0.01, 'stop_dollars': 5.00, 'min_conf': 0.80},
    {'name': 'US30',   'lot': 0.1,  'stop_dollars': 10.00, 'min_conf': 0.80},
    {'name': 'NAS100', 'lot': 0.1,  'stop_dollars': 10.00, 'min_conf': 0.80},
    {'name': 'BTCUSD', 'lot': 0.01, 'stop_dollars': 20.00, 'min_conf': 0.85},
]

TF = 'M15'

def log(msg, sym='SYSTEM'):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f'[{ts}] [{sym}] {msg}', flush=True)

def load_models():
    models = {}
    for sym_cfg in SYMBOLS:
        sym = sym_cfg['name']
        model_files = sorted(MODEL_DIR.glob(f'xgboost_{sym}_*.pkl'), key=lambda p: p.stat().st_mtime, reverse=True)
        if model_files:
            raw = safe_load_model(model_files[0])
            if isinstance(raw, dict) and 'model' in raw:
                models[sym] = raw
            else:
                models[sym] = {'model': raw, 'feature_names': []}
            log(f'Loaded model: {model_files[0].name}', sym)
        else:
            log('No model found!', sym)
    return models

def get_data(mt5, symbol, n_bars=100):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, n_bars)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def build_features_live(df):
    df = df.copy()
    if 'tick_volume' in df.columns and 'volume' not in df.columns:
        df['volume'] = df['tick_volume']
    df['ret_1'] = df['close'].pct_change(1)
    df['ret_5'] = df['close'].pct_change(5)
    df['ret_10'] = df['close'].pct_change(10)
    df['ma_5'] = df['close'].rolling(5).mean()
    df['ma_10'] = df['close'].rolling(10).mean()
    df['ma_20'] = df['close'].rolling(20).mean()
    df['ma_50'] = df['close'].rolling(50).mean()
    df['ratio_ma5_ma20'] = df['ma_5'] / df['ma_20']
    df['ratio_ma10_ma50'] = df['ma_10'] / df['ma_50']
    tr = pd.concat([df['high']-df['low'], (df['high']-df['close'].shift()).abs(), (df['low']-df['close'].shift()).abs()], axis=1).max(axis=1)
    df['atr_14'] = tr.rolling(14).mean()
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df['rsi_14'] = 100 - (100 / (1 + rs))
    df['volume_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
    for col in ['close', 'volume', 'atr_14']:
        if col in df.columns:
            df[f'{col}_zscore'] = (df[col] - df[col].rolling(20).mean()) / df[col].rolling(20).std().replace(0, np.nan)
    df['high_low_pct'] = (df['high'] - df['low']) / df['close']
    df['close_open_pct'] = (df['close'] - df['open']) / df['open']
    return df

def trade_signal(mt5, sym_cfg, model_dict):
    sym = sym_cfg['name']
    model_data = model_dict.get(sym)
    if model_data is None:
        return None

    df = get_data(mt5, sym, 100)
    if df is None or len(df) < 50:
        return None

    df_feat = build_features_live(df)
    feature_names = model_data.get('feature_names', [])
    if not feature_names:
        feature_names = [c for c in df_feat.columns if c.startswith(('ret_','ma_','ratio_','atr_','rsi_','volume_','high_low','close_open'))]

    model = model_data['model'] if isinstance(model_data, dict) else model_data
    available = [c for c in feature_names if c in df_feat.columns]
    X = df_feat[available].fillna(0).values[-1:].reshape(1, -1)

    proba = model.predict_proba(X)
    confidence = float(max(proba[0]))
    direction = int(model.predict(X)[0])

    return {'direction': direction, 'confidence': confidence, 'proba': proba[0]}

def place_trade(mt5, sym_cfg, direction, confidence):
    sym = sym_cfg['name']
    lot = sym_cfg['lot']
    stop_dollars = sym_cfg['stop_dollars']
    tick = mt5.symbol_info_tick(sym)
    price = tick.ask if direction == 1 else tick.bid
    sl = price - stop_dollars if direction == 1 else price + stop_dollars

    request = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': sym,
        'volume': lot,
        'type': mt5.ORDER_TYPE_BUY if direction == 1 else mt5.ORDER_TYPE_SELL,
        'price': price, 'sl': sl, 'tp': 0.0,
        'deviation': 10, 'magic': 123456,
        'comment': f'MULTI conf={confidence:.2f}',
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        dir_label = 'LONG' if direction == 1 else 'SHORT'
        log(f'{dir_label} @ {price:.2f} SL={sl:.2f} ticket={result.order}', sym)
        return {'ticket': result.order, 'entry': price, 'sl': sl}
    else:
        err = result.comment if result else 'no response'
        log(f'FAILED: {err}', sym)
        return None

def main_loop(interval=300):
    log('Starting Multi-Symbol Bot v1.0')
    models = load_models()
    log(f'Loaded {len(models)} models')

    mt5.initialize()
    log('MT5 initialized')

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not LOG_PATH.exists():
        with open(LOG_PATH, 'w', newline='') as f:
            csv.writer(f).writerow(['timestamp', 'symbol', 'direction', 'confidence', 'entry_price', 'sl', 'ticket', 'status'])

    while True:
        for sym_cfg in SYMBOLS:
            sym = sym_cfg['name']
            try:
                positions = mt5.positions_get(symbol=sym)
                if positions and len(positions) > 0:
                    pos = positions[0]
                    log(f'Open: {pos.type_name} PnL={pos.profit:.2f}', sym)
                    continue

                signal = trade_signal(mt5, sym_cfg, models)
                if signal is None:
                    continue

                if signal['confidence'] >= sym_cfg['min_conf'] and signal['direction'] != -1:
                    result = place_trade(mt5, sym_cfg, signal['direction'], signal['confidence'])
                    if result:
                        with open(LOG_PATH, 'a', newline='') as f:
                            csv.writer(f).writerow([datetime.now().strftime('%Y-%m-%d %H:%M'), sym,
                                'LONG' if signal['direction']==1 else 'SHORT',
                                f'{signal["confidence"]:.3f}',
                                f'{result["entry"]:.2f}', f'{result["sl"]:.2f}',
                                result['ticket'], 'OPEN'])
                else:
                    log(f'No signal: conf={signal["confidence"]:.3f}/{sym_cfg["min_conf"]}', sym)
            except Exception as e:
                log(f'Error: {e}', sym)

        time.sleep(interval)

if __name__ == '__main__':
    main_loop()
