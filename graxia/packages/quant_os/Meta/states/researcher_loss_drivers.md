# สาเหตุที่ระบบเทรดขาดทุน — Loss Driver Analysis
## 2026-06-25 · researcher agent

อ้างอิงข้อมูลจาก: backtest results, stress test, WFO, XGBoost metrics, regime filter eval

---

## 🔴 CRITICAL FINDING #1: ไม่มี Strategy Edge

**ระบบไม่มี edge ที่แท้จริง — ทุก metrics บอกว่าแพ้หรือเสมอ**

| Metric | ค่า | ความหมาย |
|--------|-----|----------|
| XGBoost Accuracy | **54.27%** | แทบไม่ต่างจากสุ่ม (50%) |
| XGBoost Profit Factor | **0.97** | ต่ำกว่า 1.0 = ขาดทุน |
| XGBoost Sharpe | **-0.2012** | ติดลบ |
| WFO Weighted Accuracy | **50.81%** | เสมอเหรียญ |
| WFO Total Net | **-1,304.78** | ขาดทุนสะสม |
| WFO Profit Factor | **0.815** | เสีย cost มากกว่ากำไร |
| Unfiltered Net Pips | **-61.77** | ขาดทุน |
| Best Filter (conf≥0.75) Net Pips | **+5.98** | กำไร 6 pip จาก 62 trades = ขาดทุนเมื่อรวม cost |

**ไม่มี confidence threshold ไหนที่ให้ positive net_pips อย่างมีนัยสำคัญ**

---

## 🔴 CRITICAL FINDING #2: Overfitting ขั้นรุนแรง

| Symptom | ค่า |
|---------|-----|
| Train Accuracy | **100%** |
| OOS Accuracy | **47–63%** (แกว่งสุด) |
| Feature Importance | **0.021–0.026** (ทุก feature เท่ากัน = noise) |

XGBoost **จำ pattern ใน train data ได้หมด** แต่ generalize ไม่ได้
เฉลี่ย OOS accuracy ~50% = random

---

## 🔴 CRITICAL FINDING #3: MRB + MLB ไม่เทรด

| Strategy | Trades | PnL |
|----------|--------|-----|
| MTM | 2 | $91 |
| MRB | **0** | **$0** |
| MLB | **0** | **$0** |

Core strategies (ML-based) ไม่ produce signal เลยที่ threshold ที่ตั้งไว้
เหลือแค่ MTM ตัวเดียวที่เทรด — แค่ 2 ครั้ง

---

## 🔴 CRITICAL FINDING #4: Regime Shift = Death

Stress test ผลเดียวที่ FAIL คือ **regime_shift**:
- PnL degradation: **-155.3%**
- Max drawdown: **631%** (พอร์ตหมด)
- Recovery: **ไม่มี** (null)

ระบบ **ป้องกัน regime change ไม่ได้** — เมื่อ market เปลี่ยน volatility regime
system ยังเทรดเหมือนเดิม → ขาดทุนยับ

---

## 🟡 MAJOR FINDING #5: Cost Structure กินกำไร

| Item | Value |
|------|-------|
| WFO Total Gross | -646.71 |
| WFO Total Cost | 658.05 |
| Profit Factor (after cost) | 0.815 |

ต่อให้มี edge เล็กน้อย (WFO gross ~0) cost ก็กินหมด
- Spread cost: 0.17 pips/trade
- Slippage: 9.7e-05 (p90)
- Typical move: 1.18 pips
- **Signal-to-noise ratio ต่ำมาก**

---

## 🟡 MAJOR FINDING #6: Trade Frequency ต่ำเกินไป

| Confidence | % Bars | Trades | Net Pips |
|-----------|--------|--------|----------|
| ≥0.50 | 48.4% | 482 | -34.74 |
| ≥0.60 | 26.0% | 259 | -0.37 |
| ≥0.70 | 10.8% | 108 | -1.30 |
| ≥0.75 | 6.2% | 62 | +5.98 |

ยิ่ง filter สูง → trades น้อยเกินไปที่จะ statistically significant
62 trades = ไม่มั่นใจว่า edge จริงหรือแค่บังเอิญ

---

## 🎯 Root Cause Prioritization

```
Urgent ──────────────────────────────────────────── Chill
  │                                                      
  │  1. Overfitting (ML) ←─────┐                        
  │  2. No edge (all models)   │                        
  │  3. Zero signal MRB/MLB   ─┤                        
  │  4. Regime shift death     │                        
  │  5. Cost eats edge ○───────┘                        
  │  6. Low trade freq                                  
  │                                                      
```

---

## 📋 Actionable Recommendations

### R1: Retrain ML model with regularization (ด่วน)
ปัจจุบัน: `XGBoost()` default params → overfit 100%
ควร:
```python
XGBoost(
    max_depth=3,           # ลดจาก default (6)
    learning_rate=0.01,    # ช้าแต่ stable
    subsample=0.7,         # bootstrap
    colsample_bytree=0.7,  # random features
    reg_lambda=5.0,        # L2 regularization
    reg_alpha=2.0,         # L1 regularization
    early_stopping_rounds=20
)
```

### R2: Fix MRB + MLB thresholds (ด่วน)
MLB ใช้ threshold P(success) > 0.72 ซึ่งสูงเกินไป → trade น้อยมาก
- Lower threshold to 0.55–0.60
- Add dynamic threshold based on market regime
- Test with backtest: at least 200+ trades per symbol

### R3: Add regime-aware position sizing (ด่วน)
Regime shift = max drawdown 631%
```python
if regime == CRISIS or regime == HIGH_VOLATILITY:
    position_size *= 0.25  # reduce 75%
    max_positions = 1
```

### R4: Validate with simulation (อาทิตย์นี้)
- Run `scripts/stress_test.py` regime_shift scenario AFTER R1-R3
- Target: PnL degradation < 50%, recovery < 1000 min
- Re-run WFO: target profit_factor > 1.2, Sharpe > 0.5

### R5: Benchmark against simple baseline (อาทิตย์นี้)
ถ้า ML model 54% accuracy แพ้ buy-and-hold → ต้องมี benchmark
เปรียบเทียบ XGBoost กับ:
- Simple moving average crossover
- Random classifier (expected ~50%)
- ถ้า ML ไม่ดีกว่า simple → เปลี่ยน approach

---

State saved by researcher agent. 2026-06-25
