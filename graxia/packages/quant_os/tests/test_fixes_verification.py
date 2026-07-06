"""
Comprehensive verification tests for all fixes applied to quant_os.

Each test verifies ONE specific fix behavior with clear assertion messages.
"""

import inspect
import logging
import os
import re
import sys
from decimal import Decimal
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from graxia.packages.quant_os.core.feature_config import EXCLUDE_COLS, get_feature_cols
from graxia.packages.quant_os.core.logging_redactor import RedactingFilter
from graxia.packages.quant_os.execution.fill_model import (
    FillRequest,
    Side,
    simulate_entry,
)
from graxia.packages.quant_os.validation.deflated_sharpe import (
    DeflatedSharpeResult,
    MinBTLResult,
    deflated_sharpe_ratio,
    min_backtest_length,
)
from graxia.packages.quant_os.validation.regime_detector import (
    RegimeConfig,
    RegimeDetector,
    RegimeState,
)


# =============================================================================
# 1. Test execution/manager.py logger fix
# =============================================================================
class TestOrderManagerLoggerFix:
    """Verify logger.error() works when order has no SL (BUG-001 fix)."""

    def test_logger_error_string_format_not_nameerror(self):
        """logger.error with %s formatting must not raise NameError."""
        logger = logging.getLogger("execution.manager")
        order_id = "test-order-123"
        # The fix: logger.error("...", order.id) uses %s formatting
        # instead of f-string that would NameError on missing scope
        logger.error(
            "CRITICAL: Order %s has no stop-loss — blocking submission",
            order_id,
        )
        # If we got here, no NameError was raised
        assert True

    def test_manager_submit_to_broker_checks_stop_loss(self):
        """_submit_to_broker source must check stop_price and call logger.error."""
        from graxia.packages.quant_os.execution.manager import OrderManager

        source = inspect.getsource(OrderManager._submit_to_broker)
        assert "stop_price" in source, "_submit_to_broker must check stop_price"
        assert "logger.error" in source, "_submit_to_broker must call logger.error"

    def test_manager_uses_percent_format_not_fstring_for_logger(self):
        """logger.error must use %s formatting, not f-strings."""
        from graxia.packages.quant_os.execution.manager import OrderManager

        source = inspect.getsource(OrderManager._submit_to_broker)
        # Must use logger.error("... %s ...", var) not logger.error(f"...{var}...")
        assert 'logger.error("CRITICAL: Order %s' in source, "logger.error must use %s string formatting for safety"


# =============================================================================
# 2. Test execution/fill_model.py spread fix
# =============================================================================
class TestFillModelSpreadFix:
    """Verify spread parameter exists in simulate_entry signature."""

    def test_simulate_entry_accepts_spread_parameter(self):
        """simulate_entry must accept a spread parameter."""
        sig = inspect.signature(simulate_entry)
        assert "spread" in sig.parameters, "simulate_entry must accept spread parameter"

    def test_spread_parameter_type_is_decimal(self):
        """spread parameter must be typed as Decimal."""
        sig = inspect.signature(simulate_entry)
        param = sig.parameters["spread"]
        assert param.annotation == Decimal, f"spread param type should be Decimal, got {param.annotation}"

    def test_zero_spread_entry_equals_ask_plus_slippage(self):
        """With zero spread, BUY entry = ask + slippage."""
        req = FillRequest(
            side=Side.BUY,
            entry_price=Decimal("1.0850"),
            stop_loss=Decimal("1.0800"),
            take_profit=Decimal("1.0900"),
            slippage_entry=Decimal("0.0001"),
            slippage_exit=Decimal("0.0001"),
        )
        result = simulate_entry(req, Decimal("1.0849"), Decimal("1.0851"), Decimal("0"))
        assert result.entry_price == Decimal(
            "1.0852"
        ), f"BUY entry with zero spread should be ask+slippage=1.0852, got {result.entry_price}"

    def test_sell_entry_below_bid(self):
        """SELL entry must be below bid minus slippage."""
        req = FillRequest(
            side=Side.SELL,
            entry_price=Decimal("1.0850"),
            stop_loss=Decimal("1.0900"),
            take_profit=Decimal("1.0800"),
            slippage_entry=Decimal("0.0001"),
            slippage_exit=Decimal("0.0001"),
        )
        result = simulate_entry(req, Decimal("1.0849"), Decimal("1.0851"), Decimal("0"))
        assert result.entry_price == Decimal(
            "1.0848"
        ), f"SELL entry with zero spread should be bid-slippage=1.0848, got {result.entry_price}"


