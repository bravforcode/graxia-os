# Broker CFD Terms — Multi-Asset Reference

**Generated:** 2026-07-01  
**Broker:** Pepperstone (Razor account)  
**Account Type:** Demo / Paper Trading  
**Platform:** MetaTrader 5

---

## 1. Symbol Specifications

### XAUUSD (Gold vs USD)

| Property | Value |
|----------|-------|
| Instrument | Spot Gold CFD |
| Contract Size | 100 oz |
| Digits | 2 |
| Point | 0.01 |
| Tick Size | 0.01 |
| Tick Value | $1.00 per tick per 1 lot |
| Min Lot | 0.01 |
| Max Lot | 100 |
| Lot Step | 0.01 |
| Margin (initial) | Varies by leverage (typically 5% = $500/lot at $3,200/oz) |
| Typical Spread | 5–15 points (0.05–0.15 USD) |
| Commission | $0 (Razor — spread-only pricing) |
| Swap Long | ~-3.50 per lot/day |
| Swap Short | ~+1.20 per lot/day |

**Trading Hours:** Sun 22:05 – Fri 21:00 UTC (daily break 21:00–22:05 UTC)  
**Note:** Follows COMEX gold futures session. Liquidity drops during Asian session.

---

### EURUSD (Euro vs US Dollar)

| Property | Value |
|----------|-------|
| Instrument | Spot Forex CFD |
| Contract Size | 100,000 EUR |
| Digits | 5 |
| Point | 0.00001 |
| Tick Size | 0.00001 |
| Tick Value | $1.00 per tick per 1 lot |
| Min Lot | 0.01 |
| Max Lot | 100 |
| Lot Step | 0.01 |
| Margin (initial) | Varies by leverage (typically 3.33% at 1:30 leverage) |
| Typical Spread | 5–12 points (0.5–1.2 pips) |
| Commission | $0 (Razor — spread-only pricing) |
| Swap Long | ~-6.50 per lot/day |
| Swap Short | ~+2.80 per lot/day |

**Trading Hours:** Sun 22:05 – Fri 21:00 UTC (daily break 21:00–22:05 UTC)  
**Note:** Most liquid pair. Tightest spreads during London/NY overlap (13:00–17:00 UTC).

---

### BTCUSD (Bitcoin vs USD)

| Property | Value |
|----------|-------|
| Instrument | Crypto CFD |
| Contract Size | 1 BTC |
| Digits | 2 |
| Point | 0.01 |
| Tick Size | 0.01 |
| Tick Value | $0.01 per tick per 1 lot |
| Min Lot | 0.01 |
| Max Lot | 10 |
| Lot Step | 0.01 |
| Margin (initial) | Varies (typically 10–20% = $6,000–$12,000/lot at $60,000) |
| Typical Spread | 200–2,000 points ($2–$20) |
| Commission | $0 (Razor — spread-only pricing) |
| Swap Long | ~-45.00 per lot/day |
| Swap Short | ~+12.00 per lot/day |

**Trading Hours:** 24/7 (crypto market never closes)  
**Note:** Spread widens significantly on weekends. High volatility during US session. CFD pricing follows spot exchanges (Binance, Coinbase).

---

### ETHUSD (Ethereum vs USD)

| Property | Value |
|----------|-------|
| Instrument | Crypto CFD |
| Contract Size | 1 ETH |
| Digits | 2 |
| Point | 0.01 |
| Tick Size | 0.01 |
| Tick Value | $0.01 per tick per 1 lot |
| Min Lot | 0.01 |
| Max Lot | 10 |
| Lot Step | 0.01 |
| Margin (initial) | Varies (typically 10–20%) |
| Typical Spread | 100–1,000 points ($1–$10) |
| Commission | $0 (Razor — spread-only pricing) |
| Swap Long | ~-22.00 per lot/day |
| Swap Short | ~+6.00 per lot/day |

**Trading Hours:** 24/7 (crypto market never closes)  
**Note:** Follows BTC correlation. Higher spread during low-liquidity hours.

---

## 2. Pepperstone Razor Account — Key Parameters

| Parameter | Value |
|-----------|-------|
| Account Type | Razor (ECN-style) |
| Pricing Model | Spread-only (no commission on metals/forex/crypto CFDs) |
| Execution | MARKET execution |
| Requotes | None (market execution) |
| Slippage | Variable (worse in fast markets) |
| Max Leverage | 1:500 (varies by jurisdiction, 1:30 for EU/UK retail) |
| Negative Balance Protection | Yes |
| Minimum Deposit | $0 (demo), $200 (live) |
| Server | Pepperstone-Demo / Pepperstone-Live |

---

## 3. Risk Parameters

### Per-Symbol Limits

| Symbol | Max Lot | Stops Level | Freeze Level | Notes |
|--------|---------|-------------|--------------|-------|
| XAUUSD | 100 | 0–20 pts | 0–10 pts | Stops level varies by account type |
| EURUSD | 100 | 0–5 pts | 0–5 pts | Very tight stops allowed |
| BTCUSD | 10 | 50–500 pts | 20–100 pts | Wider stops required for volatility |
| ETHUSD | 10 | 50–500 pts | 20–100 pts | Similar to BTC |

