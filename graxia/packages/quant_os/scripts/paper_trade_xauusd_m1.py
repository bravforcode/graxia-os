"""
XAUUSD M1 Paper Trading Bot — Pepperstone Demo

Strategy: XGBoost classifier on M1 features
- Entry: When confidence >= 0.55
- Exit: After 5 bars (target holding period)
- Position size: 0.01 lot (micro)
- Stop loss: 50 points ($5)
- Take profit: 100 points ($10)

Risk Management:
- Max 1 open position at a time
- Max 10 trades per day
- Max 2% risk per trade
"""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import xgboost as xgb
from datetime import datetime, timedelta
from pathlib import Path
import json
import time
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.build_features import compute_features

# ── Configuration ───────────────────────────────────────────────────
PATH = r'C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe'
SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_M1
LOT_SIZE = 0.01  # Micro lot
STOP_LOSS_POINTS = 50  # $5
TAKE_PROFIT_POINTS = 100  # $10
MAX_TRADES_PER_DAY = 10
MAX_RISK_PER_TRADE = 0.02  # 2% of balance

BASE = Path(__file__).parent.parent
FEAT_DIR = BASE / "artifacts" / "features_v2"
LOG_DIR = BASE / "artifacts" / "paper_trades"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── Feature Engineering ─────────────────────────────────────────────
def compute_features(df):
    """Compute technical features for M1 data."""
    features = df.copy()
    
    # Returns
    features["return_1"] = df["close"].pct_change(1)
    features["return_5"] = df["close"].pct_change(5)
    features["return_10"] = df["close"].pct_change(10)
    features["return_20"] = df["close"].pct_change(20)
    features["log_return"] = np.log(df["close"] / df["close"].shift(1))
    
    # Moving averages
    for period in [5, 10, 20, 50]:
        features["sma_" + str(period)] = df["close"].rolling(window=period).mean()
        features["ema_" + str(period)] = df["close"].ewm(span=period, adjust=False).mean()
    
    # MACD
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    features["macd"] = ema12 - ema26
    features["macd_signal"] = features["macd"].ewm(span=9, adjust=False).mean()
    features["macd_hist"] = features["macd"] - features["macd_signal"]
    
    # RSI
    for period in [7, 14, 21]:
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        features["rsi_" + str(period)] = 100 - (100 / (1 + rs))
    
    # Stochastic
    low_14 = df["low"].rolling(window=14).min()
    high_14 = df["high"].rolling(window=14).max()
    features["stoch_k"] = 100 * (df["close"] - low_14) / (high_14 - low_14)
    features["stoch_d"] = features["stoch_k"].rolling(window=3).mean()
    
    # Bollinger Bands
    sma20 = df["close"].rolling(window=20).mean()
    std20 = df["close"].rolling(window=20).std()
    features["bb_upper"] = sma20 + (std20 * 2)
    features["bb_middle"] = sma20
    features["bb_lower"] = sma20 - (std20 * 2)
    features["bb_width"] = (features["bb_upper"] - features["bb_lower"]) / features["bb_middle"]
    features["bb_pct"] = (df["close"] - features["bb_lower"]) / (features["bb_upper"] - features["bb_lower"])
    
    # ATR
    tr1 = df["high"] - df["low"]
    tr2 = abs(df["high"] - df["close"].shift())
    tr3 = abs(df["low"] - df["close"].shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    features["atr_14"] = tr.rolling(window=14).mean()
    
    # Volatility
    features["volatility_10"] = df["close"].pct_change().rolling(window=10).std() * np.sqrt(252)
    features["volatility_20"] = df["close"].pct_change().rolling(window=20).std() * np.sqrt(252)
    
    # Volume
    if df["volume"].sum() > 0:
        features["volume_sma_20"] = df["volume"].rolling(window=20).mean()
        features["volume_ratio"] = df["volume"] / features["volume_sma_20"]
        features["obv"] = (np.sign(df["close"].diff()) * df["volume"]).cumsum()
    
    # Candle
    features["body"] = df["close"] - df["open"]
    features["body_pct"] = features["body"] / df["open"]
    features["upper_shadow"] = df["high"] - df[["open", "close"]].max(axis=1)
    features["lower_shadow"] = df[["open", "close"]].min(axis=1) - df["low"]
    
    # ROC
    features["roc_10"] = df["close"].pct_change(10) * 100
    features["roc_20"] = df["close"].pct_change(20) * 100
    
    return features

# ── Model Training ──────────────────────────────────────────────────
def train_model():
    """Train XGBoost model on historical M1 data."""
    print("Training model on historical data...")
    
    df = pd.read_parquet(FEAT_DIR / "features_XAUUSD_M1.parquet")
    exclude = {"target", "target_return", "symbol", "freq", "target_3class", "hour", "day_of_week", "is_london", "is_ny", "is_overlap"}
    feature_cols = [c for c in df.columns if c not in exclude
                    and df[c].dtype in (np.float64, np.float32, np.int64, np.int32)]
    
    X = df[feature_cols].fillna(0).values[:-5]
    y = df["target"].values[:-5]
    
    model = xgb.XGBClassifier(
        n_estimators=100, max_depth=5, learning_rate=0.1,
        subsample=0.8, colsample_bytree=0.8, random_state=42,
        eval_metric="logloss", verbosity=0
    )
    model.fit(X, y)
    
    acc = (model.predict(X) == y).mean()
    print("Training accuracy: " + str(round(acc, 4)))
    
    return model, feature_cols

# ── Trading Logic ───────────────────────────────────────────────────
class PaperTrader:
    def __init__(self, model, feature_cols):
        self.model = model
        self.feature_cols = feature_cols
        self.trades_today = 0
        self.last_trade_date = None
        self.trade_log = []
        self.open_positions = []
        
    def can_trade(self):
        """Check if we can take a new trade."""
        today = datetime.now().date()
        if self.last_trade_date != today:
            self.trades_today = 0
            self.last_trade_date = today
        
        if self.trades_today >= MAX_TRADES_PER_DAY:
            return False
        
        # Check for open positions
        positions = mt5.positions_get(symbol=SYMBOL)
        if positions and len(positions) > 0:
            return False
        
        return True
    
    def get_signal(self):
        """Get trading signal from model."""
        # Fetch last 100 M1 bars
        rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 100)
        if rates is None or len(rates) < 55:
            return None
        
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df = df.rename(columns={'time': 'timestamp', 'tick_volume': 'volume'})
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        df = df.set_index('timestamp')
        
        # Compute features
        features = compute_features(df)
        
        # Get last row (current bar)
        # Drop time features that require DatetimeIndex
        drop_cols = {"hour", "day_of_week", "is_london", "is_ny", "is_overlap"}
        available_cols = [c for c in self.feature_cols if c not in drop_cols and c in features.columns]
        last_row = features[available_cols].iloc[-1:].fillna(0)
        
        # Predict
        pred = self.model.predict(last_row)[0]
        conf = np.max(self.model.predict_proba(last_row)[0])
        
        return {
            "direction": "LONG" if pred == 1 else "SHORT",
            "confidence": float(conf),
            "price": float(df["close"].iloc[-1]),
            "timestamp": str(df.index[-1]),
        }
    
    def place_trade(self, signal):
        """Place a trade on MT5."""
        if signal["confidence"] < 0.55:
            return None
        
        # Get account info
        account = mt5.account_info()
        balance = account.balance
        
        # Calculate position size (risk 2% per trade)
        risk_amount = balance * MAX_RISK_PER_TRADE
        tick_value = mt5.symbol_info(SYMBOL).trade_tick_value
        lot_size = LOT_SIZE
        
        # Determine order type
        if signal["direction"] == "LONG":
            order_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(SYMBOL).ask
            sl = price - STOP_LOSS_POINTS * mt5.symbol_info(SYMBOL).point
            tp = price + TAKE_PROFIT_POINTS * mt5.symbol_info(SYMBOL).point
        else:
            order_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(SYMBOL).bid
            sl = price + STOP_LOSS_POINTS * mt5.symbol_info(SYMBOL).point
            tp = price - TAKE_PROFIT_POINTS * mt5.symbol_info(SYMBOL).point
        
        # Create order
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": lot_size,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 10,
            "magic": 20260705,
            "comment": "XAUUSD_M1_Paper",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            self.trades_today += 1
            trade = {
                "ticket": result.order,
                "direction": signal["direction"],
                "entry_price": price,
                "sl": sl,
                "tp": tp,
                "confidence": signal["confidence"],
                "timestamp": signal["timestamp"],
                "open_time": str(datetime.now()),
            }
            self.trade_log.append(trade)
            print("  TRADE: " + signal["direction"] + " @ " + str(round(price, 2)) + " conf=" + str(round(signal["confidence"], 4)))
            return trade
        else:
            print("  TRADE FAILED: " + str(result.comment if result else "No result"))
            return None
    
    def save_log(self):
        """Save trade log to file."""
        log_path = LOG_DIR / "trades_XAUUSD_M1.json"
        with open(log_path, "w") as f:
            json.dump(self.trade_log, f, indent=2)

