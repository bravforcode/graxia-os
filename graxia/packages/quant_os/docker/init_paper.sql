CREATE TABLE IF NOT EXISTS paper_trades (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    direction VARCHAR(16) NOT NULL,
    entry_price DOUBLE PRECISION NOT NULL,
    exit_price DOUBLE PRECISION,
    sl_distance DOUBLE PRECISION,
    tp_distance DOUBLE PRECISION,
    lot_size DOUBLE PRECISION NOT NULL,
    pnl DOUBLE PRECISION,
    commission DOUBLE PRECISION DEFAULT 0,
    spread_cost DOUBLE PRECISION DEFAULT 0,
    status VARCHAR(16) DEFAULT 'open',
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    signal_confidence DOUBLE PRECISION,
    signal_json TEXT
);

CREATE TABLE IF NOT EXISTS paper_positions (
    id SERIAL PRIMARY KEY,
    trade_id INTEGER NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    direction VARCHAR(16) NOT NULL,
    entry_price DOUBLE PRECISION NOT NULL,
    current_price DOUBLE PRECISION,
    sl_price DOUBLE PRECISION,
    tp_price DOUBLE PRECISION,
    lot_size DOUBLE PRECISION NOT NULL,
    floating_pnl DOUBLE PRECISION DEFAULT 0,
    opened_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS paper_portfolio (
    id SERIAL PRIMARY KEY,
    balance DOUBLE PRECISION NOT NULL,
    equity DOUBLE PRECISION NOT NULL,
    total_pnl DOUBLE PRECISION DEFAULT 0,
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