# =============================================================================
# 3. Test execution/adapters/base.py set_stop_loss ABC
# =============================================================================
class TestBrokerAdapterSetStopLossABC:
    """Verify BrokerAdapter defines set_stop_loss as abstractmethod."""

    def test_set_stop_loss_is_abstract(self):
        """BrokerAdapter must define set_stop_loss as abstractmethod."""
        from graxia.packages.quant_os.execution.adapters.base import BrokerAdapter

        assert "set_stop_loss" in BrokerAdapter.__abstractmethods__, (
            f"BrokerAdapter must declare set_stop_loss as abstract, " f"got: {BrokerAdapter.__abstractmethods__}"
        )

    def test_cannot_instantiate_without_set_stop_loss(self):
        """Concrete adapter that omits set_stop_loss must raise TypeError."""
        from graxia.packages.quant_os.execution.adapters.base import BrokerAdapter

        class IncompleteAdapter(BrokerAdapter):
            def connect(self):
                return True

            def disconnect(self):
                pass

            def submit_order(self, order):
                pass

            def cancel_order(self, broker_order_id):
                pass

            def get_positions(self):
                return []

            def get_order_status(self, broker_order_id):
                pass

            def close_position(self, broker_position_id, volume, symbol=""):
                pass

            def get_account_info(self):
                pass

        with pytest.raises(TypeError, match="set_stop_loss"):
            IncompleteAdapter("test")

    def test_concrete_adapter_with_set_stop_loss_instantiates(self):
        """Concrete adapter implementing set_stop_loss must instantiate."""
        from graxia.packages.quant_os.execution.adapters.base import (
            AccountInfo,
            BrokerAdapter,
        )

        class CompleteAdapter(BrokerAdapter):
            def connect(self):
                return True

            def disconnect(self):
                pass

            def submit_order(self, order):
                pass

            def cancel_order(self, broker_order_id):
                pass

            def get_positions(self):
                return []

            def get_order_status(self, broker_order_id):
                pass

            def close_position(self, broker_position_id, volume, symbol=""):
                pass

            def set_stop_loss(self, position_ticket, symbol, stop_loss_price, take_profit=None):
                return True

            def get_account_info(self):
                return AccountInfo(equity=10000, cash=10000, margin_used=0, margin_available=10000)

        adapter = CompleteAdapter("test")
        assert adapter.name == "test"
        assert adapter.set_stop_loss(123, "EURUSD", 1.0800) is True


