# Known Limitations

1. **MT5 Gateway**: The deprecated `broker/mt5_gateway.py` is read-only. However, **live order capability EXISTS** via `execution/adapters/mt5.py:MT5Adapter.submit_order()` which calls `mt5.order_send()`. The system can send real orders when `live_trading_enabled=True` and MT5 terminal is running. Default mode is `TradingMode.PAPER` with `live_trading_enabled=False`. **DO NOT** assume the system is read-only — always verify current trading mode before starting.
2. Margin estimate from `order_calc_margin()` does not account for existing positions
3. Swap not modeled in cost calculations
4. Backtest engine uses close-price fills — Phase 3.1 addressed bar-level resolution; tick-level fill pending
5. ContractSpec snapshots have placeholder SHA-256 hashes
6. No EURUSD or GBPUSD research started
7. Walk-forward implemented for XAUUSD/EURUSD at 15min/1min. DSR and PBO analysis not yet standardized.
