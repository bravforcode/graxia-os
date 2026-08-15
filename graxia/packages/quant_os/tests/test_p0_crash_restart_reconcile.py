"""P0 integration test: signal -> risk -> order -> crash/restart -> reconcile.

Validates the WS-D live-path safety guarantee: an executed position is recorded
in the disk-backed ledger (the authoritative state), survives a process restart
(reloaded from the same SQLite file), and reconciles cleanly against the broker.
Also proves the reconciler CATCHES a lost position (LOCAL_ONLY) rather than
silently continuing -- the failure mode that would let a crash go undetected.
"""

from datetime import UTC, datetime
from decimal import Decimal

from graxia.packages.quant_os.core.enums import PositionType, RegimeType
from graxia.packages.quant_os.execution.broker_adapter import BrokerAdapter, BrokerPosition
from graxia.packages.quant_os.execution.ledger import Ledger, Position
from graxia.packages.quant_os.execution.reconcile import Reconciler, ReconciliationStatus
from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker
from graxia.packages.quant_os.risk.engine import (
    AccountState,
    PortfolioState,
    RiskEngine,
)
from graxia.packages.quant_os.risk.engine import (
    Signal as RiskSignal,
)
from graxia.packages.quant_os.risk.kill_switch import KillSwitch


def _make_position() -> Position:
    # Opened with qty 0; the execution fill (apply_fill) sets the real quantity.
    now = datetime.now(UTC)
    return Position(
        position_id="pos-p0-001",
        symbol="XAUUSD",
        asset_class="metals",
        venue="pepperstone",
        side="LONG",
        quantity=Decimal("0"),
        entry_price=Decimal("2300.00"),
        current_price=Decimal("2300.00"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        swap_cost=Decimal("0"),
        commission=Decimal("0"),
        opened_at=now,
        updated_at=now,
        signal_id="sig-p0-001",
        strategy_id="p0_test",
        broker_position_id="brk-p0-001",
    )


class MockAdapter(BrokerAdapter):
    """Minimal broker adapter: returns a controllable position book."""

    def __init__(self, positions=None):
        self.name = "mock"
        self._connected = False
        self._positions = list(positions or [])

    async def connect(self):
        return True

    async def disconnect(self):
        pass

    async def get_account(self):
        return None

    async def get_positions(self):
        return self._positions

    async def get_position(self, symbol):
        return next((p for p in self._positions if p.symbol == symbol), None)

    async def place_order(self, order):
        return None

    async def cancel_order(self, broker_order_id):
        return False

    async def get_order_status(self, broker_order_id):
        return None

    async def get_price(self, symbol):
        return {"bid": Decimal("1"), "ask": Decimal("1")}


class TestP0CrashRestartReconcile:
    def test_position_survives_restart_and_reconciles_clean(self, tmp_path):
        import asyncio

        db = str(tmp_path / "ledger.db")

        # --- signal -> risk -> order (record in ledger) ---
        kill = KillSwitch(state_file=str(tmp_path / "ks.json"))
        cb = CircuitBreaker(state_file=str(tmp_path / "cb.json"))
        risk = RiskEngine(kill_switch=kill, circuit_breaker=cb)
        acct = AccountState(equity=100000, balance=100000, max_drawdown_pct=0.02, margin_level_pct=500)
        port = PortfolioState(total_exposure_pct=0.1, position_symbols=[])
        sig = RiskSignal(
            symbol="XAUUSD",
            conviction=0.8,
            entry_price=2300.0,
            stop_loss=2290.0,
            take_profit=2320.0,
        )
        verdict = risk.evaluate(
            signal=sig,
            account=acct,
            portfolio=port,
            realized_vol=0.15,
            regime=RegimeType.TREND_STRONG_UP,
        )
        assert verdict.approved is True

        ledger = Ledger(db)
        pos = _make_position()
        ledger.save_position(pos)
        ledger.apply_fill(
            pos.position_id,
            Decimal("0.10"),
            Decimal("2300.00"),
            commission=Decimal("7.00"),
        )
        ledger.close()

        # --- CRASH / RESTART: brand-new ledger instance on the same db file ---
        ledger2 = Ledger(db)
        open_positions = ledger2.get_all_open()
        assert len(open_positions) == 1
        assert open_positions[0].position_id == "pos-p0-001"
        assert open_positions[0].quantity == Decimal("0.10")

        # --- RECONCILE against broker reporting the same position ---
        broker_pos = BrokerPosition(
            symbol="XAUUSD",
            position_type=PositionType.LONG,
            quantity=Decimal("0.10"),
            avg_price=Decimal("2300.00"),
            unrealized_pnl=Decimal("0"),
        )
        adapter = MockAdapter([broker_pos])
        reconciler = Reconciler(ledger2, {"pepperstone": adapter})
        result = asyncio.run(reconciler.reconcile_venue("pepperstone"))

        assert result.status == ReconciliationStatus.CLEAN
        assert result.mismatches == []
        ledger2.close()

    def test_reconcile_detects_lost_position_after_restart(self, tmp_path):
        import asyncio

        db = str(tmp_path / "ledger.db")
        ledger = Ledger(db)
        pos = _make_position()
        ledger.save_position(pos)
        ledger.apply_fill(pos.position_id, Decimal("0.10"), Decimal("2300.00"))
        ledger.close()

        # Restart
        ledger2 = Ledger(db)
        assert len(ledger2.get_all_open()) == 1

        # Broker reports NO position (e.g. closed externally / lost in crash).
        # The reconciler MUST flag LOCAL_ONLY rather than stay silent.
        adapter = MockAdapter([])
        reconciler = Reconciler(ledger2, {"pepperstone": adapter})
        result = asyncio.run(reconciler.reconcile_venue("pepperstone"))

        assert result.status == ReconciliationStatus.MISMATCH
        assert len(result.mismatches) == 1
        assert result.mismatches[0].mismatch_type.value == "LOCAL_ONLY"
        assert result.mismatches[0].severity == "CRITICAL"
        ledger2.close()
