# Multi-Broker Setup Guide

## Current MT5 Installations Found

| # | Installation Path | Broker | Terminal Hash | Status |
|---|---|---|---|---|
| 1 | `C:\Program Files\MetaTrader 5` | MetaQuotes-Demo (default) | `D0E8209F77C8CF37AD8BF550E51FF075` | Installed, configured |
| 2 | `C:\Program Files\Pepperstone MetaTrader 5` | Pepperstone-Demo | `73B7A2420D6397DFF9014A20F1201F97` | Installed, configured |

**AppData:** `%APPDATA%\MetaQuotes\Terminal\` contains two live terminal instances (hashes above) plus `Common` and `Community` directories.

---

## Adding XM MT5 Demo

1. Download the XM MT5 terminal from: https://www.xm.com/trading-platforms/mt5
2. Run the installer — it will create a separate directory (e.g. `C:\Program Files\XM MT5`)
3. Launch the terminal, search for "XMGlobal-Demo" server, and register a demo account
4. After login, a new hash folder will appear under `%APPDATA%\MetaQuotes\Terminal\`

## Adding IC Markets MT5 Demo

1. Download the IC Markets MT5 terminal from: https://www.icmarkets.com/en/trading-platforms/mt5
2. Run the installer — it will create a separate directory (e.g. `C:\Program Files\IC Markets MT5`)
3. Launch the terminal, search for "ICMarkets-Demo" server, and register a demo account
4. After login, a new hash folder will appear under `%APPDATA%\MetaQuotes\Terminal\`

---

## Python MT5 Singleton Limitation

`MetaTrader5` Python library (`import MetaTrader5 as mt5`) **can only connect to ONE terminal per process**. Calling `mt5.initialize()` a second time with a different path will silently reconnect to the same terminal or fail.

### Workaround: Separate Processes via `multiprocessing`

Run each broker in its own OS process. Communication happens through `multiprocessing.Queue`, `Pipe`, or a shared database.

```python
"""multi_broker.py — Run two MT5 brokers in isolated processes."""
import multiprocessing as mp
import time
from typing import Optional


def broker_worker(broker_name: str, terminal_path: str, queue: mp.Queue) -> None:
    """Connect to one MT5 terminal and collect data."""
    import MetaTrader5 as mt5

    initialized = mt5.initialize(path=terminal_path)
    if not initialized:
        queue.put(f"{broker_name}: mt5.initialize() failed — {mt5.last_error()}")
        return

    queue.put(f"{broker_name}: connected")

    # Example: fetch EURUSD tick data
    rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M1, 0, 100)
    if rates is not None:
        queue.put(f"{broker_name}: received {len(rates)} EURUSD candles")
    else:
        queue.put(f"{broker_name}: no data — {mt5.last_error()}")

    mt5.shutdown()
    queue.put(f"{broker_name}: done")


if __name__ == "__main__":
    brokers = [
        ("MetaQuotes-Demo", r"C:\Program Files\MetaTrader 5\terminal64.exe"),
        ("Pepperstone-Demo", r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"),
    ]

    queue = mp.Queue()
    processes = []

    for name, path in brokers:
        p = mp.Process(target=broker_worker, args=(name, path, queue))
        p.start()
        processes.append(p)

    for p in processes:
        p.join()

    while not queue.empty():
        print(queue.get())
```

For ongoing streaming, replace the one-shot fetch with a loop and use `Queue` to push ticks to a collector process.

---

## Estimated Setup Time & Data Capacity

| Step | Time |
|---|---|
| Download & install XM MT5 | ~5 min |
| Register XM demo account | ~3 min |
| Download & install IC Markets MT5 | ~5 min |
| Register IC Markets demo account | ~3 min |
| Integrate new broker into multi-broker runner | ~15 min |
| **Total per new broker** | **~30 min** |

**Data collection capacity:** Each broker process can run independently 24/7. With 4 brokers, you can collect tick data on ~40–60 symbols simultaneously (limited by CPU core count and network bandwidth, not MT5 itself).
