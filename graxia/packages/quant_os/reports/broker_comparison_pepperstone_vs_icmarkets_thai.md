# Pepperstone Razor vs IC Markets Raw — XAUUSD Paper Trading (Thai User)

> **Focus:** Speed of setup. Recommendation = whichever gets running fastest for a Thai user.

---

## 1. XAUUSD Spread & Cost per Trade (0.1 lot)

| Metric | Pepperstone Razor | IC Markets Raw |
|---|---|---|
| **Account type** | Razor (raw ECN spreads + $0 commission on commodities) | Raw Spread (raw interbank spreads + $7/rt commission) |
| **XAUUSD avg spread** | ~0.2–0.4 pips (from 0.1 pts) | ~0.7–1.0 pips |
| **Commission on XAUUSD** | **$0** (commodities CFD = 0 commission on Razor) | **$7/round turn** per standard lot |
| **0.1 lot — spread cost** | ~$0.20–$0.40 | ~$0.70–$1.00 |
| **0.1 lot — commission** | $0.00 | $0.70 |
| **0.1 lot — total cost** | **~$0.20–$0.40** | **~$1.40–$1.70** |

> **Winner: Pepperstone.** XAUUSD is commission-free on Razor (commodities CFD), while IC Markets charges $7/rt. Pepperstone's total cost is ~4-8x cheaper per 0.1 lot trade.

---

## 2. Commission Structure ($/lot for XAUUSD)

| Broker | Commission per side | Round turn (open+close) | Cost for 0.1 lot | Cost for 1.0 lot |
|---|---|---|---|---|
| **Pepperstone Razor** | $0 (commodities CFD) | **$0** | $0 | $0 |
| **IC Markets Raw** | $3.50/side | **$7.00** | $0.70 | $7.00 |

Key detail: Pepperstone Razor charges $3.50/side only on **margin FX** (forex pairs). XAUUSD is classified as a **commodity CFD**, which carries **zero commission** on Razor. IC Markets charges $3.50/side on everything including XAUUSD.

---

## 3. MT5 Availability

| Feature | Pepperstone | IC Markets |
|---|---|---|
| **MT5** | ✅ Yes (Windows, Web, iOS, Android) | ✅ Yes (Windows, Web, iOS, Android) |
| Other platforms | MT4, cTrader, TradingView, own platform | MT4, cTrader, TradingView, WebTrader |
| VPS | Free (low latency, collocated) | Free (low latency, NY4) |

**Both brokers fully support MT5.** No advantage either way.

---

## 4. Thai Client Onboarding

| Item | Pepperstone | IC Markets |
|---|---|---|
| **Regulator (entity for TH)** | SCB (Bahamas) | FSA (Seychelles) |
| **Thai language support** | ✅ Full site in ไทย | ✅ Full site in ไทย |
| **Thai Baht (THB) account** | ✅ XAUTHB pair available | ✅ USDTHB listed |
| **Documents needed** | Photo ID (passport/ID card) + Proof of Address (≤6 months) | Photo ID (passport/ID card) + Proof of Address (≤6 months) |
| **Verification time** | ~minutes (digital onboarding) | ~minutes to hours |
| **Minimum deposit** | **$10** | **$0** (no minimum) |
| **Deposit methods** | Visa, MC, PayPal, Skrill, Neteller, bank wire, Apple Pay, Google Pay | Visa, MC, PayPal, Skrill, Neteller, UnionPay, BPay, bank wire |
| **Accepts Thai clients?** | ✅ Yes (not restricted) | ✅ Yes (not restricted; only US, Canada, NZ, Iran, N Korea restricted) |

> **Both accept Thai clients with identical KYC docs.** No advantage.

---

## 5. Account Opening Speed

| Step | Pepperstone | IC Markets |
|---|---|---|
| Registration | ~2 min (email + basic info) | ~2 min (email + basic info) |
| Verification | **Instant digital verification** (auto-ID scan) | Manual review (typically within hours) |
| Demo account | Immediate after registration | Immediate after registration |
| Live account | Same day (often minutes) | Same day (1–24 hours) |
| **Overall estimated time to trade** | **~5–15 minutes** | **~1–24 hours** |

