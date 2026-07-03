# 🔧 Integration Plan: Borrowed Patterns → Graxia Quant OS

> **Date**: 2026-06-26
> **Status**: DRAFT — รอ user approve ก่อนเริ่ม implement
> **Methodology**: Deep dive ทั้ง Graxia codebase + 5 source repos แล้ว synthesize

---

## 📋 สรุปสิ่งที่ Graxia มีอยู่แล้ว

| Module | สถานะ | ความเห็น |
|--------|-------|----------|
| `strategies/base.py` | ✅ ดี | ABC Strategy, Signal dataclass, position sizing |
| `backtest/engine.py` | ✅ ดีมาก | Event-driven, lookahead guard, MTF cursor, fill model |
| `risk/engine.py` | ✅ ดี | 17 pre-trade checks, kill switch, circuit breaker |
| `execution/manager.py` | ✅ ดี | Order state machine, idempotency, human approval |
| `core/config.py` | ✅ ดี | Dataclass config, env override, hard limits |
| `core/enums.py` | ✅ ดี | Comprehensive enums for all states |

**Graxia ไม่ได้แย่ — แต่มีจุดที่ pattern จาก repos อื่นจะช่วยได้มาก**

---

## 🎯 5 Patterns ที่จะนำมาใช้

### Pattern 1: Strategy API Enhancement (from jesse-ai/jesse)

**สิ่งที่ jesse ทำดี:**
```python
# jesse's pattern —简洁明了
class GoldenCross(Strategy):
    def should_long(self):
        return ta.ema(self.candles, 8) > ta.ema(self.candles, 21)

    def go_long(self):
        entry_price = self.price - 10
        qty = utils.size_to_qty(self.balance * 0.05, entry_price)
        self.buy = qty, entry_price
        self.take_profit = qty, entry_price * 1.2
        self.stop_loss = qty, entry_price * 0.9
```

**สิ่งที่ Graxia มีอยู่:**
```python
# Graxia's current pattern — ดีแต่ verbose
class Strategy(ABC):
    @abstractmethod
    def generate_signal(self, symbol, ohlcv_data, indicators, regime) -> Optional[Signal]:
        pass
```

**สิ่งที่จะเปลี่ยน:**

| File | เปลี่ยน | รายละเอียด |
|------|---------|-------------|
| `strategies/base.py` | ➕ เพิ่ม | `should_enter()` / `should_exit()` helper methods |
| `strategies/base.py` | ➕ เพิ่ม | `self.price` / `self.balance` convenience properties |
| `strategies/base.py` | ➕ เพิ่ม | `hyperparameters()` method for Optuna integration |
| `strategies/base.py` | ➕ เพิ่ม | `on_trade_closed()` callback for strategy adaptation |

**ไม่เปลี่ยน:**
- `generate_signal()` ยังคงเป็น primary API (Graxia ต้องการ Signal object ที่มี metadata)
- `Signal` dataclass ยังคงมี confidence, regime, indicator_values (jesse ไม่มี)

**ข้อจำกัด:**
- jesse ใช้ `self.buy = qty, price` syntax → Graxia ต้องใช้ `Signal` object แทน
- Graxia มี `RegimeType` filter ที่ jesse ไม่มี → รักษาไว้

---

### Pattern 2: Risk Management Enhancement (from kvrancic/algorithmic-trading-bot)

**สิ่งที่ kvrancic ทำดี:**
```python
# Kelly Criterion position sizing
kelly_fraction = 0.25  # ใช้แค่ 25% ของ Kelly
position_size = kelly_fraction * (win_rate - (1-win_rate)/odds)

# VaR analysis
var_95 = np.percentile(returns, 5)

# Multi-model ensemble
ensemble_pred = weighted_avg([xgb_pred, lstm_pred, cnn_pred])
```

**สิ่งที่ Graxia มีอยู่:**
```python
# Graxia's current risk engine — ดีแต่ missing Kelly + VaR
class RiskEngine:
    async def check_order(self, order) -> RiskCheckResult:
        # 13 checks แต่ไม่มี Kelly sizing หรือ VaR
```

**สิ่งที่จะเปลี่ยน:**

| File | เปลี่ยน | รายละเอียด |
|------|---------|-------------|
| `risk/position_sizer.py` | ➕ เพิ่ม | Kelly Criterion sizing method |
| `risk/engine.py` | ➕ เพิ่ม | VaR-based exposure check |
| `risk/engine.py` | ➕ เพิ่ม | Correlation-based portfolio risk |
| `risk/pre_trade_risk.py` | ➕ เพิ่ม | Max drawdown trailing stop |

