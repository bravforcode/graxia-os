# Multi-Horizon Portfolio Redesign — Full-Stack Plan (v1)
### แผนปรับสถาปัตยกรรมระบบเทรดใหม่ทั้งยวง — จาก single-asset intraday classifier สู่ multi-strategy portfolio

**สถานะระบบเดิม (ก่อนแผนนี้):** PBO=100%, deflated t-stat ไม่ significant แม้ single trial (p=0.0695), meta-labeling threshold-search มีลาย signature ของ noise ไม่ใช่ edge จริง — **ปิดเคสแล้ว ไม่ต้องกลับไปต่อ**

**เป้าหมายของแผนนี้ (นิยาม "ดีที่สุด" แบบวัดผลได้):** positive expectancy หลัง cost ที่ผ่าน deflated-Sharpe/PBO test ที่ significant จริง, generalize ข้าม regime ได้, max drawdown ควบคุมได้ชัดเจนล่วงหน้า — ไม่ใช่ "กำไรมากที่สุดขาดทุนน้อยที่สุดพร้อมกัน" ซึ่งไม่มีจริง

**ขอบเขต:** Full stack — data → signal → validation → risk → execution → monitoring, ครอบคลุม XAUUSD / FX / BTC-ETH ในสถาปัตยกรรม portfolio เดียว หลาย horizon พร้อมกัน

**นี่คือเอกสาร architecture + rationale + roadmap** ไม่ใช่ code implementation เต็มรูป — แต่ละ phase ใน roadmap คือ session แยกที่ทำได้จริง

---

## 1. Philosophical Shift — ทำไมต้องเปลี่ยนวิธีคิดทั้งหมด ไม่ใช่แค่เปลี่ยน asset

ปัญหาของระบบเดิมไม่ใช่แค่ "features ไม่ดีพอ" — มันคือการเลือกใช้ paradigm ผิดตั้งแต่ต้น: **ML classifier เรียนรู้ pattern จาก lagging technical indicators บน M15** เป็นการพยายามหา edge จาก statistical pattern-mining บนข้อมูลที่ retail เข้าถึงเหมือนกันหมด — ซึ่ง field นี้พิสูจน์มา 30+ ปีว่าแทบไม่เหลือ edge หลัง cost (Neely & Weller และงานตามมาหลายชิ้นที่ทบทวนไปแล้ว)

แผนใหม่เปลี่ยน paradigm เป็น: **rule-based systematic strategy ที่ harvest risk premium ที่มีเอกสารวิชาการรองรับหนักแน่น** (time-series momentum, carry) แล้วเอา statistical rigor เดียวกับที่เพิ่งใช้ฆ่าระบบเดิม (deflated Sharpe, PBO, walk-forward) มา validate ก่อน deploy

| มิติ | ระบบเดิม | ระบบใหม่ |
|---|---|---|
| Edge source | ML pattern discovery บน lagging indicators | Documented risk premium (momentum, carry) |
| Horizon | M15 intraday | D1/H4 swing, multi-day |
| Model | 158-feature classifier, black-box | Simple rule, 3-8 parameters, transparent |
| Label | Triple-barrier WIN/LOSS/TIMEOUT classification | Continuous vol-scaled position size |
| Validation | Post-hoc (พิสูจน์ว่าตายทีหลัง) | Pre-registered gate ก่อน deploy ทุก phase |
| Diversification | Single-symbol ต่อ model | Portfolio ข้าม asset class + horizon |
| Data ที่เคย "ไร้ประโยชน์" | COT/macro บน M15 — mismatch horizon | COT/macro บน weekly rebalance — match horizon พอดี |

**นัยสำคัญ:** ทีมงานวิจัยระดับ CTA/managed futures (AQR, Man AHL) ไม่ได้ชนะตลาดด้วยการ mine pattern ที่ซับซ้อนกว่าใคร — เขาชนะด้วย simple, transparent, vol-scaled rule + risk management ที่เข้มงวด + diversification ข้าม asset จำนวนมาก นี่คือ template ที่แผนนี้ยึดตาม

---

## 2. Evidence Base — สิ่งที่มีหลักฐานวิชาการรองรับจริง

### 2.1 Time-Series Momentum (TSM) — แกนหลักของแผน

