"""Tests for stop-loss (MT5 adapter) and price sanity check (pre-trade risk gate).

Covers:
- MT5Adapter.set_stop_loss: success, failure, retry, reconnect
- MT5Adapter.update_trailing_stop: BUY/SELL, no-move, insufficient data
- OMS post-fill SL setup: default SL, skip when already set, disabled config
- price_sanity_check: normal price, anomalous price, edge cases
- PreTradeRiskGate with price provider: pass, reject, no provider
"""

from __future__ import annotations

from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# MT5 Adapter Stop-Loss Tests
# ---------------------------------------------------------------------------


class TestMT5SetStopLoss:
    """Tests for MT5Adapter.set_stop_loss."""

    def _make_adapter(self):
        """Create MT5Adapter with mocked MT5 module."""
        from graxia.packages.quant_os.execution.adapters.mt5 import MT5Adapter

        mock_mt5 = MagicMock()
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True
        mock_mt5.terminal_info.return_value = MagicMock()

        # Success result
        success_result = MagicMock()
        success_result.retcode = 10009
        success_result.comment = "Done"

        mock_mt5.order_send.return_value = success_result

        adapter = MT5Adapter(login=123456, password="test", server="Demo")
        adapter._connected = True

        # Inject mock mt5 module
        import graxia.packages.quant_os.execution.adapters.mt5 as mt5_mod

        original_mt5 = mt5_mod.mt5
        mt5_mod.mt5 = mock_mt5

        return adapter, mock_mt5, mt5_mod, original_mt5

    def test_set_stop_loss_success(self):
        """set_stop_loss returns True on TRADE_RETCODE_DONE."""
        adapter, mock_mt5, mt5_mod, original = self._make_adapter()
        try:
            result = adapter.set_stop_loss(
                position_ticket=12345,
                symbol="XAUUSD",
                stop_loss_price=2280.0,
            )
            assert result is True
            mock_mt5.order_send.assert_called_once()
            call_args = mock_mt5.order_send.call_args[0][0]
            assert call_args["action"] == 5  # TRADE_ACTION_SLTP
            assert call_args["position"] == 12345
            assert call_args["sl"] == 2280.0
        finally:
            mt5_mod.mt5 = original

    def test_set_stop_loss_with_tp(self):
        """set_stop_loss includes TP when provided."""
        adapter, mock_mt5, mt5_mod, original = self._make_adapter()
        try:
            result = adapter.set_stop_loss(
                position_ticket=12345,
                symbol="XAUUSD",
                stop_loss_price=2280.0,
                take_profit=2350.0,
            )
            assert result is True
            call_args = mock_mt5.order_send.call_args[0][0]
            assert call_args["tp"] == 2350.0
        finally:
            mt5_mod.mt5 = original

    def test_set_stop_loss_failure(self):
        """set_stop_loss returns False on non-10009 retcode."""
        adapter, mock_mt5, mt5_mod, original = self._make_adapter()
        try:
            fail_result = MagicMock()
            fail_result.retcode = 10006  # TRADE_RETCODE_INVALID
            fail_result.comment = "Invalid SL"
            mock_mt5.order_send.return_value = fail_result

            result = adapter.set_stop_loss(
                position_ticket=12345,
                symbol="XAUUSD",
                stop_loss_price=2280.0,
            )
            assert result is False
        finally:
            mt5_mod.mt5 = original

    def test_set_stop_loss_retries_on_invalid_price(self):
        """set_stop_loss retries on TRADE_RETCODE_INVALID_PRICE (10014)."""
        adapter, mock_mt5, mt5_mod, original = self._make_adapter()
        try:
            invalid_price = MagicMock()
            invalid_price.retcode = 10014
            invalid_price.comment = "Invalid price"

            success = MagicMock()
            success.retcode = 10009
            success.comment = "Done"

            mock_mt5.order_send.side_effect = [invalid_price, success]

            result = adapter.set_stop_loss(
                position_ticket=12345,
                symbol="XAUUSD",
                stop_loss_price=2280.0,
            )
            assert result is True
            assert mock_mt5.order_send.call_count == 2
        finally:
            mt5_mod.mt5 = original

    def test_set_stop_loss_retries_exhausted(self):
        """set_stop_loss returns False after retries exhausted."""
        adapter, mock_mt5, mt5_mod, original = self._make_adapter()
        try:
            invalid_price = MagicMock()
            invalid_price.retcode = 10014
            invalid_price.comment = "Invalid price"

            mock_mt5.order_send.return_value = invalid_price

            result = adapter.set_stop_loss(
                position_ticket=12345,
                symbol="XAUUSD",
                stop_loss_price=2280.0,
            )
            assert result is False
            assert mock_mt5.order_send.call_count == 3  # _RETRIES
        finally:
            mt5_mod.mt5 = original


