# TASK: Fix Cost Model in backtest_cost.py

## Context
Audit ของ bridge agent พบว่า `scripts/backtest_cost.py` มีปัญหา 3 จุดที่ทำให้ "no edge" conclusion ไม่มี empirical basis:

1. **`evaluate_backtest()` line 214** — references `price` ที่ไม่ defined ใน scope → crash ทุกครั้งที่รัน
2. **`compute_trade_pnl()` line 107** — ใช้ `price = 2350.0` hardcoded แทน bar close price จริงของแต่ละ trade
3. **หน่วยสับสน** — CLI help บอก "dollars" แต่ formula ต้องการ return units; ไม่มีชุด input ไหนที่รู้จักให้ผลลัพธ์ถูกต้อง

## What to fix

### Fix 1: `evaluate_backtest()` — ใช้ราคาจริงต่อแถว

**ปัญหา:** line 214 `total_cost = (spread_cost + slippage_p90) * price * lot_mult * n_trades` ใช้ flat price

**แก้:** เปลี่ยนเป็น sum ของ per-trade cost จาก `pnl_df`:
```python
# แทนที่ line 214:
total_cost = pnl_df["cost_dollars"].sum()  # ใช้ cost ที่คำนวณต่อแถวแล้ว
```

และลบ `price` reference ที่ไม่ defined ออก

### Fix 2: `compute_trade_pnl()` — ใช้ bar close price จริง

**ปัญหา:** line 107 `price = 2350.0` hardcoded ทุก trade ใช้ราคาเดียวกัน

**แก้:** เพิ่ม parameter `close_prices: np.ndarray` แล้วใช้ราคาจริงต่อแถว:
```python
def compute_trade_pnl(
    df, preds, spread_cost, slippage_p90, lot_mult,
    close_prices=None,  # เพิ่ม parameter นี้
):
    target_return = df["target_return"].values
    if close_prices is not None:
        price_arr = close_prices  # ใช้ราคาจริงต่อแถว
    else:
        price_arr = np.full(len(target_return), 2350.0)  # fallback
    ...
    raw_pnl_dollars = raw_pnl_frac * price_arr * lot_mult
    cost_per_trade = (spread_cost + slippage_p90) * price_arr * lot_mult
    net_pnl = raw_pnl_dollars - cost_per_trade
```

### Fix 3: ตัดสินหน่วยให้เด็ดขาด

**กฎ:** `spread_cost` และ `slippage_p90` เป็น **return units เท่านั้น** ทุกที่

- เปลี่ยน CLI help text จาก "dollars" เป็น "return units (fraction of price)"
- เปลี่ยน CLI defaults จาก `0.17/0.39` เป็นค่าจาก `config/cost_calibration.json`:
  - XAUUSD: spread=0.000050, slippage=0.000027
- เปลี่ยน `evaluate_backtest()` defaults ให้ตรงกัน
- เปลี่ยน `compute_trade_pnl()` docstring ให้ชัด

### Fix 4: เพิ่ม sanity test

เพิ่ม test ที่เช็ค broker-realistic bounds:
```python
def test_cost_per_trade_realistic_range():
    """0.01 lot XAUUSD cost per trade must be $0.05–$2.00"""
    cost = compute_cost_per_trade(spread_cost=0.00005, slippage=0.000027, price=2350, lot=0.01)
    assert 0.05 <= cost <= 2.0, f"Cost ${cost:.4f} outside realistic range"
```

## Files to modify
- `scripts/backtest_cost.py` — main fixes
- `tests/test_cost_unit_regression.py` — update/add tests

## Verification
1. `python scripts/backtest_cost.py --symbol XAUUSD --freq 1min` ต้องรันไม่ crash
2. `python -m pytest tests/test_cost_unit_regression.py -v` ต้อง pass
3. JSON output ต้องมี `total_cost` ที่ไม่ใช่ flat `n × rate`
4. ตัวเลข Net P&L ต้องเปลี่ยนจากเดิม (เพราะ cost model เปลี่ยน)

## ไม่ต้องทำ
- ไม่ต้องแก้ `SUMMARY.md` หรือ JSON เก่า — ปล่อยไว้ unverified
- ไม่ต้องแก้ `walk_forward.py` หรือ `wf_patched.py` — แก้แค่ `backtest_cost.py` ก่อน
- ไม่ต้องแก้ `engine.py` — นั่นคนละ code path
