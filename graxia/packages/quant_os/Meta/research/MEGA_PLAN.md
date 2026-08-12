# MEGA PLAN — Production Trading System Architecture

**Date:** 2026-06-27
**Goal:** Build the best Data Ingestion Pipeline + Production Trading Bot that won't break with real money
**Architecture:** Distributed State Machine (not a script — a system)

---

## PART 0: TOOL ANALYSIS VERDICTS

### The Anti-Framework Stack (2026 Meta)

| Component | Tool | Verdict | Stars | License | Why |
|-----------|------|---------|-------|---------|-----|
| **The Crawler** | Crawl4AI | ✅ USE | 69.7k | Apache-2.0 | Async, anti-bot bypass, Markdown output for LLM |
| **The Brain** | DeepSeek-R1 | ⚠️ EVALUATE (Phase 3+) | — | MIT | Too slow for real-time (5-30s). Good for batch news sentiment |
| **The Memory** | DuckDB | ✅ USE | 39.1k | MIT | In-process OLAP, ASOF JOIN, Parquet native, zero-config |
| **The Execution** | NautilusTrader | ⚠️ EVALUATE | 24.2k | LGPL-3.0 | Rust core, sub-μs latency. But: no MT5/Pepperstone adapter |

### Other Tools

| Tool | Verdict | Role |
|------|---------|------|
| **TradingView** | ✅ USE | Signal design layer + webhook alerts → FastAPI |
| **OpenBB** | ⚠️ EVALUATE | Historical data + macro context. AGPLv3 risk — use REST API only |
| **FinceptTerminal** | ⚠️ EVALUATE | $10,200/yr commercial license. Maintenance declining |
| **DeepForex** | ❌ SKIP | Not a real product. Abandoned GitHub repos |

### The Honest Truth

```
What works in 2026 for XAUUSD with real money:

✅ Crawl4AI → Economic calendar + news scraping
✅ DuckDB → Tick/OHLCV storage + analytics
✅ TradingView → Visual signal design + webhook alerts
✅ DeepSeek-R1 → Batch news sentiment (Phase 3+, not real-time)
✅ quant_os → Custom engine (already built)
✅ Pepperstone → Broker (already chosen)

⚠️ NautilusTrader → Best engine, but no MT5 adapter. Hybrid approach.
⚠️ OpenBB → Good for macro data, AGPLv3 license risk.
❌ DeepForex → Abandoned. Build custom ML pipeline instead.
❌ FinceptTerminal → Too expensive, declining maintenance.
```

---

## PART 1: THE 6 BACKBONE SYSTEMS

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    KILL SWITCH (Telegram)                    │
│              "ปุ่มแดง" — Cancel All + Market Close            │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    TELEMETRY LAYER                           │
│         Telegram Alerts + Grafana Dashboard + Logs           │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   DATA      │  │   ALPHA     │  │   RISK              │  │
│  │   FEEDER    │→ │   ENGINE    │→ │   ENGINE            │  │
│  │             │  │             │  │                       │  │
│  │ MT5 Ticks   │  │ 13 Strat    │  │ Position Sizing     │  │
│  │ Crawl4AI    │  │ ML Models   │  │ Daily Loss Limit    │  │
│  │ DuckDB      │  │ Regime      │  │ Max Drawdown        │  │
│  └─────────────┘  └─────────────┘  └──────────┬──────────┘  │
│                                                │              │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────▼──────────┐  │
│  │   POSITION  │  │   FAULT     │  │   OMS & EXECUTION   │  │
│  │   LEDGER    │← │   TOLERANCE │← │   ENGINE            │  │
│  │             │  │             │  │                       │  │
│  │ Local State │  │ Idempotent  │  │ Order Management    │  │
│  │ Reconcile   │  │ Heartbeat   │  │ Partial Fills       │  │
│  │ Cost Track  │  │ Recovery    │  │ TWAP/VWAP           │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

### System 1: Data Feeder (ดึงข้อมูล)

**Role:** Clean, validated market data → Alpha Engine