# ── Main Loop ───────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("XAUUSD M1 PAPER TRADING BOT")
    print("=" * 60)
    
    # Connect to MT5
    if not mt5.initialize(PATH):
        print("MT5 connection failed:", mt5.last_error())
        return
    
    account = mt5.account_info()
    print("Connected: " + str(account.login) + " @ " + account.server)
    print("Balance: $" + str(round(account.balance, 2)))
    
    # Train model
    model, feature_cols = train_model()
    
    # Initialize trader
    trader = PaperTrader(model, feature_cols)
    
    print("\nStarting paper trading loop...")
    print("Press Ctrl+C to stop\n")
    
    try:
        while True:
            # Check if market is open
            symbol_info = mt5.symbol_info(SYMBOL)
            if symbol_info is None or not symbol_info.visible:
                mt5.symbol_select(SYMBOL, True)
            
            # Get signal
            signal = trader.get_signal()
            
            if signal and trader.can_trade():
                print("[" + str(datetime.now().strftime("%H:%M:%S")) + "] " + 
                      signal["direction"] + " conf=" + str(round(signal["confidence"], 4)) + 
                      " price=" + str(round(signal["price"], 2)))
                
                # Place trade if confidence is high enough
                if signal["confidence"] >= 0.55:
                    trade = trader.place_trade(signal)
                    if trade:
                        trader.save_log()
            
            # Wait for next bar (60 seconds)
            time.sleep(60)
    
    except KeyboardInterrupt:
        print("\nStopping paper trading bot...")
        trader.save_log()
        print("Trade log saved to: " + str(LOG_DIR / "trades_XAUUSD_M1.json"))
    
    mt5.shutdown()

if __name__ == "__main__":
    main()
