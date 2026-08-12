"""Tests for Phase 2B: Safety-critical infrastructure."""

import os
import sys
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

# Add graxia/packages to sys.path so quant_os is importable as a package
_PACKAGES = Path(__file__).resolve().parent.parent.parent  # graxia/packages
_QUANT_OS = _PACKAGES / "quant_os"
if str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

from quant_os.broker.contract_snapshot_store import ContractSnapshotStore
from quant_os.broker.contract_spec import ContractSpec, compute_snapshot_hash
from quant_os.risk.kill_switch import KillSwitch
from quant_os.risk.position_sizer_v2 import SizingResult, size_position
from quant_os.risk.pre_trade_risk import pre_trade_check
from quant_os.risk.risk_ledger import RiskLedger
from quant_os.risk.risk_policy import RiskPolicy

# ============================================================
# FIXTURES
# ============================================================


def _make_spec(**overrides) -> ContractSpec:
    """Build a valid ContractSpec with defaults."""
    defaults = dict(
        broker="TestBroker",
        server="TestBroker-Demo",
        symbol="XAUUSD",
        account_currency="USD",
        digits=2,
        point=Decimal("0.01"),
        trade_contract_size=Decimal("100"),
        trade_tick_size=Decimal("0.01"),
        trade_tick_value=Decimal("1.0"),
        volume_min=Decimal("0.01"),
        volume_max=Decimal("100"),
        volume_step=Decimal("0.01"),
        stops_level_points=50,
        freeze_level_points=50,
        currency_base="USD",
        currency_profit="USD",
        currency_margin="USD",
        trade_mode=0,
        filling_mode=1,
        execution_mode=0,
        captured_at_utc=datetime(2025, 1, 15, 12, 0, 0),
        snapshot_hash="",
    )
    defaults.update(overrides)
    spec = ContractSpec(**defaults)
    h = compute_snapshot_hash(spec)
    return ContractSpec(**{**spec.__dict__, "snapshot_hash": h})


def _xauusd_spec() -> ContractSpec:
    """XAUUSD fixture: contract_size=100, tick_size=0.01, tick_value=1.0."""
    return _make_spec(
        symbol="XAUUSD",
        trade_contract_size=Decimal("100"),
        trade_tick_size=Decimal("0.01"),
        trade_tick_value=Decimal("1.0"),
        volume_min=Decimal("0.01"),
        volume_max=Decimal("100"),
        volume_step=Decimal("0.01"),
        stops_level_points=50,
        digits=2,
        point=Decimal("0.01"),
    )


def _eurusd_spec() -> ContractSpec:
    """EURUSD fixture: contract_size=100000, tick_size=0.00001, tick_value=1.0."""
    return _make_spec(
        symbol="EURUSD",
        trade_contract_size=Decimal("100000"),
        trade_tick_size=Decimal("0.00001"),
        trade_tick_value=Decimal("1.0"),
        volume_min=Decimal("0.01"),
        volume_max=Decimal("100"),
        volume_step=Decimal("0.01"),
        stops_level_points=10,
        digits=5,
        point=Decimal("0.00001"),
    )


def _risk_policy() -> RiskPolicy:
    return RiskPolicy(
        risk_per_trade_bps=100,  # 1.00%
        max_daily_loss_bps=200,  # 2.00%
        max_weekly_loss_bps=500,  # 5.00%
        max_total_drawdown_bps=1000,  # 10.00%
        max_open_positions=5,
        max_orders_per_day=20,
    )


# ============================================================
# 1-4: ContractSpec tests
# ============================================================