Moskowitz, Ooi & Pedersen (2012) เป็นงานต้นทางที่พิสูจน์ว่า time-series momentum (ไม่ใช่ cross-sectional) ให้ premium บวกสม่ำเสมอข้าม asset class Hurst, Ooi & Pedersen (2017) *A Century of Evidence on Trend-Following Investing* ขยายไปถึงข้อมูลย้อนหลังตั้งแต่ปี 1880 ครอบคลุม 67 ตลาด พบ Sharpe ratio ราว 0.4 สม่ำเสมอแทบทุกทศวรรษ รวมถึงช่วง Great Depression, WWII, และ stagflation ยุค 1970s — นี่คือหนึ่งใน risk premium ที่มีหลักฐานยาวนานที่สุดในวงการ quant finance ทั้งหมด และมี correlation ต่ำหรือติดลบกับ asset class ดั้งเดิม ทำให้เป็น diversifier ที่ดี ไม่ใช่แค่ "อีกกลยุทธ์หนึ่ง"

ข้อควรระวัง: long-run Sharpe ดี แต่ short-period drawdown มีจริงและมีนัยสำคัญ — ต้องตั้ง expectation ให้ถูกตั้งแต่ต้น

### 2.2 Gold (XAUUSD) — fit ที่ดีที่สุดสำหรับ TSM sleeve

ไม่มีงานวิชาการ peer-review ที่แยก gold ออกมาเดี่ยวๆ โดยตรง แต่ gold เป็นหนึ่งใน asset class ที่รวมอยู่ใน multi-asset TSM studies ข้างต้นมาตลอด (เป็น commodity ที่มี trending behavior ชัดเจนที่สุดตัวหนึ่ง) หลักฐานระดับ retail-backtest (ไม่ peer-review, ให้น้ำหนักน้อยกว่า) จากการทดสอบ 8,693 trades พบว่า trend-following (EMA Swing) ชนะ mean-reversion (RSI) บน XAUUSD อย่างชัดเจน และ D1 timeframe ให้ risk-adjusted return ดีกว่า H1 (PF 1.85 vs 1.19) — สอดคล้องทิศทางเดียวกับงานวิชาการแม้จะให้น้ำหนักเป็นหลักฐานสนับสนุนรอง ไม่ใช่หลักฐานหลัก

### 2.3 FX — ต้องระวัง single-pair momentum ที่อ่อนแรงลงแล้ว

จุดสำคัญที่ต้อง flag ตรงๆ: literature หลายชิ้น (Pukthuanthong-Le et al. 2007, Neely et al. 2009) พบว่า **momentum แบบ simple filter/MA rule บน G10 currencies เดี่ยวๆ จางหายไปตั้งแต่ต้นทศวรรษ 1990s** — ยังใช้ได้กับ emerging market currencies เท่านั้นในบางงาน นี่คือเหตุผลที่ **EURUSD เดี่ยวๆ ไม่ใช่ตัวเลือกที่ดีสำหรับ single-pair momentum** — TSM แบบ multi-asset/multi-currency (vol-scaled basket) ยังคง robust ตาม methodology ของ Moskowitz/Hurst แต่นั่นคือ portfolio approach ไม่ใช่ single-pair

FX carry เป็นอีกเส้นทางที่มีหลักฐานหนักแน่นกว่า: excess return ของ carry trade มาจาก compensation สำหรับ crash risk ประมาณ 1 ใน 3 ของ return ทั้งหมด และ Sharpe ของ carry strategy ที่สร้างอย่างดี (valuation-adjusted, vol-targeted) อยู่ราว 0.5-0.9 ในช่วง 24 ปีที่ทดสอบ — **แต่ EURUSD ก็ไม่ใช่ carry pair ที่ดี** เพราะ EUR/USD rate differential เล็กและใกล้เคียงกันมานานเกือบทศวรรษ ต้องใช้คู่ที่มี differential กว้างกว่า

### 2.4 Crypto (BTC/ETH) — cross-sectional แข็งแรงกว่า time-series มาก แต่ต้องมี coin มากกว่า 2 ตัว

หลักฐานแข็งแรงที่สุดของ crypto momentum คือแบบ cross-sectional (long winner quintile / short loser quintile ข้าม universe ของเหรียญจำนวนมาก) — งานที่ apply risk-managed momentum แบบนี้ให้ weekly return เฉลี่ย 3.47% และ annualized Sharpe 1.42 ซึ่งสูงกว่าตลาดดั้งเดิมมาก แต่นี่คือผลจาก portfolio หลายสิบเหรียญ ไม่ใช่ BTC/ETH สองตัว

