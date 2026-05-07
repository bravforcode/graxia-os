-- ═══════════════════════════════════════════════════════════════════════════════
-- Graxia OS — ClickHouse Analytics Schema
-- High-Performance Analytics for Trading & Revenue
-- ═══════════════════════════════════════════════════════════════════════════════

-- Create database
CREATE DATABASE IF NOT EXISTS graxia_analytics;

-- ═══════════════════════════════════════════════════════════════════════════════
-- TIER 4: REAL-TIME ANALYTICS (Features 46-60)
-- ═══════════════════════════════════════════════════════════════════════════════

-- ── Events Table (Raw Data) ──
CREATE TABLE IF NOT EXISTS graxia_analytics.events (
    event_id UUID,
    user_id String,
    session_id String,
    event_type LowCardinality(String),
    event_category LowCardinality(String),
    timestamp DateTime64(3),
    date Date DEFAULT toDate(timestamp),
    properties String, -- JSON
    platform LowCardinality(String),
    country LowCardinality(String),
    device_type LowCardinality(String)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (date, event_type, timestamp)
TTL date + INTERVAL 1 YEAR
SETTINGS index_granularity = 8192;

-- ── Trades Analytics ──
CREATE TABLE IF NOT EXISTS graxia_analytics.trades (
    trade_id UUID,
    order_id UUID,
    user_id String,
    market_id String,
    symbol String,
    side LowCardinality(String), -- BUY, SELL
    order_type LowCardinality(String), -- MARKET, LIMIT, STOP
    amount Float64,
    price Float64,
    total Float64,
    fee Float64,
    pnl Float64,
    timestamp DateTime64(3),
    date Date DEFAULT toDate(timestamp),
    trading_mode LowCardinality(String), -- PAPER, LIVE
    strategy_id String,
    execution_time_ms UInt32
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (date, symbol, timestamp)
TTL date + INTERVAL 2 YEAR
SETTINGS index_granularity = 8192;

-- ── Orders Analytics ──
CREATE TABLE IF NOT EXISTS graxia_analytics.orders (
    order_id UUID,
    user_id String,
    product_id String,
    order_type LowCardinality(String),
    status LowCardinality(String), -- PENDING, COMPLETED, CANCELLED
    amount Float64,
    currency LowCardinality(String),
    revenue Float64,
    cost Float64,
    profit Float64,
    payment_method LowCardinality(String),
    source LowCardinality(String), -- organic, ads, referral
    campaign_id String,
    timestamp DateTime64(3),
    date Date DEFAULT toDate(timestamp)
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (date, status, timestamp)
TTL date + INTERVAL 2 YEAR
SETTINGS index_granularity = 8192;

-- ── Revenue by Hour (Materialized View Target) ──
CREATE TABLE IF NOT EXISTS graxia_analytics.revenue_hourly (
    hour DateTime,
    source LowCardinality(String),
    currency LowCardinality(String),
    total_revenue AggregateFunction(sum, Float64),
    total_orders AggregateFunction(count, UInt64),
    unique_customers AggregateFunction(uniq, String),
    avg_order_value AggregateFunction(avg, Float64)
) ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(hour)
ORDER BY (hour, source, currency);

-- Materialized View: Revenue Aggregation
CREATE MATERIALIZED VIEW IF NOT EXISTS graxia_analytics.revenue_hourly_mv
TO graxia_analytics.revenue_hourly
AS SELECT
    toStartOfHour(timestamp) AS hour,
    source,
    currency,
    sumState(revenue) AS total_revenue,
    countState() AS total_orders,
    uniqState(user_id) AS unique_customers,
    avgState(revenue) AS avg_order_value
FROM graxia_analytics.orders
GROUP BY hour, source, currency;

-- ── Trading Performance by Hour ──
CREATE TABLE IF NOT EXISTS graxia_analytics.trading_performance_hourly (
    hour DateTime,
    symbol String,
    trading_mode LowCardinality(String),
    strategy_id String,
    total_pnl AggregateFunction(sum, Float64),
    total_trades AggregateFunction(count, UInt64),
    winning_trades AggregateFunction(sumIf, UInt64, Float64),
    losing_trades AggregateFunction(sumIf, UInt64, Float64),
    avg_trade_size AggregateFunction(avg, Float64),
    max_drawdown Float64,
    volatility Float64
) ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(hour)
ORDER BY (hour, symbol, trading_mode, strategy_id);

-- Materialized View: Trading Performance
CREATE MATERIALIZED VIEW IF NOT EXISTS graxia_analytics.trading_performance_hourly_mv
TO graxia_analytics.trading_performance_hourly
AS SELECT
    toStartOfHour(timestamp) AS hour,
    symbol,
    trading_mode,
    strategy_id,
    sumState(pnl) AS total_pnl,
    countState() AS total_trades,
    sumIfState(1, pnl > 0) AS winning_trades,
    sumIfState(1, pnl < 0) AS losing_trades,
    avgState(amount * price) AS avg_trade_size,
    0 AS max_drawdown,
    0 AS volatility
FROM graxia_analytics.trades
GROUP BY hour, symbol, trading_mode, strategy_id;

-- ═══════════════════════════════════════════════════════════════════════════════
-- ANALYTICS FUNCTIONS & VIEWS
-- ═══════════════════════════════════════════════════════════════════════════════

-- ── Daily Active Users (DAU) View ──
CREATE VIEW IF NOT EXISTS graxia_analytics.dau AS
SELECT
    date,
    uniqExact(user_id) AS active_users,
    uniqExactIf(user_id, event_type = 'trade') AS active_traders,
    uniqExactIf(user_id, event_type = 'purchase') AS active_buyers
FROM graxia_analytics.events
GROUP BY date
ORDER BY date DESC;

-- ── Monthly Active Users (MAU) View ──
CREATE VIEW IF NOT EXISTS graxia_analytics.mau AS
SELECT
    toStartOfMonth(date) AS month,
    uniqExact(user_id) AS active_users,
    uniqExactIf(user_id, event_type = 'trade') AS active_traders,
    uniqExactIf(user_id, event_type = 'purchase') AS active_buyers
FROM graxia_analytics.events
GROUP BY month
ORDER BY month DESC;

-- ── Retention Cohort View ──
CREATE VIEW IF NOT EXISTS graxia_analytics.retention AS
SELECT
    signup_date,
    activity_date,
    dateDiff('day', signup_date, activity_date) AS days_since_signup,
    uniqExact(user_id) AS returning_users
FROM (
    SELECT
        user_id,
        min(toDate(timestamp)) OVER (PARTITION BY user_id) AS signup_date,
        toDate(timestamp) AS activity_date
    FROM graxia_analytics.events
)
GROUP BY signup_date, activity_date, days_since_signup
ORDER BY signup_date DESC, days_since_signup;

-- ── Funnel Analysis View ──
CREATE VIEW IF NOT EXISTS graxia_analytics.funnel_daily AS
SELECT
    date,
    countIf(event_type = 'page_view') AS page_views,
    countIf(event_type = 'product_view') AS product_views,
    countIf(event_type = 'add_to_cart') AS add_to_carts,
    countIf(event_type = 'checkout_start') AS checkout_starts,
    countIf(event_type = 'purchase') AS purchases,
    round(purchases / page_views * 100, 2) AS conversion_rate
FROM graxia_analytics.events
GROUP BY date
ORDER BY date DESC;

-- ═══════════════════════════════════════════════════════════════════════════════
-- OPTIMIZATIONS
-- ═══════════════════════════════════════════════════════════════════════════════

-- Enable query cache
SET allow_experimental_query_cache = true;

-- Set max memory usage per query
SET max_memory_usage = 2000000000; -- 2GB

-- Enable parallel replicas for distributed queries
SET allow_experimental_parallel_reading_from_replicas = 1;