**Components:**
```
MT5 Ticks ──→ ┌──────────────┐ ──→ DuckDB (Parquet)
               │ Quality Gate │
Crawl4AI   ──→ │ - Schema     │ ──→ Memory Cache (OHLCV window)
               │ - Range      │
TradingView ─→ │ - Sequence   │ ──→ Event Bus (NATS/asyncio.Queue)
               │ - Stale      │
               └──────────────┘
```

**Tech Stack:**
| Layer | Tool | Why |
|-------|------|-----|
| Tick Data | MetaTrader5 PyPI | Direct from Pepperstone |
| News/Calendar | Crawl4AI | Async, anti-bot, Markdown output |
| Storage | DuckDB + Parquet | ASOF JOIN, hive partitioning |
| Quality Gate | Custom (existing) | 8-check validation |
| Cache | asyncio.Queue | Zero dependency, <1μs latency |

**DuckDB Schema:**
```sql
-- Tick data (hive partitioned)
CREATE TABLE ticks (
    timestamp TIMESTAMP,
    bid DOUBLE,
    ask DOUBLE,
    spread_points INTEGER,
    symbol VARCHAR,
    source VARCHAR
) PARTITION BY (symbol, year, month);

-- OHLCV bars
CREATE TABLE ohlcv (
    time TIMESTAMP,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume DOUBLE,
    symbol VARCHAR,
    timeframe VARCHAR
);

-- News events (from Crawl4AI)
CREATE TABLE news_events (
    timestamp TIMESTAMP,
    event VARCHAR,
    impact VARCHAR,  -- HIGH/MEDIUM/LOW
    actual DOUBLE,
    forecast DOUBLE,
    previous DOUBLE,
    source VARCHAR
);

-- ASOF JOIN: align news to nearest tick
SELECT t.*, n.event, n.impact
FROM ticks t
ASOF JOIN news_events n
ON t.symbol = n.symbol AND t.timestamp >= n.timestamp;
```

**Implementation Priority:** P0 (Week 1-2)

---

### System 2: Alpha Engine (สมองคิดกลยุทธ์)

**Role:** Clean data → Signals (NEVER executes orders)

**Output Format:**
```python
@dataclass(frozen=True)
class Signal:
    symbol: str           # "XAUUSD"
    side: str             # "BUY" | "SELL"
    conviction: float     # 0.0 - 1.0
    strategy: str         # "ema_cross" | "multi_tf_align" | ...
    entry_price: float    # Suggested entry
    stop_loss: float      # Suggested SL
    take_profit: float    # Suggested TP
    timestamp: datetime
    regime: str           # Current market regime
    confidence: float     # Model confidence
    metadata: Dict        # Strategy-specific data
```

**Components:**
```
Clean Data → ┌──────────────────┐ → Signal
              │ Strategy Router  │
              │ (Regime-based)   │
              │                  │
              │ ┌──────────────┐ │
              │ │ 13 Strategies│ │
              │ │ (existing)   │ │
              │ └──────────────┘ │
              │ ┌──────────────┐ │
              │ │ ML Models    │ │
              │ │ (XGBoost)    │ │
              │ └──────────────┘ │
              │ ┌──────────────┐ │
              │ │ Regime Filter│ │
              │ │ (ADX/ATR)   │ │
              │ └──────────────┘ │
              └──────────────────┘
```

**Key Rules:**
1. Alpha Engine outputs Signal ONLY — never calls order_send
2. Signal is immutable (frozen dataclass)
3. Multiple strategies can signal same symbol — Risk Engine decides
4. Regime filter gates which strategies are active

**Implementation Priority:** P0 (exists, needs bug fixes)

---

### System 3: Risk Engine (เกราะคุมความเสี่ยง)

**Role:** Gate between Signal and Execution. "ตัวเบรกของระบบ"

