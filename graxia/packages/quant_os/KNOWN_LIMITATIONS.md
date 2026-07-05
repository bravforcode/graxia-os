# Known Limitations

1. **MT5 Gateway (broker/mt5_gateway.py)**: Read-only interface for market data, account info, and contract specifications. Does NOT send orders. **Not the same as** `execution/adapters/mt5.py` which is a fully functional live-order adapter.
2. Margin estimate from `order_calc_margin()` does not account for existing positions
3. Swap not modeled in cost calculations
4. Backtest engine uses close-price fills — Phase 3.1 addressed bar-level resolution; tick-level fill pending
5. ContractSpec snapshots have placeholder SHA-256 hashes
6. No EURUSD or GBPUSD research started
7. Walk-forward implemented for XAUUSD/EURUSD at 15min/1min. DSR and PBO analysis not yet standardized.