ด้วย BTC/ETH เท่านั้น เราทำได้แค่ time-series momentum ซึ่งก็มีหลักฐานบวกเช่นกัน (การศึกษา momentum cycle แบบ dynamic พบว่า trend-following ชนะ buy-hold ทั้งบน crypto และ S&P500 โดย crypto ให้ risk-adjusted return สูงกว่า) แต่ควรตั้งเป้า Sharpe ให้ต่ำกว่าตัวเลข cross-sectional ข้างต้นพอสมควร เพราะเป็นคนละ methodology

---

## 3. Asset & Strategy Recommendation — คำแนะนำตรงๆ

นี่คือคำแนะนำของฉัน ไม่ใช่ความจริงสัมบูรณ์ — เหตุผลกำกับไว้ทุกจุดเพื่อให้ท้าทาย/ปรับได้

| Asset | สถานะ | Sleeve | เหตุผล |
|---|---|---|---|
| **XAUUSD** | **เก็บไว้ เป็นแกนหลัก** | TSM/Trend (D1, H4 confirm) | หลักฐานตรงที่สุด, ไม่มี "single-pair momentum จางหาย" ปัญหาแบบ FX |
| **EURUSD** | **ขยาย ไม่ใช่เก็บเดี่ยว** | TSM basket + แยก carry sleeg | เดี่ยวๆ momentum จางไปแล้วตาม literature — ต้องรวมเป็น basket อย่างน้อย 3-4 คู่ (เสนอ: EURUSD, GBPUSD, USDJPY, AUDUSD หรือ USDCHF) เพื่อให้ TSM diversification ทำงานตาม methodology จริง |
| **BTC/ETH** | **เก็บไว้ เป็น TSM sleeve** | TSM/Trend | Cross-sectional ต้องการ coin มากกว่านี้ — ถ้าขยายได้ (ผ่านช่องทางที่ถูกกฎหมายไทย) แนะนำเพิ่มเป็น 4-5 เหรียญสภาพคล่องสูง (เช่น SOL, BNB) เพื่อปลดล็อค cross-sectional edge ที่แข็งแรงกว่า |
| **FX Carry basket** | **เพิ่มใหม่ (แนะนำ)** | Carry, แยกจาก TSM | ต้องเลือกคู่ที่มี rate differential กว้างพอ — ต้อง verify กับ broker จริงว่า swap/rollover cost เท่าไหร่ก่อนเชื่อตัวเลข "clean" จาก academic paper |

**ทำไมไม่ตัด asset ไหนออก:** โครงสร้าง 3 asset class (commodity safe-haven, FX, crypto) ให้ diversification ที่ดีในแง่ correlation ต่ำ/เป็นลบในหลาย regime ตรงกับหลักการ multi-asset TSM/risk-parity — การตัดออกจะทำให้ portfolio โฟกัสแคบลงโดยไม่มีเหตุผลทางสถิติมารองรับ

---

## 4. Portfolio Architecture

```
Portfolio (vol-targeted, e.g. 10-15% annualized)
├── Sleeve A: TSM/Trend (D1, weekly rebalance)
│   ├── XAUUSD
│   ├── FX basket (EURUSD, GBPUSD, USDJPY, AUDUSD)
│   └── BTC, ETH (+ expansion candidates)
├── Sleeve B: FX Carry (weekly/monthly rebalance)
│   └── High-differential pairs (TBD post broker verification)
└── [Sleeve C: Intraday — retained on ice, ไม่ active จนกว่าจะมีเหตุผลใหม่]
```

**Position sizing ต่อ instrument (vol-targeting, มาตรฐาน TSM literature):**

```
position_size(t) = signal(t) × (target_vol / realized_vol(t))
```

**Combination ข้าม sleeve (inverse-vol / risk parity):**

```
sleeve_weight(t) = (1 / realized_vol_sleeve(t)) / Σ(1 / realized_vol_all_sleeves(t))
```

Rebalance รายสัปดาห์ (ไม่ต้อง real-time เหมือนระบบเดิม — นี่คือข้อดีสำคัญของการย้าย horizon เพราะลด execution/latency risk ไปมาก)

**ข้อควรระวังที่ literature เตือนไว้ตรงๆ:** correlation ระหว่าง asset/sleeve มักพุ่งเข้าใกล้ 1 ในช่วง market stress — diversification ลด risk ใน normal condition แต่ไม่ช่วยเรื่อง tail risk เท่าไหร่ ต้องมี portfolio-level kill-switch แยกจาก per-sleeve risk control (ดู Section 6)

