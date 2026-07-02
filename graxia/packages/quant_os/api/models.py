"""
SQLAlchemy ORM models for Quant OS.

Kept self-contained (local declarative Base) so Alembic and the API can import
models without the external graxia.database package.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship

from ..core.enums import (
    CloseReason,
    DataQualityCheck,
    DecisionType,
    IncidentSeverity,
    KillSwitchType,
    ModelStatus,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionType,
    ReconciliationStatus,
    RegimeType,
    RiskCheckResult,
    SignalType,
    StrategyStatus,
    TimeInForce,
)

Base = declarative_base()


class Order(Base):
    """Order entity."""

    __tablename__ = "quant_orders"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_orders_idempotency"),
        Index("ix_orders_symbol", "symbol"),
        Index("ix_orders_strategy", "strategy_id"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_created_at", "created_at"),
        Index("ix_orders_trading_mode", "trading_mode"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    client_order_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(128))

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[OrderSide] = mapped_column(SAEnum(OrderSide), nullable=False)
    order_type: Mapped[OrderType] = mapped_column(SAEnum(OrderType), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    time_in_force: Mapped[TimeInForce] = mapped_column(SAEnum(TimeInForce), default=TimeInForce.DAY)

    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False)
    signal_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("quant_signals.id"))
    # Kept as plain UUID to avoid a circular FK with quant_risk_checks.
    risk_check_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True))
    compliance_check_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_by: Mapped[str | None] = mapped_column(String(64))
    trading_mode: Mapped[str] = mapped_column(String(32), nullable=False)

    status: Mapped[OrderStatus] = mapped_column(SAEnum(OrderStatus), default=OrderStatus.CREATED)
    fill_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"))
    avg_fill_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    fee: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    rejection_reason: Mapped[str | None] = mapped_column(Text)
    raw_broker_response: Mapped[dict | None] = mapped_column(JSONB)

    state_history: Mapped[list["OrderStateHistory"]] = relationship(
        "OrderStateHistory", back_populates="order", lazy="dynamic"
    )
    fills: Mapped[list["Fill"]] = relationship("Fill", back_populates="order", lazy="dynamic")
    signal: Mapped[Optional["Signal"]] = relationship("Signal", back_populates="orders")


class OrderStateHistory(Base):
    """Order state transition audit log."""

    __tablename__ = "quant_order_state_history"
    __table_args__ = (
        Index("ix_state_history_order_id", "order_id"),
        Index("ix_state_history_occurred_at", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    order_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("quant_orders.id"), nullable=False)
    from_status: Mapped[OrderStatus | None] = mapped_column(SAEnum(OrderStatus))
    to_status: Mapped[OrderStatus] = mapped_column(SAEnum(OrderStatus), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), default="system")
    reason: Mapped[str | None] = mapped_column(Text)
    context: Mapped[dict | None] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    order: Mapped["Order"] = relationship("Order", back_populates="state_history")


class Fill(Base):
    """Trade fills / executions."""

    __tablename__ = "quant_fills"
    __table_args__ = (
        Index("ix_fills_symbol", "symbol"),
        Index("ix_fills_strategy", "strategy_id"),
        Index("ix_fills_filled_at", "filled_at"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    order_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("quant_orders.id"), nullable=False)
    broker_fill_id: Mapped[str | None] = mapped_column(String(128))

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[OrderSide] = mapped_column(SAEnum(OrderSide), nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False)

    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"))
    fee_currency: Mapped[str] = mapped_column(String(4), default="USD")

    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    regime: Mapped[RegimeType | None] = mapped_column(SAEnum(RegimeType))

    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    trading_mode: Mapped[str] = mapped_column(String(32), nullable=False)

    order: Mapped["Order"] = relationship("Order", back_populates="fills")


class Position(Base):
    """Current and historical positions."""

    __tablename__ = "quant_positions"
    __table_args__ = (
        Index("ix_positions_symbol", "symbol"),
        Index("ix_positions_strategy", "strategy_id"),
        Index("ix_positions_open", "is_open"),
        Index("ix_positions_symbol_open", "symbol", "is_open"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False)
    position_type: Mapped[PositionType] = mapped_column(SAEnum(PositionType), nullable=False)

    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    avg_entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))

    unrealized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"))

    stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    take_profit: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))

    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    close_reason: Mapped[CloseReason | None] = mapped_column(SAEnum(CloseReason))

    trading_mode: Mapped[str] = mapped_column(String(32), nullable=False)

    entry_order_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("quant_orders.id"))
    exit_order_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("quant_orders.id"))


class Signal(Base):
    """Trading signals from strategies."""

    __tablename__ = "quant_signals"
    __table_args__ = (
        Index("ix_signals_strategy", "strategy_id"),
        Index("ix_signals_symbol", "symbol"),
        Index("ix_signals_received_at", "received_at"),
        Index("ix_signals_processed", "processed"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    signal_type: Mapped[SignalType] = mapped_column(SAEnum(SignalType), nullable=False)

    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    strength: Mapped[str | None] = mapped_column(String(16))

    regime: Mapped[RegimeType | None] = mapped_column(SAEnum(RegimeType))
    indicator_values: Mapped[dict | None] = mapped_column(JSONB)

    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(32), default="tradingview")

    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    decision: Mapped[DecisionType | None] = mapped_column(SAEnum(DecisionType))
    # Kept as plain UUID to avoid a circular FK with quant_orders.
    order_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True))
    rejection_reason: Mapped[str | None] = mapped_column(String(256))

    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    orders: Mapped[list["Order"]] = relationship("Order", back_populates="signal")


class RiskCheck(Base):
    """Pre-trade risk validation results."""

    __tablename__ = "quant_risk_checks"
    __table_args__ = (
        Index("ix_risk_checks_result", "result"),
        Index("ix_risk_checks_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    signal_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("quant_signals.id"))

    result: Mapped[RiskCheckResult] = mapped_column(SAEnum(RiskCheckResult), nullable=False)
    checks: Mapped[dict] = mapped_column(JSONB, default=dict)
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    portfolio_exposure_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    daily_loss_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    current_drawdown_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Backtest(Base):
    """Backtest results."""

    __tablename__ = "quant_backtests"
    __table_args__ = (
        Index("ix_backtests_strategy", "strategy_id"),
        Index("ix_backtests_symbol", "symbol"),
        Index("ix_backtests_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False)

    start_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)

    initial_capital: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("10000"))
    final_capital: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))

    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0)
    losing_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    profit_factor: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    max_drawdown: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    max_drawdown_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    sharpe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    sortino_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    calmar_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    expectancy: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    avg_win: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    avg_loss: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    avg_rr: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    total_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    cagr: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))

    total_fees: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    total_slippage: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    slippage_used: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0.5"))
    commission_used: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("3.5"))

    params: Mapped[dict] = mapped_column(JSONB, default=dict)
    equity_curve: Mapped[list | None] = mapped_column(JSONB)
    monthly_returns: Mapped[list | None] = mapped_column(JSONB)

    is_walk_forward: Mapped[bool] = mapped_column(Boolean, default=False)
    oos_start_date: Mapped[datetime.date | None] = mapped_column(Date)
    overfitting_tests: Mapped[dict | None] = mapped_column(JSONB)

    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BacktestTrade(Base):
    """Individual trades from backtests."""

    __tablename__ = "quant_backtest_trades"
    __table_args__ = (Index("ix_backtest_trades_backtest_id", "backtest_id"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    backtest_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("quant_backtests.id"), nullable=False)

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    position_type: Mapped[PositionType] = mapped_column(SAEnum(PositionType), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)

    pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    return_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    fees: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"))

    close_reason: Mapped[CloseReason | None] = mapped_column(SAEnum(CloseReason))


class PortfolioSnapshot(Base):
    """Daily portfolio snapshots."""

    __tablename__ = "quant_portfolio_snapshots"
    __table_args__ = (UniqueConstraint("snapshot_date", name="uq_snapshots_date"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    snapshot_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)

    balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    equity: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    floating_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))

    daily_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    daily_pnl_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0"))

    open_positions: Mapped[int] = mapped_column(Integer, default=0)
    daily_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_trades_day: Mapped[int] = mapped_column(Integer, default=0)

    drawdown_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0"))
    peak_equity: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    portfolio_exposure_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0"))

    sharpe_7d: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    sharpe_30d: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    win_rate_20: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    expectancy_20: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))

    trading_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KillSwitchEvent(Base):
    """Kill switch trigger log."""

    __tablename__ = "quant_kill_switch_events"
    __table_args__ = (Index("ix_kill_switch_occurred_at", "occurred_at"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    switch_type: Mapped[KillSwitchType] = mapped_column(SAEnum(KillSwitchType), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    context: Mapped[dict | None] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reset_by: Mapped[str | None] = mapped_column(String(64))


class RiskEvent(Base):
    """Risk limit breach events."""

    __tablename__ = "quant_risk_events"
    __table_args__ = (
        Index("ix_risk_events_created_at", "created_at"),
        Index("ix_risk_events_severity", "severity"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[IncidentSeverity] = mapped_column(SAEnum(IncidentSeverity), nullable=False)

    symbol: Mapped[str | None] = mapped_column(String(16))
    strategy_id: Mapped[str | None] = mapped_column(String(64))

    value: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    threshold: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    action_taken: Mapped[str | None] = mapped_column(Text)

    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StrategyRegistry(Base):
    """Strategy registry with versioning."""

    __tablename__ = "quant_strategy_registry"
    __table_args__ = (
        UniqueConstraint("strategy_id", "version", name="uq_strategy_version"),
        Index("ix_strategy_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(16), default="1.0.0")

    group_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[StrategyStatus] = mapped_column(SAEnum(StrategyStatus), default=StrategyStatus.HYPOTHESIS)

    evidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    paper_days_completed: Mapped[int] = mapped_column(Integer, default=0)
    paper_trades_count: Mapped[int] = mapped_column(Integer, default=0)

    params: Mapped[dict] = mapped_column(JSONB, default=dict)
    symbols: Mapped[list] = mapped_column(JSONB, default=list)
    timeframes: Mapped[list] = mapped_column(JSONB, default=list)

    is_frozen: Mapped[bool] = mapped_column(Boolean, default=False)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MLModel(Base):
    """ML model registry."""

    __tablename__ = "quant_ml_models"
    __table_args__ = (
        Index("ix_ml_models_status", "status"),
        Index("ix_ml_models_strategy", "strategy_id"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(16), nullable=False)
    model_type: Mapped[str] = mapped_column(String(32), nullable=False)

    strategy_id: Mapped[str | None] = mapped_column(String(64))
    symbols: Mapped[list] = mapped_column(JSONB, default=list)

    accuracy: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    precision: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    recall: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    f1_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    oos_accuracy: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))

    feature_list: Mapped[list] = mapped_column(JSONB, default=list)
    file_path: Mapped[str | None] = mapped_column(String(512))
    training_data_hash: Mapped[str | None] = mapped_column(String(64))

    status: Mapped[ModelStatus] = mapped_column(SAEnum(ModelStatus), default=ModelStatus.RESEARCH)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)

    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    train_start: Mapped[datetime.date | None] = mapped_column(Date)
    train_end: Mapped[datetime.date | None] = mapped_column(Date)

    last_drift_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    drift_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))

    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    """Immutable audit trail."""

    __tablename__ = "quant_audit_log"
    __table_args__ = (
        Index("ix_audit_event_type", "event_type"),
        Index("ix_audit_actor", "actor"),
        Index("ix_audit_occurred_at", "occurred_at"),
    )

    id: Mapped[BigInteger] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    resource: Mapped[str | None] = mapped_column(String(128))
    action: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[str | None] = mapped_column(String(16))
    context: Mapped[dict | None] = mapped_column(JSONB)
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DataQualityRun(Base):
    """Data quality check results."""

    __tablename__ = "quant_data_quality_runs"
    __table_args__ = (
        Index("ix_dq_passed", "passed", "ran_at"),
        Index("ix_dq_symbol", "symbol"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(16))
    check_name: Mapped[DataQualityCheck] = mapped_column(SAEnum(DataQualityCheck), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaperDailyReport(Base):
    """Paper trading daily reports."""

    __tablename__ = "quant_paper_daily_reports"
    __table_args__ = (UniqueConstraint("report_date", name="uq_paper_report_date"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    report_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)

    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    open_positions_count: Mapped[int] = mapped_column(Integer, default=0)

    daily_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"))
    cumulative_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"))
    current_drawdown_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0"))

    win_rate_20: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    expectancy_20: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))

    avg_slippage_pips: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    fill_rate_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    incidents_count: Mapped[int] = mapped_column(Integer, default=0)
    gate_status: Mapped[str] = mapped_column(String(16), default="PASS")

    details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReconciliationLog(Base):
    """Broker reconciliation results."""

    __tablename__ = "quant_reconciliation_logs"
    __table_args__ = (
        Index("ix_recon_run_date", "run_date"),
        Index("ix_recon_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    run_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    broker_id: Mapped[str] = mapped_column(String(32), nullable=False)
    recon_type: Mapped[str] = mapped_column(String(32), nullable=False)

    status: Mapped[ReconciliationStatus] = mapped_column(SAEnum(ReconciliationStatus), nullable=False)
    severity: Mapped[str | None] = mapped_column(String(8))

    discrepancies: Mapped[list | None] = mapped_column(JSONB)
    internal_snap: Mapped[dict | None] = mapped_column(JSONB)
    broker_snap: Mapped[dict | None] = mapped_column(JSONB)
    actions_taken: Mapped[list | None] = mapped_column(JSONB)

    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