**Decision Flow:**
```
Signal → ┌─────────────────────────────────────────┐ → APPROVE/REJECT
          │ Risk Engine                               │
          │                                           │
          │ 1. Position Sizing (Kelly/Vol Targeting)  │
          │ 2. Daily Loss Limit (2% equity)           │
          │ 3. Max Drawdown (15% hard stop)           │
          │ 4. Portfolio Exposure (80% max)            │
          │ 5. Correlation Check                       │
          │ 6. Regime Adjustment                       │
          │ 7. Contract Validation                     │
          │ 8. Stale Data Check                        │
          │                                           │
          │ IF any check FAILS → REJECT + log reason  │
          │ IF all PASS → APPROVE with sized quantity  │
          └─────────────────────────────────────────┘
```

**Position Sizing Formula:**
```python
# Volatility-targeting (recommended over Kelly)
target_vol = 0.15  # 15% annualized portfolio vol
realized_vol = rolling_volatility(returns, window=20)
vol_scalar = target_vol / realized_vol
position_size = base_size * vol_scalar * regime_multiplier

# Regime multipliers
REGIME_MULT = {
    "CRISIS": 0.0,        # No trading
    "HIGH_VOLATILITY": 0.25,  # 75% reduction
    "LOW_VOLATILITY": 0.75,
    "TRENDING_UP": 1.0,
    "TRENDING_DOWN": 1.0,
    "RANGING": 0.8,
}
```

**Hard Limits (Immutable):**
| Limit | Value | Override |
|-------|-------|----------|
| Max risk per trade | 1% equity | Never |
| Hard stop drawdown | 15% | Never |
| Daily loss limit | 2% equity | Never |
| Weekly loss limit | 5% equity | Never |
| Max portfolio exposure | 80% | Never |
| Max positions | 20 | Never |

**Implementation Priority:** P0 (exists, needs CVaR + real-time monitoring)

---

### System 4: OMS & Execution Engine (มือทำงาน)

**Role:** Approved Signal → Real Orders on Pepperstone MT5

**This is where most bots die.** The OMS must handle:

```
Approved Signal → ┌───────────────────────────────┐ → Order Result
                   │ OMS & Execution Engine         │
                   │                                 │
                   │ 1. Order Creation               │
                   │    - Generate unique order_id   │
                   │    - Store in ledger (idempotent)│
                   │                                 │
                   │ 2. Order Submission             │
                   │    - Send to MT5                │
                   │    - Handle partial fills       │
                   │    - Retry logic (max 3)        │
                   │                                 │
                   │ 3. Order Monitoring             │
                   │    - Track fill status          │
                   │    - Detect timeouts (30s)      │
                   │    - Handle rejections          │
                   │                                 │
                   │ 4. TWAP/VWAP (large orders)     │
                   │    - Split into child orders    │
                   │    - Time-weighted execution    │
                   └───────────────────────────────┘
```

**Idempotency Pattern:**
```python
class OMS:
    def submit_order(self, signal: Signal) -> OrderResult:
        # Check if order already exists (idempotency)
        existing = self.ledger.get_by_signal_id(signal.signal_id)
        if existing:
            return existing  # Don't double-submit

        # Create order with unique ID
        order = Order(
            order_id=uuid4(),
            signal_id=signal.signal_id,
            symbol=signal.symbol,
            side=signal.side,
            quantity=self.risk_engine.approve(signal),
            status="PENDING",
        )

        # Store BEFORE sending (crash recovery)
        self.ledger.save(order)

        # Submit to broker
        result = self.broker.send(order)

        # Update status
        order.status = result.status
        self.ledger.update(order)

        return result
```

**Partial Fill Handling:**
```python
def handle_partial_fill(self, order: Order, fill: Fill):
    order.filled_quantity += fill.quantity
    order.remaining_quantity = order.quantity - order.filled_quantity

    if order.remaining_quantity > 0:
        # Wait for more fills or timeout
        if time.now() - order.created_at > TIMEOUT_SECONDS:
            # Cancel remaining, keep what we got
            self.broker.cancel(order.order_id)
            order.status = "PARTIALLY_FILLED"
    else:
        order.status = "FILLED"

    self.ledger.update(order)
```

