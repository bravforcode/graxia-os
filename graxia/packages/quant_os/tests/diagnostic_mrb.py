"""Diagnostic: Log indicator values for MRB/MLB to see why they don't trigger"""
import sys, os
sys.path.insert(0, os.getcwd())

import math
from graxia.packages.quant_os.backtest.data_loader import load_csv_data

data_dir = os.path.join("graxia", "packages", "quant_os", "data")
csv_path = os.path.join(data_dir, "EURUSD_X.csv")
data, timestamps = load_csv_data(csv_path, date_column="Date", date_format="%Y-%m-%d %H:%M:%S%z")

close = data["close"][-500:]
high = data["high"][-500:]
low = data["low"][-500:]
volume = data["volume"][-500:]

# Calculate indicators
def ema(prices, period):
    if len(prices) < period:
        return []
    k = 2 / (period + 1)
    result = [sum(prices[:period]) / period]
    for p in prices[period:]:
        result.append((p - result[-1]) * k + result[-1])
    return result

def rsi(prices, period=14):
    if len(prices) < period + 1:
        return [None] * len(prices)
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    result = [None] * period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result.append(100)
        else:
            rs = avg_gain / avg_loss
            result.append(100 - 100 / (1 + rs))
    return result

def bollinger(prices, period=20, std_mult=2):
    if len(prices) < period:
        return [], [], []
    upper, middle, lower = [], [], []
    for i in range(period - 1, len(prices)):
        window = prices[i - period + 1:i + 1]
        mean = sum(window) / period
        std = math.sqrt(sum((x - mean) ** 2 for x in window) / period)
        middle.append(mean)
        upper.append(mean + std_mult * std)
        lower.append(mean - std_mult * std)
    return upper, middle, lower

def adx_calc(high, low, close, period=14):
    if len(close) < period * 2 + 1:
        return [None] * len(close)
    
    trs, pdm, mdm = [], [], []
    for i in range(1, len(close)):
        h_l = high[i] - low[i]
        h_pc = abs(high[i] - close[i-1])
        l_pc = abs(low[i] - close[i-1])
        trs.append(max(h_l, h_pc, l_pc))
        up = high[i] - high[i-1]
        down = low[i-1] - low[i]
        pdm.append(up if up > down and up > 0 else 0)
        mdm.append(down if down > up and down > 0 else 0)
    
    atr_w = sum(trs[:period])
    pdm_w = sum(pdm[:period])
    mdm_w = sum(mdm[:period])
    
    dx_values = []
    for i in range(period, len(trs)):
        atr_w = atr_w - atr_w / period + trs[i]
        pdm_w = pdm_w - pdm_w / period + pdm[i]
        mdm_w = mdm_w - mdm_w / period + mdm[i]
        if atr_w == 0:
            dx_values.append(0)
            continue
        plus_di = pdm_w / atr_w * 100
        minus_di = mdm_w / atr_w * 100
        di_sum = plus_di + minus_di
        dx = abs(plus_di - minus_di) / di_sum * 100 if di_sum > 0 else 0
        dx_values.append(dx)
    
    if len(dx_values) < period:
        return [None] * len(close)
    
    adx_val = sum(dx_values[:period]) / period
    result = [None] * (period * 2)
    for dx in dx_values[period:]:
        adx_val = (adx_val * (period - 1) + dx) / period
        result.append(adx_val)
    
    return result

# Calculate all indicators
ema20 = ema(close, 20)
ema50 = ema(close, 50)
rsi_vals = rsi(close, 14)
bb_upper, bb_middle, bb_lower = bollinger(close, 20, 2.0)
adx_vals = adx_calc(high, low, close, 14)

# Log indicator values
print("=" * 70)
print("  MRB Diagnostic — Indicator Values (last 50 bars)")
print("=" * 70)

print(f"\n  {'Bar':<6} {'Close':<10} {'RSI':<8} {'ADX':<8} {'BB_Lower':<10} {'BB_Upper':<10} {'Stoch_K':<8}")
print(f"  {'-'*60}")

for i in range(max(0, len(close)-50), len(close)):
    r = rsi_vals[i] if i < len(rsi_vals) and rsi_vals[i] is not None else None
    a = adx_vals[i] if i < len(adx_vals) and adx_vals[i] is not None else None
    bl = bb_lower[i - (len(close) - len(bb_lower))] if bb_lower and i >= (len(close) - len(bb_lower)) else None
    bu = bb_upper[i - (len(close) - len(bb_upper))] if bb_upper and i >= (len(close) - len(bb_upper)) else None
    
    # Stochastic (simplified)
    if i >= 14:
        period_high = max(high[i-13:i+1])
        period_low = min(low[i-13:i+1])
        if period_high != period_low:
            stoch_k = (close[i] - period_low) / (period_high - period_low) * 100
        else:
            stoch_k = 50
    else:
        stoch_k = 50
    
    print(f"  {i:<6} {close[i]:<10.5f} {r if r else 'N/A':<8} {a if a else 'N/A':<8} "
          f"{bl if bl else 'N/A':<10} {bu if bu else 'N/A':<10} {stoch_k:<8.1f}")

# Check how often conditions are met
print(f"\n  MRB LONG conditions (ADX<25 + Price<BB_Lower + Stoch<20 + RSI<35):")
long_count = 0
for i in range(len(close)):
    if i >= len(rsi_vals) or rsi_vals[i] is None: continue
    if i >= len(adx_vals) or adx_vals[i] is None: continue
    bl_idx = i - (len(close) - len(bb_lower))
    if bl_idx < 0 or bl_idx >= len(bb_lower): continue
    
    if adx_vals[i] < 25 and close[i] < bb_lower[bl_idx] and rsi_vals[i] < 35:
        long_count += 1

print(f"  Met {long_count} times out of {len(close)} bars ({long_count/len(close)*100:.1f}%)")

print(f"\n  MRB SHORT conditions (ADX<25 + Price>BB_Upper + Stoch>80 + RSI>65):")
short_count = 0
for i in range(len(close)):
    if i >= len(rsi_vals) or rsi_vals[i] is None: continue
    if i >= len(adx_vals) or adx_vals[i] is None: continue
    bu_idx = i - (len(close) - len(bb_upper))
    if bu_idx < 0 or bu_idx >= len(bb_upper): continue
    
    if adx_vals[i] < 25 and close[i] > bb_upper[bu_idx] and rsi_vals[i] > 65:
        short_count += 1

print(f"  Met {short_count} times out of {len(close)} bars ({short_count/len(close)*100:.1f}%)")

# Individual condition frequency
print(f"\n  Individual condition frequency:")
adx_low_count = sum(1 for a in adx_vals if a is not None and a < 25)
rsi_low_count = sum(1 for r in rsi_vals if r is not None and r < 35)
rsi_high_count = sum(1 for r in rsi_vals if r is not None and r > 65)
print(f"  ADX < 25: {adx_low_count}/{len(close)} ({adx_low_count/len(close)*100:.1f}%)")
print(f"  RSI < 35: {rsi_low_count}/{len(close)} ({rsi_low_count/len(close)*100:.1f}%)")
print(f"  RSI > 65: {rsi_high_count}/{len(close)} ({rsi_high_count/len(close)*100:.1f}%)")
