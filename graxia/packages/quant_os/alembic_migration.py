"""
Alembic Migration for Quant OS

Create this file at: backend/alembic/versions/XXX_quant_os_initial.py

Revision ID: quant_os_initial
Revises: <previous_revision>
Create Date: 2024-01-01 00:00:00.000000
"""

# Revision identifiers, used by Alembic
revision = 'quant_os_initial'
down_revision = None  # Set to your previous migration
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():
    # Enable UUID extension
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    
    # Orders table
    op.create_table(
        'quant_orders',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('client_order_id', sa.String(64), nullable=False, unique=True),
        sa.Column('idempotency_key', sa.String(128), nullable=False, unique=True),
        sa.Column('broker_order_id', sa.String(128), nullable=True),
        sa.Column('symbol', sa.String(16), nullable=False),
        sa.Column('side', sa.Enum('BUY', 'SELL', name='orderside'), nullable=False),
        sa.Column('order_type', sa.Enum('MARKET', 'LIMIT', 'STOP', 'STOP_LIMIT', name='ordertype'), nullable=False),
        sa.Column('quantity', sa.Numeric(18, 8), nullable=False),
        sa.Column('price', sa.Numeric(18, 8), nullable=True),
        sa.Column('stop_price', sa.Numeric(18, 8), nullable=True),
        sa.Column('time_in_force', sa.Enum('DAY', 'GTC', 'IOC', 'FOK', name='timeinforce'), nullable=False, server_default='DAY'),
        sa.Column('strategy_id', sa.String(64), nullable=False),
        sa.Column('signal_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quant_signals.id'), nullable=True),
        sa.Column('risk_check_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('compliance_check_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('approved_by', sa.String(64), nullable=True),
        sa.Column('trading_mode', sa.String(32), nullable=False),
        sa.Column('status', sa.Enum('CREATED', 'VALIDATED', 'RISK_APPROVED', 'COMPLIANCE_APPROVED', 'PENDING_HUMAN', 'SENT_TO_BROKER', 'ACKNOWLEDGED', 'PARTIAL_FILL', 'FILLED', 'REJECTED', 'CANCEL_REQUESTED', 'CANCELLED', 'EXPIRED', 'ERROR', name='orderstatus'), nullable=False, server_default='CREATED'),
        sa.Column('fill_quantity', sa.Numeric(18, 8), nullable=False, server_default='0'),
        sa.Column('avg_fill_price', sa.Numeric(18, 8), nullable=True),
        sa.Column('fee', sa.Numeric(18, 8), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('filled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('raw_broker_response', postgresql.JSONB(), nullable=True),
    )
    
    # Order indexes
    op.create_index('ix_orders_symbol', 'quant_orders', ['symbol'])
    op.create_index('ix_orders_strategy', 'quant_orders', ['strategy_id'])
    op.create_index('ix_orders_status', 'quant_orders', ['status'])
    op.create_index('ix_orders_created_at', 'quant_orders', [sa.text('created_at DESC')])
    op.create_index('ix_orders_trading_mode', 'quant_orders', ['trading_mode'])
    
    # Order state history table
    op.create_table(
        'quant_order_state_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quant_orders.id'), nullable=False),
        sa.Column('from_status', sa.Enum('CREATED', 'VALIDATED', 'RISK_APPROVED', 'COMPLIANCE_APPROVED', 'PENDING_HUMAN', 'SENT_TO_BROKER', 'ACKNOWLEDGED', 'PARTIAL_FILL', 'FILLED', 'REJECTED', 'CANCEL_REQUESTED', 'CANCELLED', 'EXPIRED', 'ERROR', name='orderstatus'), nullable=True),
        sa.Column('to_status', sa.Enum('CREATED', 'VALIDATED', 'RISK_APPROVED', 'COMPLIANCE_APPROVED', 'PENDING_HUMAN', 'SENT_TO_BROKER', 'ACKNOWLEDGED', 'PARTIAL_FILL', 'FILLED', 'REJECTED', 'CANCEL_REQUESTED', 'CANCELLED', 'EXPIRED', 'ERROR', name='orderstatus'), nullable=False),
        sa.Column('actor', sa.String(64), nullable=False, server_default='system'),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('context', postgresql.JSONB(), nullable=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_state_history_order_id', 'quant_order_state_history', ['order_id'])
    op.create_index('ix_state_history_occurred_at', 'quant_order_state_history', [sa.text('occurred_at DESC')])
    
    # Fills table
    op.create_table(
        'quant_fills',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quant_orders.id'), nullable=False),
        sa.Column('broker_fill_id', sa.String(128), nullable=True),
        sa.Column('symbol', sa.String(16), nullable=False),
        sa.Column('side', sa.Enum('BUY', 'SELL', name='orderside'), nullable=False),
        sa.Column('strategy_id', sa.String(64), nullable=False),
        sa.Column('quantity', sa.Numeric(18, 8), nullable=False),
        sa.Column('price', sa.Numeric(18, 8), nullable=False),
        sa.Column('fee', sa.Numeric(18, 8), nullable=False, server_default='0'),
        sa.Column('fee_currency', sa.String(4), nullable=False, server_default='USD'),
        sa.Column('realized_pnl', sa.Numeric(18, 8), nullable=True),
        sa.Column('regime', sa.Enum('TREND_STRONG_UP', 'TREND_STRONG_DOWN', 'TREND_WEAK', 'RANGE_BOUND', 'HIGH_VOLATILITY', 'LOW_VOLATILITY', 'CRISIS', 'NEWS_DRIVEN', 'ILLIQUID', 'ABNORMAL_SPREAD', 'UNCERTAIN', name='regimetype'), nullable=True),
        sa.Column('filled_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('trading_mode', sa.String(32), nullable=False),
    )
    op.create_index('ix_fills_symbol', 'quant_fills', ['symbol'])
    op.create_index('ix_fills_strategy', 'quant_fills', ['strategy_id'])
    op.create_index('ix_fills_filled_at', 'quant_fills', [sa.text('filled_at DESC')])
    
    # Positions table
    op.create_table(
        'quant_positions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('symbol', sa.String(16), nullable=False),
        sa.Column('strategy_id', sa.String(64), nullable=False),
        sa.Column('position_type', sa.Enum('LONG', 'SHORT', name='positiontype'), nullable=False),
        sa.Column('quantity', sa.Numeric(18, 8), nullable=False),
        sa.Column('avg_entry_price', sa.Numeric(18, 8), nullable=False),
        sa.Column('current_price', sa.Numeric(18, 8), nullable=True),
        sa.Column('unrealized_pnl', sa.Numeric(18, 8), nullable=True),
        sa.Column('realized_pnl', sa.Numeric(18, 8), nullable=False, server_default='0'),
        sa.Column('stop_loss', sa.Numeric(18, 8), nullable=True),
        sa.Column('take_profit', sa.Numeric(18, 8), nullable=True),
        sa.Column('opened_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_open', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('close_reason', sa.Enum('TAKE_PROFIT', 'STOP_LOSS', 'TRAILING_STOP', 'MANUAL', 'CIRCUIT_BREAKER', 'KILL_SWITCH', 'EXPIRED', 'REVERSE_SIGNAL', name='closereason'), nullable=True),
        sa.Column('trading_mode', sa.String(32), nullable=False),
        sa.Column('entry_order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quant_orders.id'), nullable=False),
        sa.Column('exit_order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quant_orders.id'), nullable=True),
    )
    op.create_index('ix_positions_symbol', 'quant_positions', ['symbol'])
    op.create_index('ix_positions_strategy', 'quant_positions', ['strategy_id'])
    op.create_index('ix_positions_open', 'quant_positions', ['is_open'])
    op.create_index('ix_positions_symbol_open', 'quant_positions', ['symbol', 'is_open'])
    
    # Signals table
    op.create_table(
        'quant_signals',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('strategy_id', sa.String(64), nullable=False),
        sa.Column('symbol', sa.String(16), nullable=False),
        sa.Column('signal_type', sa.Enum('BUY', 'SELL', 'NO_TRADE', 'EXIT', 'REDUCE', 'HOLD', name='signaltype'), nullable=False),
        sa.Column('confidence', sa.Numeric(5, 4), nullable=True),
        sa.Column('strength', sa.String(16), nullable=True),
        sa.Column('regime', sa.Enum('TREND_STRONG_UP', 'TREND_STRONG_DOWN', 'TREND_WEAK', 'RANGE_BOUND', 'HIGH_VOLATILITY', 'LOW_VOLATILITY', 'CRISIS', 'NEWS_DRIVEN', 'ILLIQUID', 'ABNORMAL_SPREAD', 'UNCERTAIN', name='regimetype'), nullable=True),
        sa.Column('indicator_values', postgresql.JSONB(), nullable=True),
        sa.Column('raw_payload', postgresql.JSONB(), nullable=True),
        sa.Column('source', sa.String(32), nullable=False, server_default='tradingview'),
        sa.Column('processed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('decision', sa.Enum('BUY', 'SELL', 'REDUCE', 'EXIT', 'HOLD', 'NO_TRADE', 'WAIT', 'ABSTAIN_INSUFFICIENT_EDGE', 'ABSTAIN_DATA_QUALITY', 'ABSTAIN_RISK_LIMIT', 'ABSTAIN_MARKET_CONDITION', name='decisiontype'), nullable=True),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quant_orders.id'), nullable=True),
        sa.Column('rejection_reason', sa.String(256), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_signals_strategy', 'quant_signals', ['strategy_id'])
    op.create_index('ix_signals_symbol', 'quant_signals', ['symbol'])
    op.create_index('ix_signals_received_at', 'quant_signals', [sa.text('received_at DESC')])
    op.create_index('ix_signals_processed', 'quant_signals', ['processed'])
    
    # Risk checks table
    op.create_table(
        'quant_risk_checks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('signal_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quant_signals.id'), nullable=True),
        sa.Column('result', sa.Enum('PASS', 'FAIL_POSITION_SIZE', 'FAIL_EXPOSURE', 'FAIL_DAILY_LOSS', 'FAIL_DRAWDOWN', 'FAIL_CORRELATION', 'FAIL_LIQUIDITY', 'FAIL_DATA_STALE', 'FAIL_COOLDOWN', 'FAIL_MAX_POSITIONS', name='riskcheckresult'), nullable=False),
        sa.Column('checks', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('portfolio_exposure_pct', sa.Numeric(8, 4), nullable=True),
        sa.Column('daily_loss_pct', sa.Numeric(8, 4), nullable=True),
        sa.Column('current_drawdown_pct', sa.Numeric(8, 4), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_risk_checks_result', 'quant_risk_checks', ['result'])
    op.create_index('ix_risk_checks_created_at', 'quant_risk_checks', [sa.text('created_at DESC')])
    
    # Backtests table
    op.create_table(
        'quant_backtests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('symbol', sa.String(16), nullable=False),
        sa.Column('timeframe', sa.String(8), nullable=False),
        sa.Column('strategy_id', sa.String(64), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('initial_capital', sa.Numeric(18, 2), nullable=False, server_default='10000'),
        sa.Column('final_capital', sa.Numeric(18, 2), nullable=True),
        sa.Column('total_trades', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('winning_trades', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('losing_trades', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('win_rate', sa.Numeric(5, 4), nullable=True),
        sa.Column('profit_factor', sa.Numeric(8, 4), nullable=True),
        sa.Column('max_drawdown', sa.Numeric(8, 4), nullable=True),
        sa.Column('max_drawdown_pct', sa.Numeric(8, 4), nullable=True),
        sa.Column('sharpe_ratio', sa.Numeric(8, 4), nullable=True),
        sa.Column('sortino_ratio', sa.Numeric(8, 4), nullable=True),
        sa.Column('calmar_ratio', sa.Numeric(8, 4), nullable=True),
        sa.Column('expectancy', sa.Numeric(18, 8), nullable=True),
        sa.Column('avg_win', sa.Numeric(18, 8), nullable=True),
        sa.Column('avg_loss', sa.Numeric(18, 8), nullable=True),
        sa.Column('avg_rr', sa.Numeric(6, 2), nullable=True),
        sa.Column('total_pnl', sa.Numeric(18, 8), nullable=True),
        sa.Column('cagr', sa.Numeric(8, 4), nullable=True),
        sa.Column('total_fees', sa.Numeric(18, 8), nullable=True),
        sa.Column('total_slippage', sa.Numeric(18, 8), nullable=True),
        sa.Column('slippage_used', sa.Numeric(8, 4), nullable=False, server_default='0.5'),
        sa.Column('commission_used', sa.Numeric(8, 4), nullable=False, server_default='3.5'),
        sa.Column('params', postgresql.JSONB(), nullable=True),
        sa.Column('equity_curve', postgresql.JSONB(), nullable=True),
        sa.Column('monthly_returns', postgresql.JSONB(), nullable=True),
        sa.Column('is_walk_forward', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('oos_start_date', sa.Date(), nullable=True),
        sa.Column('overfitting_tests', postgresql.JSONB(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_backtests_strategy', 'quant_backtests', ['strategy_id'])
    op.create_index('ix_backtests_symbol', 'quant_backtests', ['symbol'])
    op.create_index('ix_backtests_created_at', 'quant_backtests', [sa.text('created_at DESC')])
    
    # Portfolio snapshots table
    op.create_table(
        'quant_portfolio_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('snapshot_date', sa.Date(), nullable=False, unique=True),
        sa.Column('balance', sa.Numeric(18, 2), nullable=False, server_default='0'),
        sa.Column('equity', sa.Numeric(18, 2), nullable=False, server_default='0'),
        sa.Column('floating_pnl', sa.Numeric(18, 2), nullable=False, server_default='0'),
        sa.Column('daily_pnl', sa.Numeric(18, 2), nullable=False, server_default='0'),
        sa.Column('daily_pnl_pct', sa.Numeric(8, 4), nullable=False, server_default='0'),
        sa.Column('open_positions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('daily_trades', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('win_trades_day', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('drawdown_pct', sa.Numeric(8, 4), nullable=False, server_default='0'),
        sa.Column('peak_equity', sa.Numeric(18, 2), nullable=False, server_default='0'),
        sa.Column('portfolio_exposure_pct', sa.Numeric(8, 4), nullable=False, server_default='0'),
        sa.Column('sharpe_7d', sa.Numeric(8, 4), nullable=True),
        sa.Column('sharpe_30d', sa.Numeric(8, 4), nullable=True),
        sa.Column('win_rate_20', sa.Numeric(5, 4), nullable=True),
        sa.Column('expectancy_20', sa.Numeric(18, 8), nullable=True),
        sa.Column('trading_mode', sa.String(32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    
    # Kill switch events table
    op.create_table(
        'quant_kill_switch_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('switch_type', sa.Enum('MANUAL', 'DAILY_LOSS', 'DRAWDOWN', 'WEEKLY_LOSS', 'DATA_QUALITY', 'BROKER_EXECUTION', 'OPERATIONAL', 'POSITION_MISMATCH', 'DUPLICATE_ORDER', 'STALE_DATA', 'HEARTBEAT_FAIL', name='killswitchtype'), nullable=False),
        sa.Column('action', sa.String(16), nullable=False),
        sa.Column('triggered_by', sa.String(64), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('context', postgresql.JSONB(), nullable=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('reset_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reset_by', sa.String(64), nullable=True),
    )
    op.create_index('ix_kill_switch_occurred_at', 'quant_kill_switch_events', [sa.text('occurred_at DESC')])
    
    # Risk events table
    op.create_table(
        'quant_risk_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('event_type', sa.String(32), nullable=False),
        sa.Column('severity', sa.Enum('P0', 'P1', 'P2', 'P3', name='incidentseverity'), nullable=False),
        sa.Column('symbol', sa.String(16), nullable=True),
        sa.Column('strategy_id', sa.String(64), nullable=True),
        sa.Column('value', sa.Numeric(18, 8), nullable=True),
        sa.Column('threshold', sa.Numeric(18, 8), nullable=True),
        sa.Column('action_taken', sa.Text(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_risk_events_created_at', 'quant_risk_events', [sa.text('created_at DESC')])
    op.create_index('ix_risk_events_severity', 'quant_risk_events', ['severity'])
    
    # Strategy registry table
    op.create_table(
        'quant_strategy_registry',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('strategy_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('version', sa.String(16), nullable=False, server_default='1.0.0'),
        sa.Column('group_type', sa.String(32), nullable=False),
        sa.Column('status', sa.Enum('HYPOTHESIS', 'BACKTESTED', 'PAPER', 'LIVE_MICRO', 'LIVE', 'DEPRECATED', name='strategystatus'), nullable=False, server_default='HYPOTHESIS'),
        sa.Column('evidence_score', sa.Numeric(5, 2), nullable=True),
        sa.Column('paper_days_completed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('paper_trades_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('params', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('symbols', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('timeframes', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('is_frozen', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('frozen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('strategy_id', 'version', name='uq_strategy_version'),
    )
    op.create_index('ix_strategy_status', 'quant_strategy_registry', ['status'])
    
    # ML models table
    op.create_table(
        'quant_ml_models',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('version', sa.String(16), nullable=False),
        sa.Column('model_type', sa.String(32), nullable=False),
        sa.Column('strategy_id', sa.String(64), nullable=True),
        sa.Column('symbols', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('accuracy', sa.Numeric(5, 4), nullable=True),
        sa.Column('precision', sa.Numeric(5, 4), nullable=True),
        sa.Column('recall', sa.Numeric(5, 4), nullable=True),
        sa.Column('f1_score', sa.Numeric(5, 4), nullable=True),
        sa.Column('oos_accuracy', sa.Numeric(5, 4), nullable=True),
        sa.Column('feature_list', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('file_path', sa.String(512), nullable=True),
        sa.Column('training_data_hash', sa.String(64), nullable=True),
        sa.Column('status', sa.Enum('RESEARCH', 'PAPER', 'LIVE_MICRO', 'LIVE', 'DEPRECATED', name='modelstatus'), nullable=False, server_default='RESEARCH'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('trained_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('train_start', sa.Date(), nullable=True),
        sa.Column('train_end', sa.Date(), nullable=True),
        sa.Column('last_drift_check', sa.DateTime(timezone=True), nullable=True),
        sa.Column('drift_score', sa.Numeric(5, 4), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_ml_models_status', 'quant_ml_models', ['status'])
    op.create_index('ix_ml_models_strategy', 'quant_ml_models', ['strategy_id'])
    
    # Audit log table
    op.create_table(
        'quant_audit_log',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('event_type', sa.String(64), nullable=False),
        sa.Column('actor', sa.String(64), nullable=False),
        sa.Column('resource', sa.String(128), nullable=True),
        sa.Column('action', sa.String(64), nullable=True),
        sa.Column('result', sa.String(16), nullable=True),
        sa.Column('context', postgresql.JSONB(), nullable=True),
        sa.Column('prev_hash', sa.String(64), nullable=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_audit_event_type', 'quant_audit_log', ['event_type'])
    op.create_index('ix_audit_actor', 'quant_audit_log', ['actor'])
    op.create_index('ix_audit_occurred_at', 'quant_audit_log', [sa.text('occurred_at DESC')])
    
    # Data quality runs table
    op.create_table(
        'quant_data_quality_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('source', sa.String(32), nullable=False),
        sa.Column('symbol', sa.String(16), nullable=True),
        sa.Column('check_name', sa.Enum('MISSING_TIMESTAMP', 'DUPLICATE_TIMESTAMP', 'OUTLIER_PRICE', 'NEGATIVE_PRICE', 'ZERO_VOLUME', 'STALE_QUOTE', 'GAP_DETECTED', 'SESSION_BOUNDARY', name='dataqualitycheck'), nullable=False),
        sa.Column('passed', sa.Boolean(), nullable=False),
        sa.Column('details', postgresql.JSONB(), nullable=True),
        sa.Column('ran_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_dq_passed', 'quant_data_quality_runs', ['passed', sa.text('ran_at DESC')])
    op.create_index('ix_dq_symbol', 'quant_data_quality_runs', ['symbol'])
    
    # Paper daily reports table
    op.create_table(
        'quant_paper_daily_reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('report_date', sa.Date(), nullable=False, unique=True),
        sa.Column('total_trades', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('open_positions_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('daily_pnl', sa.Numeric(18, 8), nullable=False, server_default='0'),
        sa.Column('cumulative_pnl', sa.Numeric(18, 8), nullable=False, server_default='0'),
        sa.Column('current_drawdown_pct', sa.Numeric(8, 4), nullable=False, server_default='0'),
        sa.Column('win_rate_20', sa.Numeric(5, 4), nullable=True),
        sa.Column('expectancy_20', sa.Numeric(18, 8), nullable=True),
        sa.Column('avg_slippage_pips', sa.Numeric(8, 4), nullable=True),
        sa.Column('fill_rate_pct', sa.Numeric(5, 2), nullable=True),
        sa.Column('incidents_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('gate_status', sa.String(16), nullable=False, server_default='PASS'),
        sa.Column('details', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    
    # Reconciliation logs table
    op.create_table(
        'quant_reconciliation_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('run_date', sa.Date(), nullable=False),
        sa.Column('broker_id', sa.String(32), nullable=False),
        sa.Column('recon_type', sa.String(32), nullable=False),
        sa.Column('status', sa.Enum('CLEAN', 'MISMATCH', 'ERROR', name='reconciliationstatus'), nullable=False),
        sa.Column('severity', sa.String(8), nullable=True),
        sa.Column('discrepancies', postgresql.JSONB(), nullable=True),
        sa.Column('internal_snap', postgresql.JSONB(), nullable=True),
        sa.Column('broker_snap', postgresql.JSONB(), nullable=True),
        sa.Column('actions_taken', postgresql.JSONB(), nullable=True),
        sa.Column('ran_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_recon_run_date', 'quant_reconciliation_logs', [sa.text('run_date DESC')])
    op.create_index('ix_recon_status', 'quant_reconciliation_logs', ['status'])


def downgrade():
    # Drop in reverse order
    op.drop_table('quant_reconciliation_logs')
    op.drop_table('quant_paper_daily_reports')
    op.drop_table('quant_data_quality_runs')
    op.drop_table('quant_audit_log')
    op.drop_table('quant_ml_models')
    op.drop_table('quant_strategy_registry')
    op.drop_table('quant_risk_events')
    op.drop_table('quant_kill_switch_events')
    op.drop_table('quant_portfolio_snapshots')
    op.drop_table('quant_backtests')
    op.drop_table('quant_risk_checks')
    op.drop_table('quant_signals')
    op.drop_table('quant_positions')
    op.drop_table('quant_fills')
    op.drop_table('quant_order_state_history')
    op.drop_table('quant_orders')
    
    # Drop enum types
    op.execute('DROP TYPE IF EXISTS reconciliationstatus')
    op.execute('DROP TYPE IF EXISTS dataqualitycheck')
    op.execute('DROP TYPE IF EXISTS modelstatus')
    op.execute('DROP TYPE IF EXISTS strategystatus')
    op.execute('DROP TYPE IF EXISTS incidentseverity')
    op.execute('DROP TYPE IF EXISTS killswitchtype')
    op.execute('DROP TYPE IF EXISTS closereason')
    op.execute('DROP TYPE IF EXISTS positiontype')
    op.execute('DROP TYPE IF EXISTS decisiontype')
    op.execute('DROP TYPE IF EXISTS signaltype')
    op.execute('DROP TYPE IF EXISTS regimetype')
    op.execute('DROP TYPE IF EXISTS riskcheckresult')
    op.execute('DROP TYPE IF EXISTS orderstatus')
    op.execute('DROP TYPE IF EXISTS timeinforce')
    op.execute('DROP TYPE IF EXISTS ordertype')
    op.execute('DROP TYPE IF EXISTS orderside')