class TestContractSpec:
    def test_contract_spec_validate_valid(self):
        spec = _xauusd_spec()
        errors = spec.validate()
        assert errors == []

    def test_contract_spec_validate_zero_tick_value(self):
        spec = _make_spec(trade_tick_value=Decimal("0"))
        errors = spec.validate()
        assert any("trade_tick_value" in e for e in errors)

    def test_contract_spec_validate_volume_min_gt_max(self):
        spec = _make_spec(
            volume_min=Decimal("10"),
            volume_max=Decimal("1"),
        )
        errors = spec.validate()
        assert any("volume_max" in e for e in errors)

    def test_contract_spec_frozen(self):
        spec = _xauusd_spec()
        with pytest.raises(AttributeError):
            spec.symbol = "EURUSD"  # type: ignore[misc]


# ============================================================
# 5-6: ContractSnapshotStore tests
# ============================================================


class TestContractSnapshotStore:
    def test_contract_snapshot_store_save_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ContractSnapshotStore(base_dir=tmpdir)
            spec = _xauusd_spec()
            h = store.save(spec)
            loaded = store.load(h)
            assert loaded.symbol == "XAUUSD"
            assert loaded.trade_contract_size == Decimal("100")
            assert loaded.snapshot_hash == h

    def test_contract_snapshot_hash_deterministic(self):
        spec = _xauusd_spec()
        h1 = compute_snapshot_hash(spec)
        h2 = compute_snapshot_hash(spec)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex length


# ============================================================
# 7-12: Position sizer tests
# ============================================================


class TestPositionSizer:
    def test_sizer_valid_input(self):
        spec = _xauusd_spec()
        result = size_position(
            symbol="XAUUSD",
            side="BUY",
            entry_price=Decimal("2000.00"),
            stop_loss=Decimal("1990.00"),
            equity=Decimal("10000"),
            contract_spec=spec,
            risk_policy=_risk_policy(),
        )
        assert not result.rejected
        assert result.volume > 0

    def test_sizer_zero_sl_rejects(self):
        spec = _xauusd_spec()
        result = size_position(
            symbol="XAUUSD",
            side="BUY",
            entry_price=Decimal("2000.00"),
            stop_loss=Decimal("0"),
            equity=Decimal("10000"),
            contract_spec=spec,
            risk_policy=_risk_policy(),
        )
        assert result.rejected
        assert any("zero" in r.lower() for r in result.rejection_reasons)

    def test_sizer_wrong_side_sl_rejects(self):
        spec = _xauusd_spec()
        result = size_position(
            symbol="XAUUSD",
            side="BUY",
            entry_price=Decimal("2000.00"),
            stop_loss=Decimal("2010.00"),  # BUY SL above entry = wrong
            equity=Decimal("10000"),
            contract_spec=spec,
            risk_policy=_risk_policy(),
        )
        assert result.rejected
        assert any("above entry" in r.lower() for r in result.rejection_reasons)

    def test_sizer_below_min_volume_rejects(self):
        spec = _xauusd_spec()
        # Tiny equity → tiny volume → below volume_min
        result = size_position(
            symbol="XAUUSD",
            side="BUY",
            entry_price=Decimal("2000.00"),
            stop_loss=Decimal("1900.00"),
            equity=Decimal("0.01"),  # Micro equity
            contract_spec=spec,
            risk_policy=_risk_policy(),
        )
        assert result.rejected
        assert any("volume_min" in r for r in result.rejection_reasons)

    def test_sizer_rounds_down_to_step(self):
        spec = _xauusd_spec()
        result = size_position(
            symbol="XAUUSD",
            side="BUY",
            entry_price=Decimal("2000.00"),
            stop_loss=Decimal("1990.00"),
            equity=Decimal("10000"),
            contract_spec=spec,
            risk_policy=_risk_policy(),
        )
        # volume should be a multiple of volume_step (0.01)
        assert not result.rejected
        step = spec.volume_step
        remainder = result.volume % step
        assert remainder == Decimal("0"), f"volume {result.volume} not aligned to step {step}"

    def test_sizer_risk_never_exceeds_budget(self):
        spec = _xauusd_spec()
        result = size_position(
            symbol="XAUUSD",
            side="BUY",
            entry_price=Decimal("2000.00"),
            stop_loss=Decimal("1990.00"),
            equity=Decimal("10000"),
            contract_spec=spec,
            risk_policy=_risk_policy(),
        )
        assert not result.rejected
        assert (
            result.risk_amount <= result.risk_budget
        ), f"risk_amount {result.risk_amount} exceeds budget {result.risk_budget}"


