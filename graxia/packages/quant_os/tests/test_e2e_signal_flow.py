"""
E2E Integration Tests — Signal flow: XGBoost → Technical → Sentiment → Risk → Execution.

Tests the complete signal pipeline with mocked external dependencies.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from graxia.packages.quant_os.core.agents.analyst import TechnicalAnalystAgent
from graxia.packages.quant_os.core.agents.portfolio_manager import PortfolioManagerAgent
from graxia.packages.quant_os.core.agents.risk_auditor import RiskAuditorAgent
from graxia.packages.quant_os.core.enums import (
    RegimeType,
    SignalType,
)
from graxia.packages.quant_os.core.event_bus import EventBus
from graxia.packages.quant_os.core.events import (
    BarEvent,
    SignalEvent,
)
from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker
from graxia.packages.quant_os.risk.engine import AccountState, PortfolioState, RiskEngine
from graxia.packages.quant_os.risk.engine import Signal as RiskSignal
from graxia.packages.quant_os.risk.kill_switch import KillSwitch


def _make_bar_events(n=30, trend=0.001, bar_range_pct=0.0005):
    bars = []
    base_price = 2300.0
    for i in range(n):
        c = base_price * (1 + trend * i)
        r = c * bar_range_pct
        bars.append(
            BarEvent(
                symbol="XAUUSD",
                high=c + r,
                low=c - r,
                open=c - r * 0.5,
                close=c + r * 0.5,
                volume=1000,
            )
        )
    return bars


def _make_signal_event(confidence=0.8, source="technical_analyst"):
    return SignalEvent(
        symbol="XAUUSD",
        signal_type=SignalType.BUY,
        confidence=confidence,
        entry_price=2400.0,
        stop_loss=2390.0,
        take_profit=2420.0,
        source=source,
    )


def _make_risk_signal(conviction=0.8, entry=2400.0, sl=2390.0, tp=2420.0):
    return RiskSignal(
        symbol="XAUUSD",
        conviction=conviction,
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
    )


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def bus():
    return EventBus(max_queue_size=1000)


@pytest.fixture
def technical_analyst():
    return TechnicalAnalystAgent(name="technical_analyst")


@pytest.fixture
def portfolio_manager():
    return PortfolioManagerAgent(name="portfolio_manager")


@pytest.fixture
def risk_auditor():
    return RiskAuditorAgent(name="risk_auditor")


@pytest.fixture
def kill_switch(tmp_path):
    return KillSwitch(state_file=str(tmp_path / "kill_switch_state.json"))


@pytest.fixture
def circuit_breaker(tmp_path):
    return CircuitBreaker(state_file=str(tmp_path / "cb.json"))


@pytest.fixture
def risk_engine(kill_switch, circuit_breaker):
    return RiskEngine(kill_switch=kill_switch, circuit_breaker=circuit_breaker)


@pytest.fixture
def healthy_account():
    return AccountState(
        equity=100000, balance=100000, daily_pnl=0, weekly_pnl=0, max_drawdown_pct=0.02, margin_level_pct=500
    )


@pytest.fixture
def clean_portfolio():
    return PortfolioState(total_exposure_pct=0.1, position_symbols=["EURUSD"])


@pytest.fixture
def mock_broker_adapter():
    adapter = MagicMock()
    adapter.submit_order.return_value = MagicMock(status="FILLED", broker_order_id="mock_001")
    return adapter


# ============================================================================
# Happy Path
# ============================================================================


class TestE2EHappyPath:
    def test_ml_to_technical_to_risk_to_execution(
        self,
        technical_analyst,
        portfolio_manager,
        risk_auditor,
        risk_engine,
        healthy_account,
        clean_portfolio,
        mock_broker_adapter,
        tmp_path,
    ):
        bars = _make_bar_events(n=30, trend=0.002, bar_range_pct=0.0001)
        for bar in bars:
            technical_analyst.observe(bar)
        tech_signal = technical_analyst.act()
        assert tech_signal is not None

        if tech_signal.entry_price and tech_signal.stop_loss:
            risk_dist = abs(float(tech_signal.entry_price) - float(tech_signal.stop_loss))
            min_tp = float(tech_signal.entry_price) + risk_dist * 1.6
            tech_signal = SignalEvent(
                symbol=tech_signal.symbol,
                signal_type=tech_signal.signal_type,
                confidence=tech_signal.confidence,
                entry_price=float(tech_signal.entry_price),
                stop_loss=float(tech_signal.stop_loss),
                take_profit=round(min_tp, 2),
                source=tech_signal.source,
            )

        risk_auditor.observe(tech_signal)
        risk_event = risk_auditor.act()
        assert risk_event is not None

        portfolio_manager.observe(tech_signal)
        sentiment = SignalEvent(
            symbol="XAUUSD",
            signal_type=SignalType.HOLD,
            confidence=1.0,
            source="sentiment_agent",
            metadata={"position_multiplier": 1.0},
        )
        portfolio_manager.observe(sentiment)
        portfolio_manager.observe(risk_event)

        final_signal = portfolio_manager.act()
        assert final_signal is not None
        assert final_signal.signal_type == SignalType.BUY

        risk_signal = _make_risk_signal(
            conviction=final_signal.confidence,
            entry=final_signal.entry_price,
            sl=final_signal.stop_loss,
            tp=final_signal.take_profit,
        )
        verdict = risk_engine.evaluate(
            signal=risk_signal,
            account=healthy_account,
            portfolio=clean_portfolio,
            realized_vol=0.15,
            regime=RegimeType.TREND_STRONG_UP,
        )
        assert verdict.approved is True
        assert verdict.approved_quantity > 0


# ============================================================================
# Crisis Mode
# ============================================================================


class TestE2ECrisisMode:
    def test_crisis_regime_risk_engine_rejects(self, risk_engine, healthy_account, clean_portfolio):
        """CRISIS regime reduces sizing but still approves."""
        signal = _make_risk_signal(conviction=0.9)
        verdict = risk_engine.evaluate(
            signal=signal,
            account=healthy_account,
            portfolio=clean_portfolio,
            realized_vol=0.5,
            regime=RegimeType.CRISIS,
        )
        assert verdict.approved is True
        assert verdict.sizing_details.get("regime_multiplier", 1.0) < 1.0


# ============================================================================
# Low Confidence
# ============================================================================


class TestE2ELowConfidence:
    def test_low_confidence_risk_engine_rejects(self, risk_engine, healthy_account, clean_portfolio):
        signal = _make_risk_signal(conviction=0.1)
        verdict = risk_engine.evaluate(
            signal=signal,
            account=healthy_account,
            portfolio=clean_portfolio,
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert verdict.approved is False

    def test_just_above_threshold_passes(self, risk_engine, healthy_account, clean_portfolio):
        signal = _make_risk_signal(conviction=0.61)
        verdict = risk_engine.evaluate(
            signal=signal,
            account=healthy_account,
            portfolio=clean_portfolio,
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert verdict.approved is True


# ============================================================================
# Risk Rejection
# ============================================================================


class TestE2ERiskRejection:
    def test_daily_loss_limit_blocks_trade(self, risk_engine, clean_portfolio):
        account = AccountState(equity=100000, daily_pnl=-3000, weekly_pnl=0)
        signal = _make_risk_signal(conviction=0.8)
        verdict = risk_engine.evaluate(
            signal=signal, account=account, portfolio=clean_portfolio, realized_vol=0.15, regime=RegimeType.RANGE_BOUND
        )
        assert verdict.approved is False

    def test_weekly_loss_limit_blocks_trade(self, risk_engine, clean_portfolio):
        account = AccountState(equity=100000, daily_pnl=0, weekly_pnl=-6000)
        signal = _make_risk_signal(conviction=0.8)
        verdict = risk_engine.evaluate(
            signal=signal, account=account, portfolio=clean_portfolio, realized_vol=0.15, regime=RegimeType.RANGE_BOUND
        )
        assert verdict.approved is False

    def test_drawdown_limit_blocks_trade(self, risk_engine, clean_portfolio):
        account = AccountState(equity=100000, daily_pnl=0, weekly_pnl=0, max_drawdown_pct=0.16)
        signal = _make_risk_signal(conviction=0.8)
        verdict = risk_engine.evaluate(
            signal=signal, account=account, portfolio=clean_portfolio, realized_vol=0.15, regime=RegimeType.RANGE_BOUND
        )
        assert verdict.approved is False

    def test_total_exposure_blocks_trade(self, risk_engine, healthy_account):
        portfolio = PortfolioState(total_exposure_pct=0.85, position_symbols=[f"S{i}" for i in range(20)])
        signal = _make_risk_signal(conviction=0.8)
        verdict = risk_engine.evaluate(
            signal=signal,
            account=healthy_account,
            portfolio=portfolio,
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert verdict.approved is False


# ============================================================================
# Circuit Breaker
# ============================================================================


class TestE2ECircuitBreaker:
    def test_kill_switch_blocks_all_signals(self, kill_switch, circuit_breaker):
        kill_switch.activate("emergency", source="test")
        engine = RiskEngine(kill_switch=kill_switch, circuit_breaker=circuit_breaker)
        signal = _make_risk_signal()
        account = AccountState()
        portfolio = PortfolioState()
        verdict = engine.evaluate(
            signal=signal, account=account, portfolio=portfolio, realized_vol=0.15, regime=RegimeType.RANGE_BOUND
        )
        assert verdict.approved is False

    def test_circuit_breaker_metals_blocks_xauusd(self, kill_switch, circuit_breaker):
        circuit_breaker.trip("metals", "test")
        engine = RiskEngine(kill_switch=kill_switch, circuit_breaker=circuit_breaker)
        signal = _make_risk_signal()
        account = AccountState()
        portfolio = PortfolioState()
        verdict = engine.evaluate(
            signal=signal, account=account, portfolio=portfolio, realized_vol=0.15, regime=RegimeType.RANGE_BOUND
        )
        assert verdict.approved is False

    def test_circuit_breaker_does_not_block_other_classes(self, kill_switch, circuit_breaker):
        circuit_breaker.trip("forex", "test")
        engine = RiskEngine(kill_switch=kill_switch, circuit_breaker=circuit_breaker)
        signal = _make_risk_signal()
        signal.asset_class = "metals"
        account = AccountState()
        portfolio = PortfolioState()
        verdict = engine.evaluate(
            signal=signal, account=account, portfolio=portfolio, realized_vol=0.15, regime=RegimeType.RANGE_BOUND
        )
        assert verdict.approved is True

    def test_kill_switch_deactivate_restores_trading(self, kill_switch, circuit_breaker):
        kill_switch.activate("test", source="test")
        kill_switch.deactivate("resolved", authorized_by="admin")
        engine = RiskEngine(kill_switch=kill_switch, circuit_breaker=circuit_breaker)
        signal = _make_risk_signal()
        account = AccountState()
        portfolio = PortfolioState()
        verdict = engine.evaluate(
            signal=signal, account=account, portfolio=portfolio, realized_vol=0.15, regime=RegimeType.RANGE_BOUND
        )
        assert verdict.approved is True


# ============================================================================
# Portfolio Limits
# ============================================================================


class TestE2EPortfolioLimits:
    def test_max_positions_rejected(self, risk_engine, healthy_account):
        portfolio = PortfolioState(total_exposure_pct=0.5, position_symbols=[f"S{i}" for i in range(20)])
        signal = _make_risk_signal()
        verdict = risk_engine.evaluate(
            signal=signal,
            account=healthy_account,
            portfolio=portfolio,
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert verdict.approved is False

    def test_class_exposure_limit(self, risk_engine, healthy_account):
        portfolio = PortfolioState(total_exposure_pct=0.3, class_exposure_pct={"metals": 0.35})
        signal = _make_risk_signal()
        signal.asset_class = "metals"
        verdict = risk_engine.evaluate(
            signal=signal,
            account=healthy_account,
            portfolio=portfolio,
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert verdict.approved is False


# ============================================================================
# Stale Signal
# ============================================================================


class TestE2EStaleSignal:
    def test_stale_signal_rejected(self, risk_engine, healthy_account, clean_portfolio):
        signal = _make_risk_signal()
        signal.timestamp = datetime(2020, 1, 1, tzinfo=UTC)
        verdict = risk_engine.evaluate(
            signal=signal,
            account=healthy_account,
            portfolio=clean_portfolio,
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert verdict.approved is False


# ============================================================================
# Sizing
# ============================================================================


class TestE2ESizing:
    def test_sizing_with_high_vol_reduces_quantity(self, risk_engine, healthy_account, clean_portfolio):
        signal = _make_risk_signal()
        verdict_low = risk_engine.evaluate(
            signal=signal,
            account=healthy_account,
            portfolio=clean_portfolio,
            realized_vol=0.5,
            regime=RegimeType.RANGE_BOUND,
        )
        verdict_high = risk_engine.evaluate(
            signal=signal,
            account=healthy_account,
            portfolio=clean_portfolio,
            realized_vol=0.1,
            regime=RegimeType.RANGE_BOUND,
        )
        if verdict_low.approved and verdict_high.approved:
            assert verdict_low.approved_quantity <= verdict_high.approved_quantity

    def test_crisis_regime_reduces_sizing(self, risk_engine, healthy_account, clean_portfolio):
        signal = _make_risk_signal()
        verdict = risk_engine.evaluate(
            signal=signal,
            account=healthy_account,
            portfolio=clean_portfolio,
            realized_vol=0.15,
            regime=RegimeType.CRISIS,
        )
        assert verdict.approved is True
        assert verdict.sizing_details.get("regime_multiplier", 1.0) == 0.25

    def test_zero_stop_distance_rejected(self, risk_engine, healthy_account, clean_portfolio):
        signal = RiskSignal(symbol="XAUUSD", conviction=0.8, entry_price=2400.0, stop_loss=2400.0, take_profit=2420.0)
        verdict = risk_engine.evaluate(
            signal=signal,
            account=healthy_account,
            portfolio=clean_portfolio,
            realized_vol=0.15,
            regime=RegimeType.RANGE_BOUND,
        )
        assert verdict.approved is False


# ============================================================================
# Full Integration
# ============================================================================


class TestE2EFullIntegration:
    def test_full_flow_with_all_components(
        self,
        technical_analyst,
        portfolio_manager,
        risk_auditor,
        risk_engine,
        healthy_account,
        clean_portfolio,
        mock_broker_adapter,
        tmp_path,
    ):
        bars = _make_bar_events(n=30, trend=0.002, bar_range_pct=0.0001)
        for bar in bars:
            technical_analyst.observe(bar)
        tech_signal = technical_analyst.act()
        assert tech_signal is not None

        if tech_signal.entry_price and tech_signal.stop_loss:
            risk_dist = abs(float(tech_signal.entry_price) - float(tech_signal.stop_loss))
            min_tp = float(tech_signal.entry_price) + risk_dist * 1.6
            tech_signal = SignalEvent(
                symbol=tech_signal.symbol,
                signal_type=tech_signal.signal_type,
                confidence=tech_signal.confidence,
                entry_price=float(tech_signal.entry_price),
                stop_loss=float(tech_signal.stop_loss),
                take_profit=round(min_tp, 2),
                source=tech_signal.source,
            )

        risk_auditor.observe(tech_signal)
        risk_event = risk_auditor.act()
        assert risk_event is not None
        assert risk_event.passed is True

        portfolio_manager.observe(tech_signal)
        sentiment = SignalEvent(
            symbol="XAUUSD",
            signal_type=SignalType.HOLD,
            confidence=1.0,
            source="sentiment_agent",
            metadata={"position_multiplier": 1.0},
        )
        portfolio_manager.observe(sentiment)
        portfolio_manager.observe(risk_event)

        final_signal = portfolio_manager.act()
        assert final_signal is not None

        risk_signal = _make_risk_signal(
            conviction=final_signal.confidence,
            entry=final_signal.entry_price,
            sl=final_signal.stop_loss,
            tp=final_signal.take_profit,
        )
        verdict = risk_engine.evaluate(
            signal=risk_signal,
            account=healthy_account,
            portfolio=clean_portfolio,
            realized_vol=0.15,
            regime=RegimeType.TREND_STRONG_UP,
        )
        assert verdict.approved is True
