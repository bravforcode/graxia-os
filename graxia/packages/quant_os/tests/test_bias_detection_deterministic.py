"""
Bias Detection — Deterministic data that TRIGGERS each strategy.

Previous test returned NONE for all strategies (vacuous comparison).
This test creates data designed to trigger specific strategy conditions:
- EMA cross: trending data with crossover point
- RSI: overbought/oversold conditions
- News fade: sudden spike
- etc.

Only reports "CLEAN" if strategy generates a signal on BOTH truncated
and full data AND the signals match. Reports "NO_SIGNAL" if neither
produces a signal (still useful info). Reports "MISMATCH" if signals differ.
"""
import sys
import os
sys.path.insert(0, os.getcwd())

import math
from typing import Dict, List, Optional

from graxia.packages.quant_os.gold_bot.strategies.ema_cross import EMACrossStrategy
from graxia.packages.quant_os.gold_bot.strategies.rsi_divergence import RSIDivergenceStrategy
from graxia.packages.quant_os.gold_bot.strategies.news_fade import NewsFadeStrategy
from graxia.packages.quant_os.gold_bot.strategies.fibonacci import FibonacciStrategy
from graxia.packages.quant_os.gold_bot.strategies.multi_tf_align import MultiTFAlignStrategy
from graxia.packages.quant_os.gold_bot.strategies.bos_choch import BOSCHoCHStrategy
from graxia.packages.quant_os.gold_bot.strategies.supply_demand import SupplyDemandStrategy
from graxia.packages.quant_os.gold_bot.strategies.order_block import OrderBlockStrategy
from graxia.packages.quant_os.gold_bot.strategies.london_breakout import LondonBreakoutStrategy
from graxia.packages.quant_os.gold_bot.strategies.vwap_rejection import VWAPRejectionStrategy
from graxia.packages.quant_os.gold_bot.strategies.liquidity_sweep import LiquiditySweepStrategy
from graxia.packages.quant_os.gold_bot.strategies.fair_value_gap import FairValueGapStrategy
from graxia.packages.quant_os.gold_bot.strategies.opening_range import OpeningRangeStrategy


def make_trending_data(bars=200, direction="up"):
    """Create strongly trending data — triggers EMA cross, multi-TF align, BOS"""
    data = {"M15": {}, "H4": {}, "M1": {}}
    
    base = 2350.0
    for tf, drift, volatility in [("M15", 0.002, 0.0005), ("H4", 0.003, 0.0003), ("M1", 0.001, 0.0008)]:
        closes = []
        highs = []
        lows = []
        opens = []
        volumes = []
        
        price = base
        d = 1 if direction == "up" else -1
        for i in range(bars):
            change = d * drift + random.gauss(0, volatility)
            o = price
            c = price * (1 + change)
            h = max(o, c) * (1 + abs(random.gauss(0, 0.0002)))
            l = min(o, c) * (1 - abs(random.gauss(0, 0.0002)))
            
            opens.append(round(o, 2))
            closes.append(round(c, 2))
            highs.append(round(h, 2))
            lows.append(round(l, 2))
            volumes.append(100000 + random.randint(-20000, 20000))
            price = c
        
        data[tf] = {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes}
    
    return data


def make_rsi_extreme_data(bars=200, rsi_target="oversold"):
    """Create data that pushes RSI to extreme levels"""
    data = {"M15": {}, "H4": {}, "M1": {}}
    
    for tf, vol in [("M15", 0.003), ("H4", 0.002), ("M1", 0.005)]:
        closes = []
        highs = []
        lows = []
        opens = []
        volumes = []
        
        price = 2350.0
        for i in range(bars):
            # Create sharp move in one direction to push RSI
            if rsi_target == "oversold":
                if i > bars * 0.7:
                    change = -0.003  # Sharp decline
                else:
                    change = random.gauss(-0.0005, vol)
            else:  # overbought
                if i > bars * 0.7:
                    change = 0.003  # Sharp rise
                else:
                    change = random.gauss(0.0005, vol)
            
            o = price
            c = price * (1 + change)
            h = max(o, c) * (1 + abs(random.gauss(0, 0.0003)))
            l = min(o, c) * (1 - abs(random.gauss(0, 0.0003)))
            
            opens.append(round(o, 2))
            closes.append(round(c, 2))
            highs.append(round(h, 2))
            lows.append(round(l, 2))
            volumes.append(100000)
            price = c
        
        data[tf] = {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes}
    
    return data