# ============================================================
# 13-16: Pre-trade risk check tests
# ============================================================


class TestPreTradeRisk:
    def _ok_sizer_result(self) -> SizingResult:
        return SizingResult(
            volume=Decimal("0.10"),
            volume_before_round=Decimal("0.10"),
            risk_amount=Decimal("100"),
            risk_budget=Decimal("100"),
            loss_at_stop=Decimal("100"),
            margin_estimate=Decimal("500"),
            rejected=False,
            rejection_reasons=[],
            contract_snapshot_id="abc",
        )

    def test_pre_trade_check_daily_loss_blocks(self):
        ledger = RiskLedger.__new__(RiskLedger)
        ledger._state = ledger._default_state()
        ledger._state["daily_realized_loss"] = 500.0  # Hit daily limit
        ledger._state_file = Path(tempfile.mktemp(suffix=".json"))

        policy = RiskPolicy(max_daily_loss_bps=200)
        result = pre_trade_check(
            self._ok_sizer_result(),
            policy,
            ledger,
            account_equity=Decimal("10000"),
        )
        assert not result.approved
        assert any("Daily loss" in r for r in result.reasons)

    def test_pre_trade_check_weekly_loss_blocks(self):
        ledger = RiskLedger.__new__(RiskLedger)
        ledger._state = ledger._default_state()
        ledger._state["weekly_realized_loss"] = 600.0  # Hit weekly limit
        ledger._state_file = Path(tempfile.mktemp(suffix=".json"))

        policy = RiskPolicy(max_weekly_loss_bps=500)
        result = pre_trade_check(
            self._ok_sizer_result(),
            policy,
            ledger,
            account_equity=Decimal("10000"),
        )
        assert not result.approved
        assert any("Weekly loss" in r for r in result.reasons)

    def test_pre_trade_check_max_positions_blocks(self):
        ledger = RiskLedger.__new__(RiskLedger)
        ledger._state = ledger._default_state()
        ledger._state["open_positions"] = 5  # At limit
        ledger._state_file = Path(tempfile.mktemp(suffix=".json"))

        policy = RiskPolicy(max_open_positions=5)
        result = pre_trade_check(
            self._ok_sizer_result(),
            policy,
            ledger,
            account_equity=Decimal("10000"),
        )
        assert not result.approved
        assert any("Max positions" in r for r in result.reasons)

    def test_pre_trade_check_kill_switch_blocks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ks = KillSwitch(state_file=os.path.join(tmpdir, "ks.json"))
            ks.activate("test block")

            ledger = RiskLedger.__new__(RiskLedger)
            ledger._state = ledger._default_state()
            ledger._state_file = Path(tempfile.mktemp(suffix=".json"))

            result = pre_trade_check(
                self._ok_sizer_result(),
                _risk_policy(),
                ledger,
                account_equity=Decimal("10000"),
                kill_switch=ks,
            )
            assert not result.approved
            assert any("Kill switch" in r for r in result.reasons)


# ============================================================
# 17-18: Kill switch tests
# ============================================================


class TestKillSwitch:
    def test_kill_switch_activate_deactivate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ks = KillSwitch(state_file=os.path.join(tmpdir, "ks.json"))
            assert not ks.is_active()
            ks.activate("test reason")
            assert ks.is_active()
            ks.deactivate("test done", authorized_by="admin")
            assert not ks.is_active()

    def test_kill_switch_persists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "ks.json")
            ks1 = KillSwitch(state_file=path)
            ks1.activate("persist test")
            # New instance loads from file
            ks2 = KillSwitch(state_file=path)
            assert ks2.is_active()


# ============================================================
# 19: Risk ledger test
# ============================================================


