# Known Limitations

1. MT5 gateway is read-only stub — not tested live
2. Margin estimate from `order_calc_margin()` does not account for existing positions
3. Swap not modeled in cost calculations
4. Backtest engine still uses close-price fills (Phase 3.1 will fix)
5. ContractSpec snapshots have placeholder SHA-256 hashes
6. No EURUSD or GBPUSD research started
7. No walk-forward, DSR, or PBO analysis yet
8. No shadow mode or demo mode implemented