---

## 5. Data Layer

| Data type | Frequency | Sleeve ที่ใช้ | หมายเหตุ |
|---|---|---|---|
| OHLC D1/H4 | Daily/4H | ทุก sleeve | มีอยู่แล้วจาก Dukascopy |
| COT Report (CFTC) | Weekly | TSM confirmation, positioning extreme filter | **นี่คือ data ที่เคย "ไร้ impact" บน M15 — สาเหตุคือ mismatch horizon ไม่ใช่ data ไม่มีค่า** ที่ weekly rebalance มันตรง native frequency ของมันพอดี |
| Interest rate differential / swap points | Daily | Carry sleeve | ต้องดึงจาก broker จริง ไม่ใช่ theoretical rate |
| DXY, real yields | Daily | Gold sleeve (confirmation filter) | |
| Funding rate, on-chain flow | Daily/Hourly | Crypto sleeve (ถ้าต้องการ refine เพิ่ม) | |

**Data integrity requirement (บทเรียนจากระบบเดิม):** ทุก data pipeline ต้อง point-in-time correct + มี unit test ตรวจ cost-unit/scale bug แบบที่เจอมาก่อน (bug ที่ทำให้ PnL เพี้ยน 2000x) — ทำ automated sanity-check ก่อนใช้ทุกครั้ง ไม่ใช่ตรวจด้วยตาหลัง fact

---

## 6. Signal & Validation Methodology

### 6.1 Signal construction — เลือกได้ 2 แบบมาตรฐาน

**แบบ 1 — Sign-of-return (Moskowitz et al. original):**
```
signal(t) = sign(return over lookback window)   # เช่น 20-60 trading days สำหรับ D1
```

**แบบ 2 — EMA-crossover trend (Baz et al. 2015, ใช้จริงใน AHL/Man-style CTA):**
```
signal(t) = f(EMA_fast(t) - EMA_slow(t)) ผสมหลาย time horizon แล้ว normalize
```

แนะนำเริ่มจากแบบ 1 (parameter น้อยกว่า, ตีความง่ายกว่า, overfitting risk ต่ำกว่า) — แบบ 2 ค่อยพิจารณาเป็น refinement รอบสอง

**หลักการสำคัญ:** parameter ต่อ signal ควรมีแค่ 2-4 ตัว (lookback window, vol-target, rebalance freq) ไม่ใช่ 158 features — ยิ่งน้อย parameter ยิ่งยาก overfit และยิ่งตรวจสอบ statistical significance ได้ตรงไปตรงมากว่า

### 6.2 Statistical Gates — ใช้ toolkit เดียวกับที่เพิ่งฆ่าระบบเดิม

ทุก candidate strategy ต้องผ่านทุกข้อก่อนขยับไป phase ถัดไป (ตัวเลขที่เสนอเป็น engineering heuristic ที่มีเหตุผลรองรับ ไม่ใช่มาตรฐานสากลตายตัว — ปรับได้ถ้ามีเหตุผล):

| Gate | เกณฑ์ที่เสนอ | อ้างอิงจาก |
|---|---|---|
| Deflated Sharpe | Reject H0 (Sharpe=0) ที่ 95% confidence | Bailey & Lopez de Prado (2014) — เครื่องมือเดียวกับที่ใช้ฆ่า t-stat=1.48 |
| PBO | < 50% (ต่ำกว่าเดา), < 20% ก่อนขึ้น live capital | Bailey et al. PBO framework |
| Label/trial deflation | Deflate ตามจำนวน config ที่ลองจริงเสมอ — ห้ามรายงาน best-of-N เป็น point estimate | บทเรียนจาก meta-labeling threshold-fishing ที่เพิ่งเจอ |
| Walk-forward | Out-of-sample period ที่ไม่เคยแตะเลย ≥30% ของ total sample | มาตรฐานทั่วไป |
| Effective N check | คำนวณ label uniqueness ก่อนเชื่อ sample size เสมอ | บทเรียนจาก effective N 5K vs raw 60K |

---

## 7. Risk Management Layer