### Sizing Recommendations (for $10,000 account)

| Symbol | Conservative (1% risk) | Aggressive (2% risk) |
|--------|----------------------|---------------------|
| XAUUSD | 0.10 lot | 0.20 lot |
| EURUSD | 0.10 lot | 0.20 lot |
| BTCUSD | 0.01 lot | 0.02 lot |
| ETHUSD | 0.01 lot | 0.02 lot |

**Note:** These are guidelines only. Actual sizing depends on stop distance, ATR, and portfolio correlation.

---

## 4. Trading Hours Summary

| Symbol | Market Hours | Break | Best Liquidity |
|--------|-------------|-------|----------------|
| XAUUSD | Sun 22:05 – Fri 21:00 UTC | Daily 21:00–22:05 | London session (07:00–16:00 UTC) |
| EURUSD | Sun 22:05 – Fri 21:00 UTC | Daily 21:00–22:05 | London/NY overlap (13:00–17:00 UTC) |
| BTCUSD | 24/7 | None | US session (13:00–22:00 UTC) |
| ETHUSD | 24/7 | None | US session (13:00–22:00 UTC) |

---

## 5. OMS Routing (Current)

The OMS (`execution/oms.py`) currently routes by asset class:

```python
VENUE_MAP = {
    "metals": "mt5",
    "forex": "mt5",
    "indices": "mt5",
    "crypto": "binance",   # ← Currently routes to Binance adapter
}
```

**Phase 4 Change Required:**  
BTCUSD and ETHUSD should be routed to `mt5` for Pepperstone CFD execution, not `binance`. This requires:
1. Updating `VENUE_MAP["crypto"] = "mt5"`
2. Ensuring `MT5Adapter` handles crypto CFD sizing correctly (contract size = 1, not 100,000)
3. Validating spread tolerance in strategy logic (crypto spreads are 100x wider than forex)

---

## 6. Cost Analysis per 1 Lot

| Symbol | Spread Cost | Commission | Total Round-Trip | Notes |
|--------|------------|------------|-----------------|-------|
| XAUUSD | $0.05–$0.15 | $0 | $0.05–$0.15 | Low cost |
| EURUSD | $0.50–$1.20 | $0 | $0.50–$1.20 | Lowest among majors |
| BTCUSD | $2.00–$20.00 | $0 | $2.00–$20.00 | High cost — factor into edge calc |
| ETHUSD | $1.00–$10.00 | $0 | $1.00–$10.00 | High cost — factor into edge calc |

**Crypto CFD cost note:** The spread cost for BTCUSD is ~100x that of EURUSD. Strategy edge must exceed this threshold to be profitable.

---

## 7. Data Pipeline Integration

### Available Data Files

| Symbol | D1 | H1 | H4 | M15 | M1 | Source |
|--------|----|----|----|----|----|----|
| XAUUSD | ✅ | ✅ | ✅ | ✅ | ✅ | MT5 + yfinance |
| EURUSD | ✅ | ✅ | ✅ | ✅ | ✅ | MT5 + Stooq |
| BTCUSD | ✅ | ✅ | ✅ | ✅ | ✅ | Stooq + Binance |
| ETHUSD | ✅ | ✅ | ✅ | ✅ | ✅ | Stooq + Binance |

### Feature Pipeline Entry Point

```bash
python scripts/data_pipeline.py           # Unified entry point
python scripts/build_features_v3_multi_asset.py  # Multi-asset features
```

---

## 8. SMC Detector Integration

The SMC detectors (`core/smc_detectors.py`) are symbol-agnostic and work on OHLCV data. For crypto CFDs:

- **Order blocks**: Work on any timeframe; crypto has larger blocks due to volatility
- **Fair value gaps**: More frequent in crypto due to thin order books
- **Liquidity sweeps**: Crypto has more stop hunts during Asian session
- **Break of structure**: Higher frequency in crypto — may need filtering

---

## 9. Validation Scripts

| Script | Purpose | Output |
|--------|---------|--------|
| `scripts/validate_mt5_crypto.py` | MT5 connection + symbol validation | `reports/mt5_crypto_validation.json` |
| `scripts/validate_data_multi_asset.py` | CSV data quality for all symbols | `reports/data_validation.json` |
| `scripts/mt5_verify.py` | XAUUSD-specific preflight | Console only |

---

## 10. Open Items

1. **OMS routing update**: Change `crypto` → `mt5` in `execution/oms.py`
2. **Spread filter in strategy**: Add crypto-specific spread tolerance (wider thresholds)
3. **Margin calculation**: Verify MT5 `order_calc_margin()` returns correct values for crypto
4. **Commission model**: Confirm Pepperstone charges $0 commission on crypto CFDs (Razor account)
5. **Swap rates**: Monitor swap costs for overnight positions (crypto swaps are high)

---

*This document is auto-generated by `validate_mt5_crypto.py` and manually curated.*