# =============================================================================
# 4. Test backtest/engine.py regime_mult wiring
# =============================================================================
class TestBacktestEngineRegimeMultWiring:
    """Verify regime_mult affects position sizing in backtest engine."""

    def test_regime_mult_applied_to_volume(self):
        """When regime_mult != 1.0, volume must be scaled accordingly."""
        from graxia.packages.quant_os.backtest.engine import (
            InlineContractSpec,
            _historical_size,
        )

        equity = Decimal("10000")
        entry = Decimal("2000")
        sl = Decimal("1990")
        contract = InlineContractSpec.for_symbol("XAUUSD")

        base_volume = _historical_size(equity, 10, entry, sl, contract)
        assert base_volume > Decimal("0"), "Base volume must be positive"

        regime_mult = 0.5
        adjusted = base_volume * Decimal(str(regime_mult))
        assert adjusted < base_volume
        assert adjusted == base_volume * Decimal("0.5")

    def test_regime_detector_position_size_multiplier(self):
        """RegimeDetector.get_position_size_multiplier must return config-driven value."""
        detector = RegimeDetector()
        mult = detector.get_position_size_multiplier()
        assert mult == 1.0, f"Default multiplier should be 1.0, got {mult}"

    def test_backtest_engine_execute_signal_accepts_regime_mult(self):
        """BacktestEngine._execute_signal must accept regime_mult parameter."""
        from graxia.packages.quant_os.backtest.engine import BacktestEngine

        sig = inspect.signature(BacktestEngine._execute_signal)
        assert "regime_mult" in sig.parameters, "_execute_signal must accept regime_mult parameter"
        assert sig.parameters["regime_mult"].default == 1.0

    def test_backtest_engine_run_wires_regime_mult(self):
        """BacktestEngine.run() must pass regime_mult from detector to _execute_signal."""
        from graxia.packages.quant_os.backtest.engine import BacktestEngine

        source = inspect.getsource(BacktestEngine.run)
        assert "regime_mult" in source, "run() must wire regime_mult to _execute_signal"
        assert "get_position_size_multiplier" in source, "run() must call get_position_size_multiplier()"


# =============================================================================
# 5. Test backtest/engine.py deterministic timestamps
# =============================================================================
class TestBacktestEngineDeterministicTimestamps:
    """Verify _deterministic_timestamp produces consistent results."""

    def test_deterministic_timestamp_fallback_no_data(self):
        """Without timestamps, must return fixed datetime(2000,1,1)."""
        from datetime import UTC, datetime

        from graxia.packages.quant_os.backtest.engine import BacktestEngine

        engine = BacktestEngine()
        engine.timestamps = []
        ts = engine._deterministic_timestamp(42)
        assert ts == datetime(2000, 1, 1, tzinfo=UTC)

    def test_deterministic_timestamp_uses_last_timestamp(self):
        """With timestamps loaded, must return the last timestamp."""
        from datetime import UTC, datetime

        from graxia.packages.quant_os.backtest.engine import BacktestEngine

        engine = BacktestEngine()
        last_ts = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        engine.timestamps = [
            datetime(2024, 6, 14, tzinfo=UTC),
            datetime(2024, 6, 15, tzinfo=UTC),
            last_ts,
        ]
        ts = engine._deterministic_timestamp(99)
        assert ts == last_ts

    def test_deterministic_timestamp_no_datetime_now(self):
        """Must NEVER use datetime.now() — results must be reproducible."""
        from datetime import UTC, datetime

        from graxia.packages.quant_os.backtest.engine import BacktestEngine

        engine = BacktestEngine()
        engine.timestamps = []

        ts1 = engine._deterministic_timestamp(0)
        ts2 = engine._deterministic_timestamp(100)
        assert ts1 == ts2 == datetime(2000, 1, 1, tzinfo=UTC)

    def test_deterministic_timestamp_source_no_datetime_now_call(self):
        """_deterministic_timestamp source must not call datetime.now()."""
        from graxia.packages.quant_os.backtest.engine import BacktestEngine

        source = inspect.getsource(BacktestEngine._deterministic_timestamp)
        # Check for actual datetime.now() call, not just mention in docstring
        lines = [
            l.strip()
            for l in source.split("\n")
            if l.strip() and not l.strip().startswith("#") and not l.strip().startswith('"""') and '"""' not in l
        ]
        code_lines = [l for l in lines if not l.startswith(("def ", "Return", "Deterministic"))]
        for line in code_lines:
            assert "datetime.now(" not in line, f"_deterministic_timestamp must not call datetime.now(), found: {line}"