**ไม่เปลี่ยน:**
- 13 existing risk checks ยังคงทำงานเหมือนเดิม
- Kill switch / circuit breaker ไม่แตะ
- Order state machine ไม่แตะ

**ข้อจำกัด:**
- Kelly Criterion ต้องการ historical win rate + avg win/loss → ต้อง track เพิ่ม
- VaR ต้องการ returns distribution → ต้องคำนวณจาก equity curve

---

### Pattern 3: Performance Optimization (from cyclux/tradeforce)

**สิ่งที่ tradeforce ทำดี:**
```python
# Numba JIT — 100k+ records/sec
@numba.njit
def simulate_strategy(prices, signals):
    ...

# Arrow format — fast data loading
import pyarrow as pa
table = pa.ipc.open_file('data.arrow').read_all()

# Optuna hyperparameter search
study = optuna.create_study(direction='maximize')
study.optimize(objective, n_trials=100)
```

**สิ่งที่ Graxia มีอยู่:**
```python
# Graxia's backtest engine — pure Python, no JIT
class BacktestEngine:
    def run(self):
        for i in range(1, total_bars):
            # Pure Python loop — ช้าสำหรับ large datasets
```

**สิ่งที่จะเปลี่ยน:**

| File | เปลี่ยน | รายละเอียด |
|------|---------|-------------|
| `backtest/engine.py` | ➕ เพิ่ม | `_calculate_indicators_numba()` สำหรับ hot path |
| `backtest/engine.py` | ➕ เพิ่ม | Batch processing mode สำหรับ large datasets |
| `core/hyperopt.py` | 🔧 ปรับปรุง | Optuna integration ที่มีอยู่ให้ดีขึ้น |
| `backtest/data_loader.py` | ➕ เพิ่ม | Arrow format support |

**ไม่เปลี่ยน:**
- Event-driven architecture ไม่แตะ (Graxia ต้องการ lookahead guard)
- Decimal precision ไม่แตะ (Graxia ใช้ Decimal สำหรับ financial accuracy)
- Fill model ไม่แตะ

**ข้อจำกัด:**
- Numba ไม่สามารถ JIT โค้ดที่ใช้ Decimal ได้ → ต้อง convert ชั่วคราว
- Arrow format ต้องเพิ่ม dependency (`pyarrow`)
- ต้องวัด performance gain ก่อน optimise

---

### Pattern 4: Multi-Agent Architecture (from tauricresearch/tradingagents)

**สิ่งที่ tradingagents ทำดี:**
```
Analyst Team (4 agents) → Researcher Team (Bull/Bear debate) → Trader → Risk Management → Portfolio Manager
```

**สิ่งที่ Graxia มีอยู่:**
```
Strategy → Signal → RiskEngine → OrderManager → Broker
```

**สิ่งที่จะเปลี่ยน:**

| File | เปลี่ยน | รายละเอียด |
|------|---------|-------------|
| `core/agents/` | ➕ ใหม่ | Agent framework (lightweight, ไม่ใช่ LLM) |
| `core/agents/analyst.py` | ➕ ใหม่ | Technical analyst agent |
| `core/agents/researcher.py` | ➕ ใหม่ | Bull/Bear debate agent |
| `core/agents/risk_auditor.py` | ➕ ใหม่ | Risk audit agent |
| `strategies/ensemble.py` | 🔧 ปรับปรุง | ใช้ multi-agent pipeline แทน weighted average |

**ไม่เปลี่ยน:**
- ไม่ใช้ LLM (Graxia ต้อง deterministic)
- ไม่ใช้ LangGraph (Graxia ต้อง lightweight)
- Risk engine ยังคงเป็น pre-trade check

**ข้อจำกัด:**
- Graxia ต้อง deterministic → ใช้ rule-based agents ไม่ใช่ LLM agents
- Multi-agent pipeline ต้องไม่เพิ่ม latency มากเกินไป
- ต้อง backward compatible กับ strategy ที่มีอยู่

---

### Pattern 5: Event-Driven Design (from letianzj/quanttrader)

**สิ่งที่ quanttrader ทำดี:**
```python
# Event-driven architecture
class Portfolio:
    def on_bar(self, event):
        for strategy in self.strategies:
            signal = strategy.on_bar(event)
            if signal:
                self.execute(signal)

# GUI monitoring
class LiveTraderWindow:
    def update_chart(self, trade):
        ...
```