def make_spike_data(bars=200):
    """Create data with sudden spike — triggers news_fade"""
    data = {"M1": {}, "M15": {}, "H4": {}}
    
    for tf, vol in [("M1", 0.0005), ("M15", 0.0003), ("H4", 0.0002)]:
        closes = []
        highs = []
        lows = []
        opens = []
        volumes = []
        
        price = 2350.0
        for i in range(bars):
            if i == bars - 10:
                # Spike! 0.5% move in 10 bars
                change = 0.005
            elif i > bars - 10:
                change = random.gauss(0, vol)
            else:
                change = random.gauss(0, vol)
            
            o = price
            c = price * (1 + change)
            h = max(o, c) * (1 + abs(random.gauss(0, 0.0002)))
            l = min(o, c) * (1 - abs(random.gauss(0, 0.0002)))
            
            opens.append(round(o, 2))
            closes.append(round(c, 2))
            highs.append(round(h, 2))
            lows.append(round(l, 2))
            volumes.append(100000)
            price = c
        
        data[tf] = {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes}
    
    return data


def make_fibonacci_data(bars=200):
    """Create data with swing high/low for fibonacci"""
    data = {"M15": {}, "H1": {}, "H4": {}}
    
    for tf, vol in [("M15", 0.001), ("H1", 0.0008), ("H4", 0.0005)]:
        closes = []
        highs = []
        lows = []
        opens = []
        volumes = []
        
        price = 2350.0
        for i in range(bars):
            if i < bars // 3:
                change = 0.002  # Uptrend
            elif i < bars * 2 // 3:
                change = -0.003  # Downtrend (retracement)
            else:
                change = random.gauss(0, vol)
            
            o = price
            c = price * (1 + change)
            h = max(o, c) * (1 + abs(random.gauss(0, 0.0003)))
            l = min(o, c) * (1 - abs(random.gauss(0, 0.0003)))
            
            opens.append(round(o, 2))
            closes.append(round(c, 2))
            highs.append(round(h, 2))
            lows.append(round(l, 2))
            volumes.append(100000)
            price = c
        
        data[tf] = {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes}
    
    return data


import random
random.seed(42)


def run_bias_test(strategy_class, name, data_generator, data_kwargs=None):
    """Run truncated-vs-full bias test on a strategy"""
    if data_kwargs is None:
        data_kwargs = {}
    
    try:
        strategy = strategy_class()
        data = data_generator(**data_kwargs)
        
        # Get the primary timeframe the strategy uses
        primary_tf = "M15"
        close = data.get(primary_tf, data.get("M15", list(data.values())[0])).get("close", [])
        
        if len(close) < 50:
            return {"strategy": name, "status": "SKIP", "reason": "insufficient data"}
        
        current_price = close[-1]
        
        # Full data
        full_signal = strategy.analyze(data, current_price, "XAUUSD")
        
        # Truncated (80%)
        split = int(len(close) * 0.8)
        truncated = {}
        for tf in data:
            truncated[tf] = {k: v[:split] for k, v in data[tf].items()}
        trunc_price = truncated[primary_tf]["close"][-1]
        trunc_signal = strategy.analyze(truncated, trunc_price, "XAUUSD")
        
        full_dir = full_signal.direction.value if full_signal else "NONE"
        trunc_dir = trunc_signal.direction.value if trunc_signal else "NONE"
        full_score = full_signal.score if full_signal else 0
        trunc_score = trunc_signal.score if trunc_signal else 0
        
        # Classify result
        if full_dir == "NONE" and trunc_dir == "NONE":
            status = "NO_SIGNAL"
        elif full_dir == trunc_dir and abs(full_score - trunc_score) <= 10:
            status = "CLEAN"
        else:
            status = "MISMATCH"
        
        return {
            "strategy": name,
            "status": status,
            "full_dir": full_dir,
            "full_score": full_score,
            "trunc_dir": trunc_dir,
            "trunc_score": trunc_score,
        }
        
    except Exception as e:
        return {"strategy": name, "status": "ERROR", "error": str(e)}


