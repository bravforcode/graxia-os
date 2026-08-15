"""Quick diagnostic: why does RandomSignalStrategy produce 0 trades on H1?"""

import sys

sys.path.insert(0, ".")

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from quant_os.backtest.engine import BacktestConfig, BacktestEngine, InlineContractSpec, _historical_size
from quant_os.core.enums import SignalType
from quant_os.tests.test_label_shuffling import RandomSignalStrategy, _load_xauusd_h1

data = _load_xauusd_h1()
for k in data:
    data[k] = data[k][-1000:]
print(f"Data: {len(data['close'])} bars")

config = BacktestConfig(
    initial_capital=Decimal("10000"),
    slippage_pips=0.5,
    spread_pips=2.0,
    commission_per_lot=Decimal("3.5"),
    risk_per_trade_bps=100,
    strict_mtf=False,
    max_positions=5,
)

engine = BacktestEngine(config=config)
engine._symbol = "XAUUSD"  # Fix Bug #1: thread real symbol through engine
strat = RandomSignalStrategy(seed=42)
engine.set_strategy(strat)

start = datetime(2020, 1, 1, tzinfo=UTC)
timestamps = [start + timedelta(hours=i) for i in range(len(data["close"]))]
engine.load_data(data, timestamps=timestamps)

# Trace what strategy sees vs what engine does
orig_gen = strat.generate_signal
stats = {"calls": 0, "signals": 0, "exec_calls": 0, "rejected_same_symbol": 0, "rejected_volume": 0, "rejected_sl": 0}


def traced_gen(symbol, ohlcv_data, **kwargs):
    stats["calls"] += 1
    sig = orig_gen(symbol, ohlcv_data, **kwargs)
    if sig is not None:
        stats["signals"] += 1
    return sig


strat.generate_signal = traced_gen

orig_exec = engine._execute_signal


def traced_exec(signal, bar_open, bar_high, bar_low, bar_close, current_time, bar_index, regime_mult=1.0):
    stats["exec_calls"] += 1
    # Check why it might be rejected
    if len(engine.positions) >= config.max_positions:
        pass  # will be rejected
    for pos in engine.positions.values():
        if pos.symbol == signal.symbol:
            stats["rejected_same_symbol"] += 1
            if stats["rejected_same_symbol"] <= 3:
                print(f"REJECTED same-symbol: signal at bar {bar_index}, positions={len(engine.positions)}")
            return
    entry_price = signal.entry_price or bar_close
    contract = InlineContractSpec.for_symbol(signal.symbol)
    volume = _historical_size(
        equity=engine.equity,
        risk_per_trade_bps=config.risk_per_trade_bps,
        entry_price=entry_price,
        stop_loss=signal.stop_loss,
        contract=contract,
    )
    if volume <= 0:
        stats["rejected_volume"] += 1
        if stats["rejected_volume"] <= 3:
            print(
                f"REJECTED volume=0: bar={bar_index}, equity={engine.equity}, entry={entry_price}, sl={signal.stop_loss}"
            )
        return

    if signal.signal_type == SignalType.BUY and signal.stop_loss >= entry_price:
        stats["rejected_sl"] += 1
        if stats["rejected_sl"] <= 3:
            print(f"REJECTED SL direction: BUY but sl={signal.stop_loss} >= entry={entry_price}")
        return
    if signal.signal_type == SignalType.SELL and signal.stop_loss <= entry_price:
        stats["rejected_sl"] += 1
        if stats["rejected_sl"] <= 3:
            print(f"REJECTED SL direction: SELL but sl={signal.stop_loss} <= entry={entry_price}")
        return

    if stats["exec_calls"] <= 3:
        print(f"EXECUTING: {signal.signal_type.value} at bar {bar_index}, vol={volume}")

    return orig_exec(signal, bar_open, bar_high, bar_low, bar_close, current_time, bar_index, regime_mult)


engine._execute_signal = traced_exec

result = engine.run()
trades = result.get("trades", [])
print(f"\nStats: {stats}")
print(f"Trades: {len(trades)}")
for t in trades[:5]:
    print(
        f"  {t['side']} entry={t['entry_price']:.2f} exit={t['exit_price']:.2f} pnl={t['pnl']:.2f} reason={t['close_reason']}"
    )
