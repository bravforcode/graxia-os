"""Tests for RiskBudget — daily/weekly loss limits and position caps."""


from graxia.packages.quant_os.core.risk_budget import RiskBudget


class TestRiskBudgetDefaults:
    def test_default_limits(self):
        rb = RiskBudget()
        assert rb.max_daily_loss_pct == 2.0
        assert rb.max_weekly_loss_pct == 5.0
        assert rb.max_open_positions == 3

    def test_can_trade_fresh(self):
        rb = RiskBudget()
        ok, msg = rb.can_trade()
        assert ok is True
        assert msg == "OK"


class TestDailyLossLimit:
    def test_blocks_at_daily_limit(self):
        rb = RiskBudget(max_daily_loss_pct=2.0)
        rb.record_trade(-1.5)
        ok, _ = rb.can_trade()
        assert ok is True
        rb.record_trade(-0.6)  # total -2.1
        ok, msg = rb.can_trade()
        assert ok is False
        assert "Daily loss limit" in msg

    def test_daily_loss_exact_boundary(self):
        rb = RiskBudget(max_daily_loss_pct=2.0)
        rb.record_trade(-2.0)
        ok, _ = rb.can_trade()
        assert ok is False


class TestWeeklyLossLimit:
    def test_blocks_at_weekly_limit(self):
        rb = RiskBudget(max_daily_loss_pct=20.0, max_weekly_loss_pct=5.0)
        rb.record_trade(-3.0)
        ok, _ = rb.can_trade()
        assert ok is True
        rb.record_trade(-2.1)  # total -5.1
        ok, msg = rb.can_trade()
        assert ok is False
        assert "Weekly loss limit" in msg

    def test_weekly_loss_exact_boundary(self):
        rb = RiskBudget(max_daily_loss_pct=20.0, max_weekly_loss_pct=5.0)
        rb.record_trade(-5.0)
        ok, _ = rb.can_trade()
        assert ok is False


class TestMaxPositions:
    def test_blocks_when_max_reached(self):
        rb = RiskBudget(max_open_positions=3)
        for _ in range(3):
            rb.record_position_open()
        ok, msg = rb.can_trade()
        assert ok is False
        assert "Max open positions" in msg

    def test_allows_below_max(self):
        rb = RiskBudget(max_open_positions=3)
        rb.record_position_open()
        rb.record_position_open()
        ok, _ = rb.can_trade()
        assert ok is True


class TestDailyReset:
    def test_daily_pnl_resets_on_new_day(self):
        rb = RiskBudget(max_daily_loss_pct=2.0)
        rb.record_trade(-2.5)
        ok, _ = rb.can_trade()
        assert ok is False
        # Simulate next day
        rb.daily_reset_date = "2000-01-01"
        ok, _ = rb.can_trade()
        assert ok is True
        assert rb.current_daily_pnl == 0.0

    def test_weekly_pnl_resets_on_new_week(self):
        rb = RiskBudget(max_daily_loss_pct=20.0, max_weekly_loss_pct=5.0)
        rb.record_trade(-6.0)
        ok, _ = rb.can_trade()
        assert ok is False
        # Simulate next week
        rb.weekly_reset_date = "2000-W01"
        ok, _ = rb.can_trade()
        assert ok is True
        assert rb.current_weekly_pnl == 0.0


class TestRecordTrade:
    def test_record_trade_updates_pnl(self):
        rb = RiskBudget()
        rb.record_trade(1.5)
        assert rb.current_daily_pnl == 1.5
        assert rb.current_weekly_pnl == 1.5
        rb.record_trade(-0.5)
        assert rb.current_daily_pnl == 1.0
        assert rb.current_weekly_pnl == 1.0


class TestPositionTracking:
    def test_open_close_tracking(self):
        rb = RiskBudget(max_open_positions=3)
        rb.record_position_open()
        rb.record_position_open()
        assert rb.open_positions == 2
        rb.record_position_close()
        assert rb.open_positions == 1
        rb.record_position_close()
        assert rb.open_positions == 0

    def test_close_does_not_go_negative(self):
        rb = RiskBudget()
        rb.record_position_close()
        assert rb.open_positions == 0


class TestTradeAfterClose:
    def test_can_trade_again_after_positions_close(self):
        rb = RiskBudget(max_open_positions=2)
        rb.record_position_open()
        rb.record_position_open()
        ok, _ = rb.can_trade()
        assert ok is False
        rb.record_position_close()
        ok, _ = rb.can_trade()
        assert ok is True