**Implementation Priority:** P0 (Week 3-4)

---

### System 5: Position & Accounting Ledger (สมุดบัญชี)

**Role:** Track positions, P&L, costs — LOCAL STATE ONLY

**Critical Rule:** "ห้ามดึงยอด Balance จาก API กระดานเทรดมาคำนวณกลยุทธ์สดๆ เด็ดขาด"

```python
@dataclass
class Position:
    position_id: str
    symbol: str
    side: str           # "BUY" | "SELL"
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    swap_cost: float
    commission: float
    opened_at: datetime
    updated_at: datetime

@dataclass
class Account:
    equity: float
    cash: float
    margin_used: float
    margin_available: float
    daily_pnl: float
    weekly_pnl: float
    total_pnl: float
    positions: List[Position]
    last_reconciled: datetime
```

**Reconciliation (Daily):**
```python
async def reconcile(self):
    """Compare local state vs broker. Alert on mismatch."""
    local_positions = self.ledger.get_all_positions()
    broker_positions = await self.mt5.get_positions()

    for local in local_positions:
        broker = find_by_symbol(broker_positions, local.symbol)
        if broker is None:
            ALERT("Position mismatch! Local has {local.symbol}, broker doesn't")
        elif abs(local.quantity - broker.volume) > 0.001:
            ALERT("Quantity mismatch! Local={local.quantity}, Broker={broker.volume}")

    # Check balance
    local_equity = self.account.equity
    broker_equity = await self.mt5.account_equity()
    if abs(local_equity - broker_equity) > 100:  # $100 tolerance
        ALERT("Equity mismatch! Local={local_equity}, Broker={broker_equity}")
```

**Implementation Priority:** P0 (Week 3-4)

---

### System 6: Fault Tolerance & Recovery (ระบบฟื้นคืนชีพ)

**Role:** Handle "สุดวิสัย" — network down, power outage, API crash

**Components:**

```
┌─────────────────────────────────────────────────┐
│ Fault Tolerance System                            │
│                                                   │
│ ┌─────────────┐  ┌─────────────┐  ┌───────────┐ │
│ │ Heartbeat   │  │ Crash       │  │ Idempotent│ │
│ │ Monitor     │  │ Recovery    │  │ Orders    │ │
│ │             │  │             │  │           │ │
│ │ Ping every  │  │ On restart: │  │ Check     │ │
│ │ 5 seconds   │  │ 1. Load     │  │ ledger    │ │
│ │             │  │    state    │  │ before    │ │
│ │ If no pong  │  │ 2. Reconcile│  │ submit    │ │
│ │ for 30s →   │  │ 3. Resume   │  │           │ │
│ │ ALERT       │  │    or halt  │  │           │ │
│ └─────────────┘  └─────────────┘  └───────────┘ │
│                                                   │
│ ┌─────────────┐  ┌─────────────┐  ┌───────────┐ │
│ │ Kill Switch │  │ Circuit     │  │ Dead Man  │ │
│ │             │  │ Breaker     │  │ Switch    │ │
│ │ Telegram    │  │             │  │           │ │
│ │ command →   │  │ 3 losses    │  │ If no     │ │
│ │ Cancel All  │  │ in a row →  │  │ heartbeat │ │
│ │ + Close All │  │ Pause 30min │  │ for 5min  │ │
│ │             │  │             │  │ → HALT    │ │
│ └─────────────┘  └─────────────┘  └───────────┘ │
└─────────────────────────────────────────────────┘
```

**Crash Recovery Sequence:**
```python
async def on_startup(self):
    """Run on every startup — handles crash recovery."""

    # 1. Load persisted state
    state = await self.ledger.load_state()

    # 2. Reconcile with broker
    await self.reconcile()

    # 3. Check for orphaned orders
    pending_orders = self.ledger.get_pending_orders()
    for order in pending_orders:
        broker_status = await self.mt5.get_order_status(order.order_id)
        if broker_status is None:
            # Order never reached broker — safe to retry
            order.status = "RETRY"
        elif broker_status == "FILLED":
            # Order was filled but we crashed before recording
            order.status = "FILLED"
            self.ledger.update(order)

    # 4. Resume trading if all checks pass
    if self.all_checks_pass():
        self.status = "RUNNING"
    else:
        self.status = "HALTED"
        ALERT("System halted due to failed startup checks")
```