**สิ่งที่ Graxia มีอยู่:**
```python
# Graxia ใช้ callback-based — ใกล้เคียงแต่ไม่ใช่ event-driven
class BacktestEngine:
    def run(self):
        for i in range(1, total_bars):
            signal = self.strategy.generate_signal(...)
            if signal:
                self._execute_signal(signal, ...)
```

**สิ่งที่จะเปลี่ยน:**

| File | เปลี่ยน | รายละเอียด |
|------|---------|-------------|
| `core/events.py` | ➕ ใหม่ | Event types (BarEvent, SignalEvent, OrderEvent, FillEvent) |
| `core/event_bus.py` | ➕ ใหม่ | Event bus สำหรับ decouple components |
| `backtest/engine.py` | 🔧 ปรับปรุง | ใช้ event bus แทน direct method calls |
| `execution/manager.py` | 🔧 ปรับปรุง | Subscribe to OrderEvent |

**ไม่เปลี่ยน:**
- Strategy ABC ยังคงเดิม
- Risk engine ยังคงเป็น pre-trade check
- ไม่ต้องมี GUI (Graxia ใช้ Telegram + API)

**ข้อจำกัด:**
- Event bus ต้อง lightweight (ไม่ใช่afka/RabbitMQ)
- ต้องไม่ breaking change กับ strategies ที่มีอยู่
- Backtest engine ต้องยัง lookahead-safe

---

## 📅 Implementation Roadmap

### Phase A: Foundation (Week 1-2)

| Task | Pattern | ไฟล์ที่แตะ | Scope | Dependencies |
|------|---------|-------------|-------|--------------|
| A1: Strategy helper methods | jesse | `strategies/base.py` | XS | None |
| A2: Kelly Criterion sizing | kvrancic | `risk/position_sizer.py` | S | None |
| A3: Event types definition | quanttrader | `core/events.py` | XS | None |

### Phase B: Core Integration (Week 3-4)

| Task | Pattern | ไฟล์ที่แตะ | Scope | Dependencies |
|------|---------|-------------|-------|--------------|
| B1: Event bus | quanttrader | `core/event_bus.py` | M | A3 |
| B2: VaR risk check | kvrancic | `risk/engine.py` | S | A2 |
| B3: Hyperparameter helpers | jesse | `strategies/base.py` | XS | A1 |
| B4: Numba hot path | tradeforce | `backtest/engine.py` | M | None |

### Phase C: Advanced Integration (Week 5-6)

| Task | Pattern | ไฟล์ที่แตะ | Scope | Dependencies |
|------|---------|-------------|-------|--------------|
| C1: Multi-agent pipeline | tradingagents | `core/agents/` | L | B1 |
| C2: Arrow data loader | tradeforce | `backtest/data_loader.py` | S | None |
| C3: Ensemble refactor | tradingagents | `strategies/ensemble.py` | M | C1 |
| C4: Backtest event-driven | quanttrader | `backtest/engine.py` | M | B1 |

### Phase D: Validation (Week 7)

| Task | Pattern | ไฟล์ที่แตะ | Scope | Dependencies |
|------|---------|-------------|-------|--------------|
| D1: Performance benchmark | tradeforce | `tests/` | S | B4 |
| D2: Integration tests | all | `tests/` | M | All |
| D3: Documentation | all | `docs/` | S | All |

---

## ⚠️ Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking existing strategies | HIGH | ทุก change ต้อง backward compatible |
| Performance regression | MEDIUM | Benchmark ก่อน/หลัง ทุก change |
| Dependency bloat | LOW | ใช้ optional imports (numba, pyarrow) |
| Complexity increase | MEDIUM | ทุก module ต้องมี tests |
| License conflict | LOW | ใช้ MIT/Apache-2.0 patterns เท่านั้น |

---

## 🎯 Success Criteria

1. **Backtest speed**: ≥2x เร็วขึ้นสำหรับ 100k+ bars (from Numba)
2. **Strategy authoring**: เขียน strategy ได้เร็วขึ้น 30% (from jesse pattern)
3. **Risk management**: VaR + Kelly sizing ทำงานได้ถูกต้อง
4. **Multi-agent**: Ensemble strategy ใช้ agent pipeline ได้
5. **No regression**: ทุก test ที่มีอยู่ยังผ่าน

---

## 📝 Next Action

รอ user approve plan นี้ แล้วเริ่ม Phase A (Foundation) ซึ่งเป็น change ที่เล็กที่สุดและไม่มี dependencies