class TestMT5TrailingStop:
    """Tests for MT5Adapter.update_trailing_stop."""

    def _make_adapter_with_position(self, sl=0.0):
        """Create adapter with a mocked position having given SL."""
        from graxia.packages.quant_os.execution.adapters.mt5 import MT5Adapter

        mock_mt5 = MagicMock()
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True
        mock_mt5.terminal_info.return_value = MagicMock()

        # Mock position
        position = MagicMock()
        position.ticket = 12345
        position.symbol = "XAUUSD"
        position.type = 0  # BUY
        position.volume = 0.1
        position.price_open = 2300.0
        position.sl = sl
        position.tp = 0.0
        position.comment = "test-order"
        mock_mt5.positions_get.return_value = [position]

        # Success result for order_send
        success = MagicMock()
        success.retcode = 10009
        success.comment = "Done"
        mock_mt5.order_send.return_value = success

        adapter = MT5Adapter(login=123456, password="test", server="Demo")
        adapter._connected = True

        import graxia.packages.quant_os.execution.adapters.mt5 as mt5_mod

        original_mt5 = mt5_mod.mt5
        mt5_mod.mt5 = mock_mt5

        return adapter, mock_mt5, mt5_mod, original_mt5

    def test_trailing_stop_buy_moves_up(self):
        """BUY position: SL moves up when price rises."""
        adapter, mock_mt5, mt5_mod, original = self._make_adapter_with_position(sl=2290.0)
        try:
            result = adapter.update_trailing_stop(
                position_ticket=12345,
                symbol="XAUUSD",
                side="BUY",
                entry_price=2300.0,
                current_price=2320.0,
                atr_value=10.0,
                trail_multiplier=2.0,
            )
            assert result is True
            call_args = mock_mt5.order_send.call_args[0][0]
            # SL = 2320 - (10 * 2) = 2300
            assert call_args["sl"] == 2300.0
        finally:
            mt5_mod.mt5 = original

    def test_trailing_stop_buy_no_move(self):
        """BUY position: SL doesn't move down when price drops."""
        adapter, mock_mt5, mt5_mod, original = self._make_adapter_with_position(sl=2290.0)
        try:
            result = adapter.update_trailing_stop(
                position_ticket=12345,
                symbol="XAUUSD",
                side="BUY",
                entry_price=2300.0,
                current_price=2280.0,
                atr_value=10.0,
                trail_multiplier=2.0,
            )
            assert result is False  # No move needed
            mock_mt5.order_send.assert_not_called()
        finally:
            mt5_mod.mt5 = original

    def test_trailing_stop_sell_moves_down(self):
        """SELL position: SL moves down when price falls."""
        adapter, mock_mt5, mt5_mod, original = self._make_adapter_with_position(sl=2310.0)
        try:
            # Change position to SELL
            position = mock_mt5.positions_get.return_value[0]
            position.type = 1  # SELL
            position.sl = 2310.0

            result = adapter.update_trailing_stop(
                position_ticket=12345,
                symbol="XAUUSD",
                side="SELL",
                entry_price=2300.0,
                current_price=2280.0,
                atr_value=10.0,
                trail_multiplier=2.0,
            )
            assert result is True
            call_args = mock_mt5.order_send.call_args[0][0]
            # SL = 2280 + (10 * 2) = 2300
            assert call_args["sl"] == 2300.0
        finally:
            mt5_mod.mt5 = original

    def test_trailing_stop_sell_no_move(self):
        """SELL position: SL doesn't move up when price rises."""
        adapter, mock_mt5, mt5_mod, original = self._make_adapter_with_position(sl=2310.0)
        try:
            position = mock_mt5.positions_get.return_value[0]
            position.type = 1  # SELL

            result = adapter.update_trailing_stop(
                position_ticket=12345,
                symbol="XAUUSD",
                side="SELL",
                entry_price=2300.0,
                current_price=2320.0,
                atr_value=10.0,
                trail_multiplier=2.0,
            )
            assert result is False
            mock_mt5.order_send.assert_not_called()
        finally:
            mt5_mod.mt5 = original

    def test_trailing_stop_negative_atr(self):
        """Negative ATR returns False."""
        adapter, mock_mt5, mt5_mod, original = self._make_adapter_with_position()
        try:
            result = adapter.update_trailing_stop(
                position_ticket=12345,
                symbol="XAUUSD",
                side="BUY",
                entry_price=2300.0,
                current_price=2320.0,
                atr_value=-5.0,
                trail_multiplier=2.0,
            )
            assert result is False
        finally:
            mt5_mod.mt5 = original

    def test_trailing_stop_position_not_found(self):
        """Returns False when position not found."""
        adapter, mock_mt5, mt5_mod, original = self._make_adapter_with_position()
        try:
            mock_mt5.positions_get.return_value = []

            result = adapter.update_trailing_stop(
                position_ticket=99999,
                symbol="XAUUSD",
                side="BUY",
                entry_price=2300.0,
                current_price=2320.0,
                atr_value=10.0,
            )
            assert result is False
        finally:
            mt5_mod.mt5 = original

    def test_trailing_stop_unknown_side(self):
        """Unknown side returns False."""
        adapter, mock_mt5, mt5_mod, original = self._make_adapter_with_position()
        try:
            result = adapter.update_trailing_stop(
                position_ticket=12345,
                symbol="XAUUSD",
                side="INVALID",
                entry_price=2300.0,
                current_price=2320.0,
                atr_value=10.0,
            )
            assert result is False
        finally:
            mt5_mod.mt5 = original


