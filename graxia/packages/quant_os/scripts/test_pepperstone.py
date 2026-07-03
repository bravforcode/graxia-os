"""Pepperstone connection test"""

import MetaTrader5 as mt5

res = mt5.initialize(
    path=r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe",
    timeout=30000,
)
if not res:
    print("FAIL:", mt5.last_error())
    exit(1)

info = mt5.account_info()
print("=== ACCOUNT ===")
print(f"Login: {info.login}")
print(f"Balance: {info.balance}")
print(f"Equity: {info.equity}")
print(f"Leverage: {info.leverage}")
print(f"Currency: {info.currency}")
print(f"Server: {info.server}")

# XAUUSD
symbol = "XAUUSD"
mt5.symbol_select(symbol, True)
tick = mt5.symbol_info_tick(symbol)
sym = mt5.symbol_info(symbol)
spread = tick.ask - tick.bid
print(f"\n=== {symbol} ===")
print(f"Bid: {tick.bid}")
print(f"Ask: {tick.ask}")
print(f"Spread: {spread:.2f}")
print(f"Contract size: {sym.trade_contract_size}")
print(f"Digits: {sym.digits}")
print(f"Point: {sym.point}")
print(f"Min lot: {sym.volume_min}")
print(f"Max lot: {sym.volume_max}")
print(f"Lot step: {sym.volume_step}")

# H1 bars
bars = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 5)
print("\n=== H1 Bars (last 5) ===")
for b in bars:
    t = b["time"]
    print(f"  {t} O={b['open']:.2f} H={b['high']:.2f} L={b['low']:.2f} C={b['close']:.2f} Vol={b['tick_volume']}")

# D1 bars
bars_d1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 5)
print("\n=== D1 Bars (last 5) ===")
for b in bars_d1:
    t = b["time"]
    print(f"  {t} O={b['open']:.2f} H={b['high']:.2f} L={b['low']:.2f} C={b['close']:.2f} Vol={b['tick_volume']}")

# Symbols
symbols = mt5.symbols_get()
print(f"\nTotal symbols: {len(symbols)}")
metals = [s.name for s in symbols if "XAU" in s.name or "XAG" in s.name]
eurusd = [s.name for s in symbols if "EURUSD" in s.name]
print(f"Metals: {metals}")
print(f"EURUSD variants: {eurusd}")

mt5.shutdown()