**Implementation Priority:** P1 (Week 5-6)

---

## PART 2: DATA INGESTION PIPELINE (Best in Class)

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    DATA INGESTION PIPELINE                        │
│                                                                   │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────────┐   │
│  │ MT5      │───→│ Quality Gate │───→│ DuckDB               │   │
│  │ Ticks    │    │ (8 checks)   │    │ (Parquet/Hive)       │   │
│  └──────────┘    └──────────────┘    └──────────────────────┘   │
│                                                                   │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────────┐   │
│  │ Crawl4AI │───→│ NLP Extract  │───→│ DuckDB               │   │
│  │ News     │    │ (structured) │    │ (news_events table)  │   │
│  └──────────┘    └──────────────┘    └──────────────────────┘   │
│                                                                   │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────────┐   │
│  │TradingView───→│ Webhook      │───→│ Signal Queue         │   │
│  │ Alerts   │    │ Receiver     │    │ (asyncio.Queue)      │   │
│  └──────────┘    └──────────────┘    └──────────────────────┘   │
│                                                                   │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────────┐   │
│  │ OpenBB   │───→│ Macro Data   │───→│ DuckDB               │   │
│  │ (Phase2) │    │ (FRED/IMF)   │    │ (macro_features)     │   │
│  └──────────┘    └──────────────┘    └──────────────────────┘   │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Event Bus                              │   │
│  │  asyncio.Queue (Phase 1) → NATS (Phase 2+)               │   │
│  │  - tick.new → Alpha Engine                                │   │
│  │  - news.new → Sentiment Analyzer                          │   │
│  │  - signal.new → Risk Engine                               │   │
│  │  - order.fill → Position Ledger                           │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Implementation Order

| Week | Component | Priority | Effort |
|------|-----------|----------|--------|
| 1 | MT5 → DuckDB tick pipeline | P0 | 3 days |
| 1 | Quality gate integration | P0 | 2 days |
| 2 | OHLCV bar aggregation | P0 | 2 days |
| 2 | Event bus (asyncio.Queue) | P0 | 1 day |
| 3 | Crawl4AI economic calendar | P1 | 3 days |
| 3 | Crawl4AI news scraper | P1 | 2 days |
| 4 | TradingView webhook receiver | P1 | 1 day |
| 4 | News → DuckDB pipeline | P1 | 2 days |
| 5 | ASOF JOIN for news alignment | P2 | 1 day |
| 6 | OpenBB macro data | P2 | 2 days |
| 7 | NATS migration (if needed) | P3 | 3 days |

---

## PART 3: DISTRIBUTED STATE MACHINE

### State Diagram

```
                    ┌─────────┐
                    │  INIT   │
                    └────┬────┘
                         │ startup checks pass
                    ┌────▼────┐
                    │ RUNNING │◄─────────────────┐
                    └────┬────┘                   │
                         │                        │
              ┌──────────┼──────────┐             │
              │          │          │             │
         ┌────▼───┐ ┌───▼────┐ ┌──▼──────┐      │
         │ SIGNAL │ │ RISK   │ │ EXECUTE │      │
         │ GEN    │→│ CHECK  │→│ ORDER   │      │
         └────────┘ └────────┘ └────┬────┘      │
                                     │            │
                              ┌──────┼──────┐     │
                              │             │     │
                         ┌────▼───┐  ┌──────▼──┐  │
                         │ FILLED │  │ REJECTED│  │
                         └────┬───┘  └─────────┘  │
                              │                    │
                         ┌────▼────┐               │
                         │ MONITOR │               │
                         └────┬────┘               │
                              │                    │
              ┌───────────────┼───────────────┐    │
              │               │               │    │
         ┌────▼───┐    ┌─────▼────┐   ┌──────▼──┐ │
         │ MODIFY │    │ CLOSE    │   │ RECONCILE│ │
         │ SL/TP  │    │ POSITION │   │          │ │
         └────────┘    └──────────┘   └──────────┘ │
                                                    │
                    ┌──────────┐                    │
                    │ HALTED   │ ← kill switch ─────┘
                    └──────────┘ ← circuit breaker
                    ┌──────────┐
                    │ RECOVERY │ ← crash detected
                    └──────────┘
```