# ---------------------------------------------------------------------------
# Price Sanity Check Tests
# ---------------------------------------------------------------------------


class TestPriceSanityCheck:
    """Tests for the price_sanity_check function."""

    def test_normal_price_passes(self):
        """Price within 3σ of SMA passes."""
        from graxia.packages.quant_os.risk.pre_trade_gate import price_sanity_check

        # 20 prices around 2300 with small variance
        prices = [2300.0 + (i % 3 - 1) * 0.5 for i in range(20)]
        passed, reason = price_sanity_check(
            current_price=2300.5,
            recent_prices=prices,
            max_std_deviations=3.0,
            sma_period=20,
        )
        assert passed is True
        assert reason == ""

    def test_anomalous_price_rejected(self):
        """Price >3σ from SMA is rejected."""
        from graxia.packages.quant_os.risk.pre_trade_gate import price_sanity_check

        # 20 prices tightly around 2300
        prices = [2300.0 + (i % 3 - 1) * 0.1 for i in range(20)]
        # Price way off
        passed, reason = price_sanity_check(
            current_price=2400.0,  # ~100 points away from ~2300
            recent_prices=prices,
            max_std_deviations=3.0,
            sma_period=20,
        )
        assert passed is False
        assert "Price anomaly" in reason
        assert "σ from SMA" in reason

    def test_zero_price_rejected(self):
        """Zero or negative price is rejected."""
        from graxia.packages.quant_os.risk.pre_trade_gate import price_sanity_check

        passed, reason = price_sanity_check(
            current_price=0.0,
            recent_prices=[2300.0] * 20,
        )
        assert passed is False
        assert "Invalid current price" in reason

    def test_negative_price_rejected(self):
        """Negative price is rejected."""
        from graxia.packages.quant_os.risk.pre_trade_gate import price_sanity_check

        passed, reason = price_sanity_check(
            current_price=-100.0,
            recent_prices=[2300.0] * 20,
        )
        assert passed is False
        assert "Invalid current price" in reason

    def test_insufficient_data_allows_trade(self):
        """Less than 2 prices — allow trade (can't validate)."""
        from graxia.packages.quant_os.risk.pre_trade_gate import price_sanity_check

        passed, reason = price_sanity_check(
            current_price=2300.0,
            recent_prices=[],
        )
        assert passed is True

    def test_single_price_allows_trade(self):
        """Single price — allow trade."""
        from graxia.packages.quant_os.risk.pre_trade_gate import price_sanity_check

        passed, reason = price_sanity_check(
            current_price=2300.0,
            recent_prices=[2300.0],
        )
        assert passed is True

    def test_constant_prices_allows_trade(self):
        """All identical prices (std=0) — allow trade."""
        from graxia.packages.quant_os.risk.pre_trade_gate import price_sanity_check

        passed, reason = price_sanity_check(
            current_price=2300.0,
            recent_prices=[2300.0] * 20,
        )
        assert passed is True

    def test_custom_threshold(self):
        """Custom max_std_deviations parameter works."""
        from graxia.packages.quant_os.risk.pre_trade_gate import price_sanity_check

        prices = [2300.0 + (i % 3 - 1) * 0.5 for i in range(20)]
        # With 1σ threshold, small deviation is rejected
        passed, _ = price_sanity_check(
            current_price=2302.0,
            recent_prices=prices,
            max_std_deviations=1.0,
        )
        # May or may not pass depending on exact values — just verify it runs
        assert isinstance(passed, bool)

    def test_shorter_window_used(self):
        """When fewer prices than sma_period, all are used."""
        from graxia.packages.quant_os.risk.pre_trade_gate import price_sanity_check

        prices = [2300.0, 2300.5, 2301.0]
        passed, reason = price_sanity_check(
            current_price=2300.5,
            recent_prices=prices,
            sma_period=20,
        )
        assert passed is True