- **Position-level:** vol-targeted sizing ต่อ instrument (Section 4)
- **Strategy-level:** max drawdown limit ต่อ sleeve → ลด allocation หรือหยุด sleeve นั้นถ้าชน
- **Portfolio-level:** correlation monitoring แบบ real-time — ถ้า correlation ข้าม sleeve พุ่งเกิน threshold (เช่น regime stress) ให้ลด gross exposure อัตโนมัติ ไม่รอ manual intervention
- **Kill-switch:** ต้อง **แก้ P0 finding เดิมที่ยังค้างอยู่ก่อน** (kill-switch persistence ยังไม่ได้ confirm) — นี่คือ infra requirement ที่ต้องทำไม่ว่าจะเปลี่ยน strategy อะไรก็ตาม ไม่ขึ้นกับแผนนี้เลย ต้องปิดก่อน phase ใดๆ ที่แตะ live/paper capital
- **Stress testing:** replay portfolio ผ่านช่วง regime-defining event ในอดีต (COVID 2020 crash, 2022 macro reset เป็นต้น) ก่อนขึ้น live

**Architectural boundary ที่ยังต้อง apply เหมือนเดิม:** LLM agent (Hermes, OpenClaude CLI) ใช้ orchestration/monitoring/log triage ได้ แต่ห้ามแตะ order placement, position sizing, หรือ kill-switch enforcement — เหมือน constraint เดิมที่วางไว้ ไม่เปลี่ยนแค่เพราะ strategy เปลี่ยน

---

## 8. Execution Layer

- **Frequency ลดลงมาก** เทียบระบบเดิม (weekly/daily rebalance vs M15) → latency/slippage sensitivity ต่ำกว่าเดิมมาก นี่คือข้อดีเชิงโครงสร้างของการย้าย horizon
- **MT5 CFD สำหรับ BTC/ETH:** เป็นช่องทางที่แตกต่างจาก spot crypto exchange (Bybit/OKX ที่ Thai SEC สั่งบล็อกไปตั้งแต่ 28 มิ.ย. 2025 และยังบังคับใช้ต่อเนื่อง — มีคดีเพิ่มเติมที่ SEC ยื่นฟ้อง broker ที่ไทยที่พยายาม route ผ่าน affiliated overseas platform เมื่อ ก.พ. 2026) — CFD ผ่าน broker ที่กำกับดูแลในต่างประเทศ (เช่น CySEC/FCA/ASIC) น่าจะเป็นคนละ regulatory lane จาก spot exchange โดยตรง **แต่ต้อง verify สถานะ broker ปัจจุบันก่อนเริ่ม ไม่ใช่สมมติว่าปลอดภัยอัตโนมัติ** — นี่คือ open item ใน Section 10
- **Carry sleeve:** P&L จริงมาจาก swap/rollover ที่ broker เรียกเก็บ/จ่ายสำหรับ position ข้ามคืน —ตัวเลขนี้มักต่างจาก "clean" forward-implied carry ใน paper เพราะ broker มักเก็บ spread เพิ่ม ต้องดึงตัวเลข swap จริงจาก broker ก่อนคำนวณ expected Sharpe ไม่ใช้ตัวเลข textbook

---

## 9. Monitoring & Observability Layer

ใช้ stack เดิมที่มีอยู่แล้ว (Prometheus + Grafana + Loki + OpenTelemetry) — แปลง "Four Golden Signals" ให้เป็นบริบทเทรด:

| Golden Signal (ทั่วไป) | แปลงเป็นบริบทเทรด |
|---|---|
| Latency | เวลาจาก signal generation → order confirm |
| Traffic | ความถี่ signal ต่อ sleeve, data feed update rate |
| Errors | Order rejection rate, data feed staleness, kill-switch trigger count |
| Saturation | Portfolio heat (% ของ vol budget ที่ใช้ไป), correlation ข้าม sleeve |

**Alert ที่ต้องมี (ต่อยอดจาก alerts.yml template เดิม):**
```yaml
- alert: PortfolioDrawdownBreach
  expr: portfolio_drawdown_pct > threshold
  labels: {severity: critical}
- alert: CrossSleeveCorrelationSpike
  expr: sleeve_correlation_realized > 0.7
  labels: {severity: warning}
- alert: DataFeedStale
  expr: time() - last_bar_timestamp > 3600
  labels: {severity: critical}
- alert: KillSwitchTriggered
  expr: kill_switch_active == 1
  labels: {severity: critical}
```

SLO-style target: data feed uptime 99.5%+, kill-switch response < 1 rebalance cycle (ไม่ต้อง sub-second เหมือนระบบเดิมเพราะ horizon เปลี่ยนไปแล้ว)