def main():
    print("=" * 70)
    print("  Bias Detection — Deterministic Trigger Data")
    print("=" * 70)
    
    tests = [
        ("ema_cross", EMACrossStrategy, make_trending_data, {"direction": "up"}),
        ("rsi_divergence", RSIDivergenceStrategy, make_rsi_extreme_data, {"rsi_target": "oversold"}),
        ("news_fade", NewsFadeStrategy, make_spike_data, {}),
        ("fibonacci", FibonacciStrategy, make_fibonacci_data, {}),
        ("multi_tf_align", MultiTFAlignStrategy, make_trending_data, {"direction": "up"}),
        ("bos_choch", BOSCHoCHStrategy, make_trending_data, {"direction": "up"}),
        ("supply_demand", SupplyDemandStrategy, make_trending_data, {"direction": "up"}),
        ("order_block", OrderBlockStrategy, make_trending_data, {"direction": "up"}),
        ("london_breakout", LondonBreakoutStrategy, make_trending_data, {"direction": "up"}),
        ("vwap_rejection", VWAPRejectionStrategy, make_trending_data, {"direction": "up"}),
        ("liquidity_sweep", LiquiditySweepStrategy, make_trending_data, {"direction": "up"}),
        ("fair_value_gap", FairValueGapStrategy, make_trending_data, {"direction": "up"}),
        ("opening_range", OpeningRangeStrategy, make_trending_data, {"direction": "up"}),
    ]
    
    results = []
    clean = 0
    no_signal = 0
    mismatch = 0
    error = 0
    skip = 0
    
    for name, cls, gen, kwargs in tests:
        result = run_bias_test(cls, name, gen, kwargs)
        results.append(result)
        
        s = result["status"]
        if s == "CLEAN": clean += 1; icon = "[OK]"
        elif s == "NO_SIGNAL": no_signal += 1; icon = "[--]"
        elif s == "MISMATCH": mismatch += 1; icon = "[!!]"
        elif s == "ERROR": error += 1; icon = "[??]"
        else: skip += 1; icon = "[SK]"
        
        print(f"\n  {icon} {name}")
        print(f"     Full:  {result.get('full_dir', 'N/A')} (score={result.get('full_score', 'N/A')})")
        print(f"     Trunc: {result.get('trunc_dir', 'N/A')} (score={result.get('trunc_score', 'N/A')})")
        if result.get("error"):
            print(f"     Error: {result['error']}")
    
    print(f"\n{'=' * 70}")
    print(f"  RESULTS: {clean} CLEAN, {no_signal} NO_SIGNAL, {mismatch} MISMATCH, {error} ERROR, {skip} SKIP")
    print(f"{'=' * 70}")
    
    if mismatch > 0:
        print(f"\n  CRITICAL: {mismatch} strategies show DIFFERENT signals on truncated vs full data.")
        print(f"  These strategies have unintentional lookahead bias.")
    
    if no_signal > 0:
        print(f"\n  NOTE: {no_signal} strategies did not trigger on test data.")
        print(f"  Bias cannot be tested for these — need different data patterns.")
    
    return results


if __name__ == "__main__":
    main()
