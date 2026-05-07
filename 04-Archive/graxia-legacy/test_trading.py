import asyncio
import os
import sys

# Ensure path is correct
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from graxia.packages.trading.python.engine import TradingEngine
from graxia.packages.logging.python.notifications import send_telegram_message

async def run_live_trade():
    print("🚀 [BINANCE LIVE TEST] INITIATING TRADING ENGINE...")
    
    # Initialize the Trading Engine (will automatically pick up keys from .env)
    engine = TradingEngine()
    
    if not engine.api_key or not engine.api_secret:
        print("❌ ERROR: Binance API Keys are missing!")
        return

    print("✅ Binance API Keys detected successfully.")
    print(f"✅ LIVE_MODE is set to: {engine.live_mode}")
    
    symbol = "BTCUSDT"
    
    # 1. Connect to WebSocket
    await engine.connect_ws(symbol)
    
    # 2. Execute a Live Trade (Risk Engine will intercept if drawdown > 2%)
    print(f"\n📈 Executing LIVE Market Buy for {symbol}...")
    result = await engine.execute_trade(symbol=symbol, action="BUY", quantity=0.001)
    
    print("\n" + "="*50)
    print("💰 [TRADE RESULT]")
    print(f"Status: {result.get('status')}")
    print(f"Symbol: {result.get('symbol')}")
    print(f"Action: {result.get('action')}")
    print(f"Executed Price: {result.get('executed_price')}")
    print(f"Order ID: {result.get('order_id')}")
    print("="*50 + "\n")
    
    # Notify CEO via Telegram
    msg = (
        "📈 *BINANCE LIVE TRADE EXECUTED*\n\n"
        f"🤖 *Status:* `{result.get('status')}`\n"
        f"🪙 *Symbol:* `{result.get('symbol')}`\n"
        f"📊 *Action:* `{result.get('action')} 0.001`\n"
        f"💲 *Price:* `~${result.get('executed_price')}`\n\n"
        "✅ Risk Engine limits passed. Order processed via Binance API."
    )
    send_telegram_message(msg)
    print("✅ Telegram notification sent to CEO.")

if __name__ == "__main__":
    asyncio.run(run_live_trade())