---

## 10. Phased Roadmap

| Phase | Entry criteria | งานหลัก | Exit/Gate criteria |
|---|---|---|---|
| **0 — Close old P0s** | เริ่มได้เลย | Confirm kill-switch persistence, confirm live-vs-demo status ของระบบเดิม | ทั้งสองข้อ confirm แล้วเป็นลายลักษณ์อักษร |
| **1 — Data infra** | Phase 0 เสร็จ | Build D1/H4 multi-asset pipeline + COT + swap-rate feed, unit test cost/scale bugs | Data ผ่าน sanity check ทุกจุด, point-in-time verified |
| **2 — Signal implementation** | Phase 1 เสร็จ | Implement TSM (gold, FX basket, crypto), carry (FX) — 2-4 parameter ต่อ signal | Code review, parameter count ≤4 ต่อ signal |
| **3 — Statistical validation** | Phase 2 เสร็จ | รัน deflated Sharpe, PBO, walk-forward ต่อทุก candidate | ผ่านทุก gate ใน Section 6.2 |
| **4 — Portfolio construction** | Phase 3 เสร็จ (≥1 sleeve ผ่าน) | Vol-targeting + inverse-vol combination ข้าม sleeve | Portfolio-level backtest ผ่าน gate เดียวกัน |
| **5 — Paper trading** | Phase 4 เสร็จ | Deploy พร้อม monitoring stack เต็มรูป | ≥8-12 สัปดาห์, live slippage ใกล้เคียง backtest assumption, ไม่มี kill-switch false trigger |
| **6 — Small live capital** | Phase 5 เสร็จ + broker/regulatory verify แล้ว | ขึ้น capital น้อยที่สุดที่มีความหมาย | Drawdown limit ไม่ถูกชน, correlation monitoring ทำงานจริง |

---

## 11. Open Decisions ที่ยังรอ input

1. **FX basket สุดท้าย** — ยืนยัน 3-4 คู่ที่จะใช้ (เสนอ EURUSD/GBPUSD/USDJPY/AUDUSD ข้างต้น)
2. **Carry pair selection** — ต้องดู broker ที่ใช้จริงว่า swap rate เท่าไหร่ก่อนเลือกคู่
3. **Crypto universe expansion** — ขยายเกิน BTC/ETH ได้ไหมภายใต้ข้อจำกัดกฎหมายไทย (ต้อง verify ช่องทางที่ถูกต้องก่อน)
4. **Capital allocation ข้าม sleeve** — เท่ากันหมด หรือ weight ตาม confidence ของหลักฐาน (TSM > carry ตาม evidence strength ข้างต้น)?
5. **อนาคตของ intraday sleeve เดิม** — เก็บไว้เป็น sleeve เสริมระยะยาว หรือปิดถาวร?

---

## References (ไม่ verbatim quote, paraphrase + attribution ตามหลัก)

- Moskowitz, Ooi & Pedersen (2012), "Time Series Momentum," *Journal of Financial Economics*
- Hurst, Ooi & Pedersen (2017), "A Century of Evidence on Trend-Following Investing," AQR / *Journal of Portfolio Management*
- Baz, Granger, Harvey, Le Roux, Rattray (2015), trend-signal construction methodology (EMAC), referenced in currency/crypto momentum literature
- Bailey & Lopez de Prado (2014), "The Deflated Sharpe Ratio," *Journal of Portfolio Management*
- Bailey, Borwein, Lopez de Prado & Zhu (2014), "Pseudo-Mathematics and Financial Charlatanism," *Notices of the AMS*
- Neely & Weller (1999/2003), intraday FX technical trading, market efficiency evidence
- Pukthuanthong-Le et al. (2007); Neely et al. (2009) — G10 single-pair momentum decay evidence
- FX carry crash-risk decomposition: Farhi et al. (2015), Chen (2017); Macrosynergy valuation-adjusted carry research
- Crypto cross-sectional risk-managed momentum: Barroso & Santa-Clara (2015) methodology applied to crypto, ScienceDirect 2025
- Dynamic time-series momentum in cryptocurrency markets, ScienceDirect
- Thailand SEC blocking order on Bybit/OKX/CoinEx/1000X/XT.COM, effective 28 June 2025, ongoing enforcement through Feb 2026 (multiple news sources: Cointelegraph, The Block, CoinDesk, Lex Bangkok)