### State Persistence

```python
class SystemState(Enum):
    INIT = "INIT"
    RUNNING = "RUNNING"
    HALTED = "HALTED"
    RECOVERY = "RECOVERY"
    SHUTDOWN = "SHUTDOWN"

@dataclass
class PersistedState:
    system_state: SystemState
    positions: List[Position]
    pending_orders: List[Order]
    daily_pnl: float
    daily_trades: int
    last_heartbeat: datetime
    kill_switch_active: bool
    circuit_breaker_trips: int
    last_reconciled: datetime

    def save(self, path: str = "state/system_state.json"):
        """Atomic write — write to temp, then rename."""
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(asdict(self), f, default=str)
        os.replace(tmp, path)  # Atomic on POSIX

    @classmethod
    def load(cls, path: str = "state/system_state.json") -> "PersistedState":
        if not os.path.exists(path):
            return cls.default()
        with open(path) as f:
            return cls(**json.load(f))
```

---

## PART 4: IMPLEMENTATION ROADMAP

### Phase 1: Foundation (Week 1-4) — "ไม่พังกลางทาง"

| Week | Task | Deliverable |
|------|------|-------------|
| 1 | MT5 → DuckDB tick pipeline | `data/mt5_tick_ingester.py` |
| 1 | Quality gate integration | `data/quality_gate.py` (enhanced) |
| 2 | Event bus (asyncio.Queue) | `core/event_bus.py` |
| 2 | OHLCV bar aggregation | `data/bar_aggregator.py` |
| 3 | OMS with idempotency | `execution/oms.py` |
| 3 | Position Ledger | `execution/ledger.py` |
| 4 | Risk Engine (enhanced) | `risk/engine.py` (CVaR + vol targeting) |
| 4 | Reconciliation | `execution/reconcile.py` |

### Phase 2: Intelligence (Week 5-8) — "สมองคิด"

| Week | Task | Deliverable |
|------|------|-------------|
| 5 | Crawl4AI economic calendar | `market_data/crawl4ai_calendar.py` |
| 5 | Crawl4AI news scraper | `market_data/crawl4ai_news.py` |
| 6 | News sentiment (DeepSeek-R1 batch) | `ml/sentiment_analyzer.py` |
| 6 | DXY correlation filter | `gold_bot/strategies/dxy_filter.py` |
| 7 | Triple-barrier labeling | `ml/triple_barrier.py` |
| 7 | Ensemble stacking | `ml/ensemble.py` |
| 8 | Regime detection (HMM) | `ml/regime_detector.py` |
| 8 | TradingView webhook | `api/webhook_receiver.py` |

### Phase 3: Resilience (Week 9-12) — "ไม่พัง"

| Week | Task | Deliverable |
|------|------|-------------|
| 9 | Kill switch (Telegram) | `risk/kill_switch.py` (enhanced) |
| 9 | Circuit breaker | `risk/circuit_breaker.py` (enhanced) |
| 10 | Heartbeat monitor | `monitoring/heartbeat.py` |
| 10 | Crash recovery | `execution/recovery.py` |
| 11 | Telemetry (Grafana) | `monitoring/dashboard.py` |
| 11 | Telegram alerts | `monitoring/telegram.py` (enhanced) |
| 12 | NATS migration | `core/event_bus_nats.py` |
| 12 | End-to-end testing | `tests/test_e2e_live.py` |