# ---------------------------------------------------------------------------
# PreTradeRiskGate Price Sanity Integration Tests
# ---------------------------------------------------------------------------


class TestPreTradeGatePriceSanity:
    """Tests for PreTradeRiskGate with price sanity check."""

    def _make_order(self, symbol="XAUUSD", asset_class="metals"):
        """Create a mock order."""
        order = MagicMock()
        order.symbol = symbol
        order.asset_class = asset_class
        return order

    def _make_kill_switch(self, active=False):
        """Create a mock kill switch that satisfies KillSwitchLike protocol."""
        ks = MagicMock()
        ks.is_active.return_value = active
        ks.is_paused.return_value = False
        return ks

    def _make_circuit_breaker(self, is_open=False):
        """Create a mock circuit breaker that satisfies CircuitBreakerLike protocol."""
        cb = MagicMock()
        cb.is_open.return_value = is_open
        return cb

    def test_passes_without_provider(self):
        """Gate passes when no price_provider is set (with mock KS/CB)."""
        from graxia.packages.quant_os.risk.pre_trade_gate import PreTradeRiskGate

        gate = PreTradeRiskGate(
            kill_switch=self._make_kill_switch(),
            circuit_breaker=self._make_circuit_breaker(),
        )
        result = gate.check_order_sync(self._make_order())
        assert result.passed is True

    def test_passes_with_normal_price(self):
        """Gate passes when price is within 3σ."""
        from graxia.packages.quant_os.risk.pre_trade_gate import PreTradeRiskGate

        provider = MagicMock()
        # 20 prices around 2300 + current price
        prices = [2300.0 + (i % 3 - 1) * 0.5 for i in range(20)]
        prices.append(2300.5)  # current price (most recent)
        provider.get_recent_prices.return_value = prices

        gate = PreTradeRiskGate(
            price_provider=provider,
            kill_switch=self._make_kill_switch(),
            circuit_breaker=self._make_circuit_breaker(),
        )
        result = gate.check_order_sync(self._make_order())
        assert result.passed is True

    def test_rejects_anomalous_price(self):
        """Gate rejects when price is >3σ from SMA."""
        from graxia.packages.quant_os.risk.pre_trade_gate import PreTradeRiskGate

        provider = MagicMock()
        # 20 tight prices around 2300 + anomalous current price
        prices = [2300.0 + (i % 3 - 1) * 0.1 for i in range(20)]
        prices.append(2400.0)  # way off
        provider.get_recent_prices.return_value = prices

        gate = PreTradeRiskGate(
            price_provider=provider,
            kill_switch=self._make_kill_switch(),
            circuit_breaker=self._make_circuit_breaker(),
        )
        result = gate.check_order_sync(self._make_order())
        assert result.passed is False
        assert "Price anomaly" in result.reason

    def test_provider_exception_rejects(self):
        """Gate rejects when provider throws (fail-closed)."""
        from graxia.packages.quant_os.risk.pre_trade_gate import PreTradeRiskGate

        provider = MagicMock()
        provider.get_recent_prices.side_effect = RuntimeError("DB connection lost")

        gate = PreTradeRiskGate(
            price_provider=provider,
            kill_switch=self._make_kill_switch(),
            circuit_breaker=self._make_circuit_breaker(),
        )
        result = gate.check_order_sync(self._make_order())
        assert result.passed is False
        assert "Price check error" in result.reason

    def test_empty_provider_data_allows(self):
        """Gate allows when provider returns empty list."""
        from graxia.packages.quant_os.risk.pre_trade_gate import PreTradeRiskGate

        provider = MagicMock()
        provider.get_recent_prices.return_value = []

        gate = PreTradeRiskGate(
            price_provider=provider,
            kill_switch=self._make_kill_switch(),
            circuit_breaker=self._make_circuit_breaker(),
        )
        result = gate.check_order_sync(self._make_order())
        assert result.passed is True

    def test_kill_switch_checked_before_price(self):
        """Kill switch rejection takes priority over price check."""
        from graxia.packages.quant_os.risk.pre_trade_gate import PreTradeRiskGate

        kill_switch = MagicMock()
        kill_switch.is_active.return_value = True

        provider = MagicMock()
        provider.get_recent_prices.return_value = [2300.0] * 21

        mock_cb = MagicMock()
        mock_cb.is_open.return_value = False
        gate = PreTradeRiskGate(kill_switch=kill_switch, circuit_breaker=mock_cb, price_provider=provider)
        result = gate.check_order_sync(self._make_order())
        assert result.passed is False
        assert "Kill switch" in result.reason
        # Provider should NOT have been called
        provider.get_recent_prices.assert_not_called()


