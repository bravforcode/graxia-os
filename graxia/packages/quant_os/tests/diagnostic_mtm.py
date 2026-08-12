import os

from quant_os.backtest.data_loader import load_csv_data
from quant_os.strategies.mtm import MultiTimeframeMomentum

data_dir = os.path.join("graxia", "packages", "quant_os", "data")
csv_path = os.path.join(data_dir, "EURUSD_X.csv")
full_data, full_ts = load_csv_data(csv_path, date_column="Date", date_format="%Y-%m-%d %H:%M:%S%z")
data = {k: v[-500:] for k, v in full_data.items()}

strategy = MultiTimeframeMomentum()
close = data["close"]
high = data.get("high", close)
low = data.get("low", close)
volume = data.get("volume", [0] * len(close))

print(f"MTM Diagnostic — {len(close)} bars")
print(f"{'Bar':<6} {'Signal':<10} {'Score':<8} {'Dir':<6} {'Entry':<10} {'SL':<10} {'TP':<10}")
print("-" * 70)

signal_count = 0
buy_count = 0
sell_count = 0

for i in range(50, len(close)):
    ohlcv = {
        "open": data.get("open", close)[: i + 1],
        "high": high[: i + 1],
        "low": low[: i + 1],
        "close": close[: i + 1],
        "volume": volume[: i + 1],
    }

    signal = strategy.generate_signal(
        symbol="EURUSD",
        ohlcv_data=ohlcv,
        indicators=None,
        regime=None,
    )

    if signal:
        signal_count += 1
        if signal.signal_type.value == "BUY":
            buy_count += 1
        elif signal.signal_type.value == "SELL":
            sell_count += 1

        entry = f"{float(signal.entry_price):.5f}" if signal.entry_price else "N/A"
        sl = f"{float(signal.stop_loss):.5f}" if signal.stop_loss else "N/A"
        tp = f"{float(signal.take_profit):.5f}" if signal.take_profit else "N/A"

        print(
            f"{i:<6} {signal.signal_type.value:<10} {signal.confidence:.2f}    {signal.signal_type.value:<6} {entry:<10} {sl:<10} {tp:<10}"
        )

print(f"\nSummary: {signal_count} signals from {len(close)} bars")
print(f"  BUY: {buy_count}, SELL: {sell_count}")
print(f"  Signal frequency: {signal_count/len(close)*100:.1f}%")
print(f"  Avg trades per year (D1): ~{signal_count/len(close)*365:.1f}")