class TestRiskLedger:
    def test_risk_ledger_daily_tracking(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = RiskLedger(state_file=os.path.join(tmpdir, "ledger.json"))
            ledger.record_trade(pnl=-50.0, symbol="XAUUSD", volume=0.1)
            ledger.record_trade(pnl=-30.0, symbol="EURUSD", volume=0.2)
            assert ledger.daily_realized_loss == 80.0
            ledger.record_trade(pnl=100.0, symbol="GBPUSD", volume=0.1)
            # Positive trades don't add to loss
            assert ledger.daily_realized_loss == 80.0


# ============================================================
# 20-21: Safety assertions — no order_send anywhere
# ============================================================


class TestNoOrderSend:
    def test_no_order_send_in_broker(self):
        broker_dir = _QUANT_OS / "broker"
        for py in broker_dir.glob("*.py"):
            content = py.read_text(encoding="utf-8")
            # Check for function definitions of forbidden functions
            for fn in ("order_send", "order_modify", "order_close"):
                assert f"def {fn}" not in content, f"{fn} found in {py.name}"

    def test_no_order_send_in_risk(self):
        risk_dir = _QUANT_OS / "risk"
        for py in risk_dir.glob("*.py"):
            content = py.read_text(encoding="utf-8")
            for fn in ("order_send", "order_modify", "order_close"):
                assert f"def {fn}" not in content, f"{fn} found in {py.name}"


# ============================================================
# 22-23: Golden sizing tests
# ============================================================


class TestGoldenSizing:
    def test_golden_xauusd_sizing(self):
        """
        XAUUSD: contract_size=100, tick_size=0.01, tick_value=1.0
        Entry: 2000.00, SL: 1990.00, Equity: 10000, Risk: 1%
        Stop distance = 10.00 → 1000 ticks → one-lot loss = 1000 * 1.0 * 100 = 100,000
        Wait — tick_value is per contract? Let me recalculate.
        Actually tick_value for XAUUSD is per tick per lot. So:
        ticks = 10.00 / 0.01 = 1000
        one_lot_loss = 1000 * 1.0 = 1000 USD (per 1 lot = 100 oz)
        risk_budget = 10000 * 1% = 100
        raw_volume = 100 / 1000 = 0.1 lot
        rounded = 0.10 (step=0.01)
        """
        spec = _xauusd_spec()
        result = size_position(
            symbol="XAUUSD",
            side="BUY",
            entry_price=Decimal("2000.00"),
            stop_loss=Decimal("1990.00"),
            equity=Decimal("10000"),
            contract_spec=spec,
            risk_policy=_risk_policy(),
        )
        assert not result.rejected, f"Rejected: {result.rejection_reasons}"
        assert result.volume == Decimal("0.10")
        # Risk should be exactly 100 (0.1 lot * 1000 ticks * 1.0 tick_value)
        assert result.risk_amount == Decimal("100")

    def test_golden_eurusd_sizing(self):
        """
        EURUSD: contract_size=100000, tick_size=0.00001, tick_value=1.0
        Entry: 1.10000, SL: 1.09900, Equity: 10000, Risk: 1%
        Stop distance = 0.00100
        Ticks = 0.00100 / 0.00001 = 100
        one_lot_loss = 100 * 1.0 = 100 USD (per 1 lot = 100k units)
        risk_budget = 10000 * 1% = 100
        raw_volume = 100 / 100 = 1.00 lot
        rounded = 1.00 (step=0.01)
        """
        spec = _eurusd_spec()
        result = size_position(
            symbol="EURUSD",
            side="BUY",
            entry_price=Decimal("1.10000"),
            stop_loss=Decimal("1.09900"),
            equity=Decimal("10000"),
            contract_spec=spec,
            risk_policy=_risk_policy(),
        )
        assert not result.rejected, f"Rejected: {result.rejection_reasons}"
        assert result.volume == Decimal("1.00")
        assert result.risk_amount == Decimal("100")
