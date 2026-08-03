# SP2 Design (FINAL) — Full Gates Harness

- **Date:** 2026-08-03
- **Status:** FINAL (ปรับตามหลักฐาน: PBO ไม่ใช้กับ single-config trial)
- **Sub-project:** SP2 ของแผน institutional gates (SP1 ✅ เสร็จ)

---

## 1. Problem Statement (หลักฐาน)

1. **kelly bug (P1, pre-existing):** `scripts/institutional_pipeline.py:281` เรียก
   `compute_kelly(win_rate=wr, avg_rr=rr, vol_current=..., vol_target=..., regime=..., spread_cost=...)`
   แต่ `core/kelly.py::DynamicKellySizer.compute_kelly` signature จริง:
   `(win_rate, win_loss_ratio, avg_loss, current_vol, regime="normal", drawdown=0.0)`
   → `TypeError: unexpected keyword 'avg_rr'` → Layer 2c พัง pipeline วิ่งไม่จบ (ยืนยัน baseline)

2. **Harness 1028/1032 มีแค่ 5 gates** (DK, DSR, jackknife, cost-stress, label-shuffle) —
   ขาด WFA / bootstrap CI / MinBTL ที่สถาบันใช้

3. **PBO: ไม่ใช้** — หลักฐาน: pre-reg 1028 "single 12M lookback (not the 3-lookback consensus)",
   pre-reg 1032 "FROZEN — no tuning", "One run. No threshold tuning."
   → ทั้ง 2 trials เป็น **single frozen config โดย design** → ไม่มี parameter search space
   → PBO (Probability of Backtest Overfitting) วัด "search bias เมื่อเลือก best จากหลาย configs"
   ซึ่ง **ไม่มีอยู่จริงใน design นี้** → สร้าง variants หลังเห็นผล = selection bias (ต้องห้าม)
   → PBO = N/A + honest note (แทนการบังคับให้มี)

## 2. Goals / Non-Goals

**Goals:**
- **A:** fix kelly call → pipeline วิ่งครบ 6 layers
- **B:** เพิ่ม WFA (purged-CV) + Bootstrap CI + MinBTL เข้า harness 1028 + 1032
  (PBO = N/A พร้อมเหตุผล บันทึกใน artifact)

**Non-Goals:**
- C (institutional_pipeline data จริง) → SP2b
- Breadth → SP3
- ไม่เปลี่ยน verdict rule (DK ยัง primary)

## 3. Components

### Component A — kelly fix (institutional_pipeline.py:281-285)

`compute_kelly` body (inspect แล้ว): `avg_loss` ใช้แค่ guard (<=0 → return min) — **ไม่ได้ใช้ในสูตร**
`f* = (b·p − q)/b` ขึ้นกับ win_rate + win_loss_ratio เท่านั้น → `avg_loss=1.0` ผ่าน guard ได้ ถูกต้อง

```python
kr = kelly_sizer.compute_kelly(
    win_rate=wr,
    win_loss_ratio=rr,      # FIX: avg_rr → win_loss_ratio (signature จริง)
    avg_loss=1.0,           # FIX: required param — only used as >0 guard; not in formula
    current_vol=vol_current,
    regime="normal",
    # FIX: removed spread_cost (not in signature)
)
```

### Component B — shared `_trial_gates.py` (3 gates)

```python
def run_institutional_gates(
    portfolio_returns: pd.Series,        # daily portfolio returns (aligned)
    returns_by_symbol: dict[str, pd.Series],
    observed_sharpe: float,              # annualized
    n_trials: int,
    n_bars: int,
    annualization_factor: float = 252,
) -> dict:
    """WFA + Bootstrap CI + MinBTL — institutional robustness gates.

    PBO intentionally NOT computed: trials are single frozen-config
    pre-registrations (no parameter search space) — PBO would measure
    search bias that does not exist; fabricating variants post-hoc
    would introduce selection bias. Recorded as N/A.
    """
```

| Gate | Implementation | Threshold |
|---|---|---|
| WFA | `purged_cv(n, n_folds=5, embargo=12)` → per-fold OOS signal Sharpe → mean/std | positive mean |
| Bootstrap CI | `bootstrap_confidence_interval(portfolio_returns, n_resamples=1000, seed=42)` | lower > 0 |
| MinBTL | `min_backtest_length(observed_sharpe, n_trials, factor=√252, current_observations=n_bars)` | sufficient |
| PBO | **N/A** (เหตุผล §1.3) | — |

**WFA detail (signal-compatible):** `purged_cv` คืน (train_idx, test_idx) บน index 0..n
→ สำหรับแต่ละ fold: คำนวณ OOS Sharpe จาก signal*return ใน test window
→ **ไม่ใช่ ML train** — แค่ time-split robustness ของ signal
(ใช้ `purged_cv` จาก validation/walk_forward.py — evidence: signature คืน indices ล้วน)

**MinBTL detail:** ส่ง annualized Sharpe + √252 (SP1 standard) + current_observations = len(portfolio_returns)

### Integration เข้า harness 1028/1032

หลัง DSR block เพิ่ม:
```python
gates = run_institutional_gates(
    portfolio_returns=_port_df["return"],
    returns_by_symbol=returns_by_symbol,
    observed_sharpe=m["sharpe"],
    n_trials=n_trials,
    n_bars=len(_port_df),
)
```
- print WFA/Bootstrap/MinBTL ใน GATE SUMMARY + artifact (`gates` field)
- verdict rule ไม่เปลี่ยน (evidence เพิ่ม)

## 4. Testing

1. `tests/test_trial_gates.py` — helper กับ synthetic: WFA คืน folds, bootstrap CI ถูก, MinBTL sufficient logic, PBO key = "N/A" + reason
2. Re-run 1028/1032 → artifact มี `gates` field
3. `test_ws_a_tsmom.py` ยังผ่าน
4. Smoke `institutional_pipeline.py` วิ่งจบ 6 layers

## 5. Migration / Commits

1. `fix(quant_os): kelly compute_kelly call args (win_loss_ratio, avg_loss) — unblock Layer 2c`
2. `feat(quant_os): _trial_gates helper — WFA/bootstrap/MinBTL institutional gates`
3. `feat(quant_os): wire institutional gates into harness 1028+1032`
4. Re-run + update artifacts

## 6. Out of Scope

- PBO (N/A by design — single frozen config)
- institutional_pipeline data จริง (SP2b)
- Breadth (SP3)