### Phase 4: Production (Week 13-16) — "เงินจริง"

| Week | Task | Deliverable |
|------|------|-------------|
| 13 | Paper trading (60 days) | Shadow mode on Pepperstone |
| 13 | Performance benchmarks | `reports/benchmark_live.md` |
| 14 | Security audit | `reports/security_audit.md` |
| 14 | VPS deployment | `infra/deploy.sh` |
| 15 | Micro-live ($100) | First real money trades |
| 15 | Daily review process | `Meta/execution_plan.md` |
| 16 | Scale to full | Based on micro-live results |

---

## PART 5: DEPENDENCY MAP

```
Phase 1 Dependencies:
MT5 Pipeline ──→ Quality Gate ──→ Event Bus ──→ Alpha Engine
                                                       │
Position Ledger ←── OMS ←── Risk Engine ←──────────────┘

Phase 2 Dependencies:
Crawl4AI ──→ News Pipeline ──→ Sentiment ──→ Alpha Engine
TradingView ──→ Webhook ──→ Signal Queue ──→ Risk Engine

Phase 3 Dependencies:
Kill Switch ──→ Telegram ──→ OMS (cancel all)
Heartbeat ──→ Recovery ──→ State Persistence
```

---

## PART 6: COST ESTIMATE

| Component | Monthly Cost | Notes |
|-----------|-------------|-------|
| VPS (Vultr) | $12-24 | 2-4 vCPU, 4-8GB RAM |
| Pepperstone | $0 | No commission on XAUUSD |
| DuckDB | $0 | In-process, no server |
| Crawl4AI | $0 | Open source |
| DeepSeek-R1 API | $5-20 | Batch analysis only |
| Telegram Bot | $0 | Free |
| Grafana | $0 | Self-hosted |
| **Total** | **$17-44/month** | |

---

## PART 7: RISK MATRIX

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Network failure mid-order | Medium | High | Idempotent OMS + crash recovery |
| Broker API down | Low | High | Circuit breaker + halt trading |
| Data feed stale | Medium | Medium | Quality gate + staleness check |
| Model drift | Medium | Medium | Drift detector + retrain trigger |
| Black swan event | Very Low | Very High | Kill switch + hard stop loss |
| Bug in strategy code | Medium | High | TDD + shadow mode + paper trading |
| Overfitting | High | Medium | CPCV + deflated Sharpe + PBO |

---

## FILES GENERATED THIS SESSION

| File | Lines | Content |
|------|-------|---------|
| `TOOL_ANALYSIS_CRAWL4AI_NAUTILUS.md` | 682 | Crawl4AI + NautilusTrader deep dive |
| `TOOL_ANALYSIS_OPENBB_TRADINGVIEW.md` | 608 | OpenBB + TradingView deep dive |
| `TOOL_ANALYSIS_DUCKDB_DEEPSEEK.md` | ~400 | DuckDB + DeepSeek-R1 deep dive |
| `TOOL_ANALYSIS_FINCEPT_DEEPFOREX.md` | ~300 | FinceptTerminal + DeepForex deep dive |
| `DISTRIBUTED_STATE_MACHINE_RESEARCH.md` | 1,508 | State machine architecture research |
| `NATS_MESSAGING_RESEARCH.md` | 792 | NATS + messaging alternatives |
| `MEGA_PLAN.md` | This file | Master architecture plan |

---

## NEXT ACTION

**Start Phase 1, Week 1:** Build MT5 → DuckDB tick pipeline with quality gate integration.

This is the foundation everything else depends on. Without clean, validated data flowing into DuckDB, nothing else works.

Files to create:
1. `data/mt5_tick_ingester.py` — Async MT5 tick reader → DuckDB
2. `data/quality_gate.py` — Enhanced with OHLC consistency + session-aware gaps
3. `core/event_bus.py` — asyncio.Queue with subject-based routing
4. `data/bar_aggregator.py` — Tick → OHLCV bar aggregation

Total effort: ~5 days for Phase 1 foundation.