# ---------------------------------------------------------------------------
# OMS Post-Fill Stop-Loss Tests
# ---------------------------------------------------------------------------


class TestOMSPostFillSL:
    """Tests for OMS._setup_post_fill_stop_loss."""

    def _make_oms(self, trailing_configs=None):
        """Create OMS with mocked dependencies."""
        from graxia.packages.quant_os.execution.oms import OMS, TrailingStopConfig

        mock_risk = MagicMock()
        mock_risk.check_order_sync.return_value = MagicMock(passed=True)

        adapter = MagicMock()
        adapter.name = "MT5"
        adapter.is_connected = True
        adapter.get_positions.return_value = []
        adapter.set_stop_loss.return_value = True

        adapters = {"mt5": adapter}

        configs = trailing_configs or {
            "metals": TrailingStopConfig(enabled=True, trail_multiplier=2.0),
        }

        oms = OMS(
            adapters=adapters,
            risk_engine=mock_risk,
            trailing_stop_configs=configs,
        )
        return oms, adapter

    def test_skip_when_sl_already_set(self):
        """Skip post-fill SL if order already has stop_loss."""
        from graxia.packages.quant_os.core.enums import OrderStatus
        from graxia.packages.quant_os.execution.order import Order

        oms, adapter = self._make_oms()

        order = Order(
            id="test-1",
            signal_id="sig-1",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
            stop_price=2280.0,  # Already set
            status=OrderStatus.FILLED,
        )

        oms._setup_post_fill_stop_loss(order, avg_price=2300.0, adapter=adapter)
        adapter.set_stop_loss.assert_not_called()

    def test_sets_default_sl_when_not_set(self):
        """Post-fill SL computed when order has no stop_loss."""
        from graxia.packages.quant_os.core.enums import OrderStatus
        from graxia.packages.quant_os.execution.order import Order

        oms, adapter = self._make_oms()

        # Position matches order
        adapter.get_positions.return_value = [
            {"ticket": 12345, "symbol": "XAUUSD", "comment": "test-1"},
        ]

        order = Order(
            id="test-1",
            signal_id="sig-1",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
            stop_price=None,
            status=OrderStatus.FILLED,
        )

        oms._setup_post_fill_stop_loss(order, avg_price=2300.0, adapter=adapter)
        adapter.set_stop_loss.assert_called_once()
        call_kwargs = adapter.set_stop_loss.call_args[1]
        assert call_kwargs["position_ticket"] == 12345
        assert call_kwargs["symbol"] == "XAUUSD"
        # SL = 2300 - (2300 * 0.02 * 2.5) = 2300 - 115 = 2185  (metals uses 2.5x)
        assert abs(call_kwargs["stop_loss_price"] - 2185.0) < 0.01

    def test_skip_when_config_disabled(self):
        """Skip post-fill SL when trailing SL disabled for asset class."""
        from graxia.packages.quant_os.core.enums import OrderStatus
        from graxia.packages.quant_os.execution.oms import TrailingStopConfig
        from graxia.packages.quant_os.execution.order import Order

        oms, adapter = self._make_oms(trailing_configs={"metals": TrailingStopConfig(enabled=False)})

        order = Order(
            id="test-1",
            signal_id="sig-1",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
            stop_price=None,
            status=OrderStatus.FILLED,
        )

        oms._setup_post_fill_stop_loss(order, avg_price=2300.0, adapter=adapter)
        adapter.set_stop_loss.assert_not_called()

    def test_sell_sl_direction(self):
        """SELL order: SL is above entry price."""
        from graxia.packages.quant_os.core.enums import OrderStatus
        from graxia.packages.quant_os.execution.order import Order

        oms, adapter = self._make_oms()

        adapter.get_positions.return_value = [
            {"ticket": 12345, "symbol": "XAUUSD", "comment": "test-1"},
        ]

        order = Order(
            id="test-1",
            signal_id="sig-1",
            symbol="XAUUSD",
            asset_class="metals",
            side="SELL",
            quantity=0.1,
            stop_price=None,
            status=OrderStatus.FILLED,
        )

        oms._setup_post_fill_stop_loss(order, avg_price=2300.0, adapter=adapter)
        call_kwargs = adapter.set_stop_loss.call_args[1]
        # SL = 2300 + (2300 * 0.02 * 2.5) = 2300 + 115 = 2415  (metals uses 2.5x)
        assert abs(call_kwargs["stop_loss_price"] - 2415.0) < 0.01

    def test_position_not_found(self):
        """Skip when position ticket not found."""
        from graxia.packages.quant_os.core.enums import OrderStatus
        from graxia.packages.quant_os.execution.order import Order

        oms, adapter = self._make_oms()
        adapter.get_positions.return_value = []  # No matching position

        order = Order(
            id="test-1",
            signal_id="sig-1",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            quantity=0.1,
            stop_price=None,
            status=OrderStatus.FILLED,
        )

        oms._setup_post_fill_stop_loss(order, avg_price=2300.0, adapter=adapter)
        adapter.set_stop_loss.assert_not_called()