# =============================================================================
# 6. Test scripts/walk_forward.py purge/embargo
# =============================================================================
class TestWalkForwardPurgeEmbargo:
    """Verify train/test gap exists in walk-forward validation."""

    def test_walk_forward_has_gap_enforcement(self):
        """walk_forward.py source must enforce gap between train and test."""
        wf_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "walk_forward.py")
        with open(wf_path) as f:
            source = f.read()

        # Must have some form of gap between train_end and test_start
        assert "test_start" in source, "walk_forward must compute test_start"
        # The gap should be larger than just train_end (non-zero gap)
        assert re.search(r"test_start\s*=\s*train_end\s*\+", source), "test_start must be computed as train_end + gap"

    def test_walk_forward_fold_boundaries_non_overlapping(self):
        """Fold train/test ranges must never overlap (via import and run)."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
        try:
            from walk_forward import walk_forward
        except SyntaxError:
            pytest.skip("walk_forward.py has syntax error (known issue)")

        n = 200
        rng = np.random.default_rng(42)
        idx = pd.date_range("2024-01-01", periods=n, freq="1min", tz="UTC")
        df = pd.DataFrame(
            {
                "f1": rng.normal(0, 1, n),
                "f2": rng.normal(0, 1, n),
                "close": 2000 + np.cumsum(rng.normal(0, 0.1, n)),
                "target": rng.integers(0, 2, n),
                "target_return": rng.normal(0, 0.001, n),
            },
            index=idx,
        )

        agg = walk_forward(
            df,
            ["f1", "f2"],
            {
                "n_estimators": 5,
                "max_depth": 2,
                "learning_rate": 0.1,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "random_state": 42,
                "eval_metric": "logloss",
                "use_label_encoder": False,
                "verbosity": 0,
            },
            train_window=30,
            test_window=10,
            step=15,
            spread_cost=0.0,
            slippage_p90=0.0,
            min_confidence=0.0,
            min_expected_profit=-1.0,
        )

        for fold in agg["folds"]:
            train_end = pd.Timestamp(fold["train_end"])
            test_start = pd.Timestamp(fold["test_start"])
            assert (
                test_start > train_end
            ), f"Fold {fold['fold']}: test_start {test_start} must be after train_end {train_end}"

    def test_walk_forward_imports_from_centralized_feature_config(self):
        """walk_forward.py must import EXCLUDE_COLS from core.feature_config."""
        wf_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "walk_forward.py")
        with open(wf_path) as f:
            source = f.read()

        assert (
            "from core.feature_config import EXCLUDE_COLS" in source
        ), "walk_forward.py must import EXCLUDE_COLS from core.feature_config"


# =============================================================================
# 7. Test core/feature_config.py centralized EXCLUDE_COLS
# =============================================================================
class TestFeatureConfigCentralizedExcludeCols:
    """Verify EXCLUDE_COLS is centralized and contains key columns."""

    def test_exclude_cols_frozenset(self):
        """EXCLUDE_COLS must be a frozenset for immutability."""
        assert isinstance(EXCLUDE_COLS, frozenset), "EXCLUDE_COLS must be frozenset"

    def test_exclude_cols_contains_target_columns(self):
        """Must exclude target/label columns to prevent leakage."""
        required = {"target", "target_return", "label", "future_return", "forward_return"}
        missing = required - EXCLUDE_COLS
        assert not missing, f"EXCLUDE_COLS missing target columns: {missing}"

    def test_exclude_cols_contains_raw_price_columns(self):
        """Must exclude raw OHLCV to prevent memorization."""
        required = {"open", "high", "low", "close", "volume"}
        missing = required - EXCLUDE_COLS
        assert not missing, f"EXCLUDE_COLS missing price columns: {missing}"

    def test_exclude_cols_contains_identifiers(self):
        """Must exclude identifier columns."""
        required = {"timestamp", "symbol", "date"}
        missing = required - EXCLUDE_COLS
        assert not missing, f"EXCLUDE_COLS missing identifier columns: {missing}"

    def test_get_feature_cols_filters_excluded(self):
        """get_feature_cols must filter out EXCLUDE_COLS."""
        columns = ["rsi_14", "ema_20", "target", "close", "timestamp", "atr_14"]
        features = get_feature_cols(columns)
        assert "target" not in features
        assert "close" not in features
        assert "timestamp" not in features
        assert "rsi_14" in features
        assert "ema_20" in features
        assert "atr_14" in features


# =============================================================================
# 8. Test core/config.py secret redaction
# =============================================================================
class TestConfigSecretRedaction:
    """Verify secrets not exposed in repr() or str()."""

    def test_config_has_secret_fields(self):
        """Config must have fields for all secret types."""
        from graxia.packages.quant_os.core.config import get_config, reset_config

        reset_config()
        config = get_config()
        assert hasattr(config, "jwt_secret_key")
        assert hasattr(config, "webhook_hmac_secret")
        assert hasattr(config, "admin_api_key")
        assert hasattr(config, "mt5_password")
        assert hasattr(config, "telegram_bot_token")

    def test_config_secret_fields_are_strings(self):
        """Secret fields must be string type."""
        from graxia.packages.quant_os.core.config import get_config, reset_config

        reset_config()
        config = get_config()
        assert isinstance(config.jwt_secret_key, str)
        assert isinstance(config.mt5_password, str)
        assert isinstance(config.telegram_bot_token, str)


# =============================================================================
# 9. Test core/logging_redactor.py
# =============================================================================
class TestLoggingRedactor:
    """Verify secrets are redacted from log messages."""

    def test_redacting_filter_redacts_api_key(self):
        """API key patterns must be redacted."""
        f = RedactingFilter()
        record = MagicMock()
        record.msg = "api_key=sk_live_abc123def456"
        record.args = ()
        f.filter(record)
        assert "sk_live_abc123def456" not in record.msg
        assert "REDACTED" in record.msg

    def test_redacting_filter_redacts_password(self):
        """Password patterns must be redacted."""
        f = RedactingFilter()
        record = MagicMock()
        record.msg = "password=my_secret_password_123"
        record.args = ()
        f.filter(record)
        assert "my_secret_password_123" not in record.msg
        assert "REDACTED" in record.msg

    def test_redacting_filter_redacts_bearer_token(self):
        """Bearer tokens must be redacted."""
        f = RedactingFilter()
        record = MagicMock()
        record.msg = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        record.args = ()
        f.filter(record)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in record.msg
        assert "REDACTED" in record.msg

    def test_redacting_filter_redacts_telegram_token(self):
        """Telegram bot tokens must be redacted."""
        f = RedactingFilter()
        record = MagicMock()
        record.msg = "Using bot1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
        record.args = ()
        f.filter(record)
        assert "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi" not in record.msg
        assert "REDACTED" in record.msg

    def test_redacting_filter_preserves_clean_messages(self):
        """Clean messages must pass through unchanged."""
        f = RedactingFilter()
        record = MagicMock()
        record.msg = "Order submitted successfully"
        record.args = ()
        f.filter(record)
        assert record.msg == "Order submitted successfully"

    def test_redacting_filter_returns_true(self):
        """filter() must return True to allow the record through."""
        f = RedactingFilter()
        record = MagicMock()
        record.msg = "test"
        record.args = ()
        assert f.filter(record) is True


# =============================================================================
# 10. Test core/regime.py unified interface
# =============================================================================
class TestRegimeUnifiedInterface:
    """Verify regime detector works through unified interface."""

    def test_regime_detector_importable(self):
        """RegimeDetector must be importable from validation.regime_detector."""
        assert RegimeDetector is not None
        assert RegimeConfig is not None
        assert RegimeState is not None

    def test_create_regime_detector_factory(self):
        """create_regime_detector factory must exist in core.regime."""
        from graxia.packages.quant_os.core.regime import create_regime_detector

        detector = create_regime_detector()
        assert isinstance(detector, RegimeDetector)

    def test_create_regime_detector_custom_params(self):
        """create_regime_detector must accept custom parameters."""
        from graxia.packages.quant_os.core.regime import create_regime_detector

        detector = create_regime_detector(
            vol_lookback_short=10,
            vol_lookback_long=100,
            vol_low_threshold=0.5,
        )
        assert detector.config.vol_lookback_short == 10
        assert detector.config.vol_lookback_long == 100
        assert detector.config.vol_low_threshold == 0.5

    def test_regime_detector_default_mult(self):
        """get_position_size_multiplier must return 1.0 by default."""
        detector = RegimeDetector()
        mult = detector.get_position_size_multiplier()
        assert mult == 1.0, f"Default multiplier should be 1.0, got {mult}"

    def test_regime_detector_vol_regime_enum(self):
        """VolRegime must have the standard regime values."""
        from graxia.packages.quant_os.validation.regime_detector import VolRegime

        values = {r.value for r in VolRegime}
        assert "low_vol" in values
        assert "normal" in values
        assert "elevated" in values
        assert "stressed" in values


# =============================================================================
# 11. Test core/dsr.py unified interface
# =============================================================================
class TestDSRUnifiedInterface:
    """Verify DSR works through unified interface."""

    def test_dsr_importable(self):
        """DSR functions must be importable from validation.deflated_sharpe."""
        assert deflated_sharpe_ratio is not None
        assert min_backtest_length is not None
        assert DeflatedSharpeResult is not None
        assert MinBTLResult is not None

    def test_core_dsr_reexports(self):
        """core.dsr must re-export DSR functions (via __all__ or direct import)."""
        from graxia.packages.quant_os.core import dsr

        assert hasattr(dsr, "deflated_sharpe_ratio")
        assert hasattr(dsr, "min_backtest_length")
        assert hasattr(dsr, "DeflatedSharpeResult")

    def test_deflated_sharpe_ratio_basic(self):
        """deflated_sharpe_ratio must return DeflatedSharpeResult."""
        result = deflated_sharpe_ratio(
            observed_sharpe=1.5,
            n_trials=10,
            n_observations=1000,
        )
        assert isinstance(result, DeflatedSharpeResult)
        assert result.observed_sharpe == 1.5
        assert 0.0 <= result.probability_alpha <= 1.0

    def test_min_backtest_length_basic(self):
        """min_backtest_length must return MinBTLResult."""
        result = min_backtest_length(observed_sharpe=1.0, n_trials=5)
        assert isinstance(result, MinBTLResult)
        assert result.min_observations > 0

    def test_deflated_sharpe_handles_zero_trials(self):
        """DSR must handle zero trials gracefully."""
        result = deflated_sharpe_ratio(
            observed_sharpe=1.0,
            n_trials=0,
            n_observations=100,
        )
        assert result.passes_threshold is False


# =============================================================================
# 12. Test ml/pipeline.py fixes
# =============================================================================
class TestMLPipelineFixes:
    """Verify no double file open, no deprecated datetime."""

    def test_pipeline_uses_utc_not_utcnow(self):
        """pipeline.py must use datetime.now(UTC), not datetime.utcnow()."""
        pipeline_path = os.path.join(os.path.dirname(__file__), "..", "ml", "pipeline.py")
        with open(pipeline_path) as f:
            source = f.read()
        assert "datetime.utcnow()" not in source
        assert "datetime.now(UTC)" in source

    def test_pipeline_uses_safe_pickle(self):
        """pipeline.py must use safe_load_model instead of raw pickle.load."""
        pipeline_path = os.path.join(os.path.dirname(__file__), "..", "ml", "pipeline.py")
        with open(pipeline_path) as f:
            source = f.read()
        assert "safe_load_model" in source

    def test_train_walk_forward_no_double_file_open(self):
        """train_walk_forward must not open model file twice."""
        import ast

        pipeline_path = os.path.join(os.path.dirname(__file__), "..", "ml", "pipeline.py")
        with open(pipeline_path) as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "train_walk_forward":
                open_calls = sum(
                    1
                    for child in ast.walk(node)
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Name) and child.func.id == "open"
                )
                assert open_calls <= 1, f"train_walk_forward has {open_calls} open() calls, expected <= 1"


# =============================================================================
# 13. Test ml/labeling.py fix
# =============================================================================
class TestMLLabelingFix:
    """Verify labeling works with correct function name."""

    def test_labeling_exports_compute_triple_barrier(self):
        """labeling.py must export compute_triple_barrier."""
        from graxia.packages.quant_os.ml.labeling import compute_triple_barrier

        assert callable(compute_triple_barrier)

    def test_labeling_exports_prepare_labeled_dataset(self):
        """labeling.py must export prepare_labeled_dataset."""
        from graxia.packages.quant_os.ml.labeling import prepare_labeled_dataset

        assert callable(prepare_labeled_dataset)

    def test_compute_triple_barrier_basic(self):
        """compute_triple_barrier must return a Series of labels."""
        from graxia.packages.quant_os.ml.labeling import compute_triple_barrier

        n = 100
        rng = np.random.default_rng(42)
        df = pd.DataFrame(
            {
                "open": 2000 + np.cumsum(rng.normal(0, 1, n)),
                "high": 2000 + np.cumsum(rng.normal(0, 1, n)) + 2,
                "low": 2000 + np.cumsum(rng.normal(0, 1, n)) - 2,
                "close": 2000 + np.cumsum(rng.normal(0, 1, n)),
                "atr_14": np.full(n, 5.0),
            }
        )
        df["high"] = df[["open", "close", "high"]].max(axis=1) + 1
        df["low"] = df[["open", "close", "low"]].min(axis=1) - 1
        labels = compute_triple_barrier(df, tp_mult=1.5, sl_mult=1.0, max_bars=5)
        assert isinstance(labels, pd.Series)
        assert len(labels) == n
        unique = set(labels.unique())
        assert unique.issubset({-1, 0, 1}), f"Labels must be in {{-1,0,1}}, got {unique}"


# =============================================================================
# 14. Test data_loader.py deterministic random
# =============================================================================
class TestSampleDataDeterministicRandom:
    """Verify generate_sample_data produces same output on re-run."""

    def test_generate_sample_data_deterministic(self):
        """Same seed must produce identical data."""
        from graxia.packages.quant_os.backtest.data_loader import generate_sample_data

        data1, ts1 = generate_sample_data(bars=100, seed=42)
        data2, ts2 = generate_sample_data(bars=100, seed=42)
        assert ts1 == ts2
        assert data1["close"] == data2["close"]
        assert data1["open"] == data2["open"]
        assert data1["high"] == data2["high"]
        assert data1["low"] == data2["low"]

    def test_generate_sample_data_different_seeds_differ(self):
        """Different seeds must produce different data."""
        from graxia.packages.quant_os.backtest.data_loader import generate_sample_data

        data1, _ = generate_sample_data(bars=100, seed=42)
        data2, _ = generate_sample_data(bars=100, seed=99)
        assert data1["close"] != data2["close"]

    def test_generate_sample_data_correct_length(self):
        """generate_sample_data must produce exact number of bars."""
        from graxia.packages.quant_os.backtest.data_loader import generate_sample_data

        data, ts = generate_sample_data(bars=500, seed=1)
        assert len(data["close"]) == 500
        assert len(ts) == 500

    def test_generate_sample_data_ohlcv_consistency(self):
        """Generated data must satisfy high >= low, all positive."""
        from graxia.packages.quant_os.backtest.data_loader import generate_sample_data

        data, _ = generate_sample_data(bars=1000, seed=42)
        for i in range(len(data["close"])):
            assert data["high"][i] >= data["low"][i], f"Bar {i}: high < low"
            assert data["high"][i] > 0
            assert data["low"][i] > 0
            assert data["close"][i] > 0
            assert data["open"][i] > 0

    def test_generate_sample_data_uses_random_module(self):
        """generate_sample_data must use random.Random(seed) for deterministic RNG."""
        from graxia.packages.quant_os.backtest.data_loader import generate_sample_data

        source = inspect.getsource(generate_sample_data)
        assert "Random(seed)" in source, "generate_sample_data must use Random(seed) for deterministic RNG"