> **Winner: Pepperstone.** Digital onboarding with instant auto-verification = trade-ready in minutes. IC Markets relies on manual account team review which can take hours.

---

## ⭐ Overall Verdict

| Criterion | Winner |
|---|---|
| Lowest cost per XAUUSD trade (0.1 lot) | **Pepperstone** ($0.20 vs $1.40+) |
| Commission-free XAUUSD | **Pepperstone** ($0 vs $7/rt) |
| MT5 availability | Tie |
| Thai client acceptance | Tie |
| Fastest account opening | **Pepperstone** (minutes vs hours) |

### 🏆 Recommendation: Pepperstone Razor

For a Thai user wanting to **paper trade XAUUSD fastest**:

1. **Pepperstone Razor** gives you XAUUSD at raw spreads + **zero commission** (commodities CFD)
2. **Instant digital verification** — no waiting for manual review
3. **$10 min deposit** — low barrier to start live after paper trading
4. **THB-supported pairs available** (XAUTHB)

Go to **[pepperstone.com/en-th/](https://www.pepperstone.com/en-th/)** → Register → Select Razor account → Get demo or fund live → Start trading XAUUSD in under 15 minutes.

---

## Stop-Loss Calculator Script

Created at: `scripts/stop_calculator.py`

**Formula:** `distance = 6.30 / (lot_size * 100)` for XAUUSD

| Lot Size | Distance ($) | Example (entry=$2330.50) Stop-Buy | Example Stop-Sell |
|---|---|---|---|
| 0.01 | 6.30000 | $2324.20 | $2336.80 |
| 0.10 | 0.63000 | $2329.87 | $2331.13 |
| 0.50 | 0.12600 | $2330.37 | $2330.63 |
| 1.00 | 0.06300 | $2330.44 | $2330.56 |

```python
#!/usr/bin/env python3
"""
XAUUSD Stop-Loss Calculator
===========================
Computes stop-loss price distance based on a fixed $6.30 risk threshold.

Formula:
    distance = 6.30 / (lot_size * 100)
    stop_buy  = entry_price - distance   (long position)
    stop_sell = entry_price + distance   (short position)

Verification:
    0.1 lot  -> distance = $0.63
    1.0 lot  -> distance = $0.063

Usage:
    python scripts/stop_calculator.py
"""

import sys


def compute_stop(lot_size: float, entry_price: float) -> dict:
    """Calculate stop distances and levels for XAUUSD."""
    if lot_size <= 0:
        raise ValueError("lot_size must be > 0")
    if entry_price <= 0:
        raise ValueError("entry_price must be > 0")

    distance = 6.30 / (lot_size * 100)
    stop_buy = entry_price - distance
    stop_sell = entry_price + distance

    return {
        "lot_size": lot_size,
        "entry_price": entry_price,
        "distance": round(distance, 5),
        "stop_buy": round(stop_buy, 2),
        "stop_sell": round(stop_sell, 2),
    }


def main() -> None:
    try:
        lot_size = float(input("Enter lot size (e.g. 0.1, 0.5, 1.0): "))
        entry_price = float(input("Enter current XAUUSD price (e.g. 2330.50): "))
    except ValueError:
        print("Error: please enter numeric values.", file=sys.stderr)
        sys.exit(1)

    try:
        result = compute_stop(lot_size, entry_price)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print("\n===== XAUUSD STOP-LOSS CALCULATION =====")
    print(f"  Lot size:          {result['lot_size']}")
    print(f"  Entry price:       ${result['entry_price']:.2f}")
    print(f"  Stop distance:     ${result['distance']:.5f}")
    print(f"  Stop-loss (BUY):   ${result['stop_buy']:.2f}")
    print(f"  Stop-loss (SELL):  ${result['stop_sell']:.2f}")
    print("=========================================")


if __name__ == "__main__":
    main()
```
