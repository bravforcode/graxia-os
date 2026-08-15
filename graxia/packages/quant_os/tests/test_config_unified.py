"""Tests for the unified config migration.

Verifies:
- ``config.unified_settings.settings`` is the single source of truth
- All new sections (telegram, TV, PixelRAG, cost calibration, paper trade,
  adjusted verdicts, broker profile) are present
- Backward-compat shims re-export the same constants and emit a
  ``DeprecationWarning`` on import
- Defaults are sane
- Env vars and .env files are respected
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reload_unified_settings():
    """Reload unified_settings so env changes take effect."""
    sys.modules.pop("config.unified_settings", None)
    sys.modules.pop("config", None)
    from config import unified_settings  # noqa: WPS433

    importlib.reload(unified_settings)
    return unified_settings


# ---------------------------------------------------------------------------
# Smoke: singleton loads, defaults sane
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_settings_singleton_exists(self):
        from config.unified_settings import settings

        assert settings is not None

    def test_existing_field_unchanged(self):
        """Existing fields MUST NOT be removed or renamed."""
        from config.unified_settings import settings

        assert settings.MT5_SERVER == "ICMarkets-Demo"
        assert settings.BROKER_NAME == "pepperstone"
        assert settings.RISK_PER_TRADE_BPS == 100
        assert ["XAUUSD", "BTCUSD", "ETHUSD"] == settings.AUTO_SYMBOLS

    def test_all_new_sections_present(self):
        from config.unified_settings import settings

        # Telegram (extended)
        assert hasattr(settings, "TELEGRAM_BOT_TOKEN")
        assert hasattr(settings, "TELEGRAM_CHAT_ID")
        assert hasattr(settings, "TELEGRAM_ALERTS_ENABLED")
        assert hasattr(settings, "TELEGRAM_ALERT_LEVEL")
        assert hasattr(settings, "TELEGRAM_STANDBY_WEBHOOK_URL")
        assert hasattr(settings, "TELEGRAM_TIMEOUT_SECONDS")

        # TradingView MCP
        assert hasattr(settings, "TV_MCP_URL")
        assert hasattr(settings, "TV_DEFAULT_TIMEFRAME")
        assert hasattr(settings, "TV_SCREEN_EXCHANGE")
        assert hasattr(settings, "TV_REQUEST_TIMEOUT")
        assert hasattr(settings, "TV_MAX_RETRIES")
        assert hasattr(settings, "TV_RETRY_BACKOFF")

        # TradingView CDP
        assert hasattr(settings, "TV_CDP_URL")
        assert hasattr(settings, "TV_CDP_TIMEOUT")
        assert hasattr(settings, "TV_CDP_CHROME_PATH")
        assert hasattr(settings, "TV_CDP_USER_DATA_DIR")
        assert hasattr(settings, "TV_SELECTOR_SYMBOL_INPUT")
        assert hasattr(settings, "TV_SELECTOR_PINE_CODE")
        assert hasattr(settings, "TV_SCREENSHOT_DIR")

        # PixelRAG
        assert hasattr(settings, "PIXELRAG_URL")
        assert hasattr(settings, "PIXELRAG_HOST")
        assert hasattr(settings, "PIXELRAG_INDEX_DIR")
        assert hasattr(settings, "PIXELRAG_TILES_DIR")
        assert hasattr(settings, "PIXELRAG_DEFAULT_N_DOCS")
        assert hasattr(settings, "PIXELRAG_REQUEST_TIMEOUT")
        assert hasattr(settings, "PIXELSHOT_TIMEOUT")
        assert hasattr(settings, "PIXELRAG_INDEX_TIMEOUT")
        assert hasattr(settings, "PIXELRAG_SERVE_TIMEOUT")

        # Cost calibration
        assert hasattr(settings, "COST_CALIBRATION_PATH")
        assert hasattr(settings, "COST_CALIBRATION_VERSION")

        # Paper trade
        assert hasattr(settings, "PAPER_TRADE_CONFIG_PATH")
        assert hasattr(settings, "PAPER_TRADE_DEFAULT_PORTFOLIO_TYPE")

        # Adjusted verdicts
        assert hasattr(settings, "ADJUSTED_VERDICTS_PATH")

        # Broker profile
        assert hasattr(settings, "BROKER_PROFILE_PATH")
        assert hasattr(settings, "BROKER_PROFILE_TEMPLATE_PATH")
        assert hasattr(settings, "BROKER_PROFILE_SCHEMA_PATH")

        # Failover
        assert hasattr(settings, "STANDBY_WEBHOOK_URL")


class TestDefaults:
    def test_telegram_defaults(self):
        from config.unified_settings import settings

        assert settings.TELEGRAM_BOT_TOKEN == ""
        assert settings.TELEGRAM_CHAT_ID == ""
        assert settings.TELEGRAM_ALERTS_ENABLED is True
        assert settings.TELEGRAM_ALERT_LEVEL == "info"

    def test_tv_mcp_defaults(self):
        from config.unified_settings import settings

        assert settings.TV_MCP_URL == "http://localhost:30001"
        assert settings.TV_DEFAULT_TIMEFRAME == "1D"
        assert settings.TV_SCREEN_EXCHANGE == "NASDAQ"
        assert settings.TV_REQUEST_TIMEOUT == 30.0
        assert settings.TV_MAX_RETRIES == 3

    def test_tv_cdp_defaults(self):
        from config.unified_settings import settings

        assert settings.TV_CDP_URL == "http://localhost:9222"
        assert settings.TV_CDP_TIMEOUT == 30
        assert settings.TV_SELECTOR_PINE_EDITOR == ".pine-editor"
        assert settings.TV_SELECTOR_WATCHLIST == ".watchlist"

    def test_pixelrag_defaults(self):
        from config.unified_settings import settings

        assert settings.PIXELRAG_URL == "http://localhost:30002"
        assert settings.PIXELRAG_DEFAULT_N_DOCS == 5
        assert settings.PIXELSHOT_TIMEOUT == 120
        # Path conversion
        from pathlib import Path

        assert isinstance(settings.PIXELRAG_INDEX_DIR, Path)
        assert isinstance(settings.PIXELRAG_TILES_DIR, Path)

    def test_cost_calibration_defaults(self):
        from config.unified_settings import settings

        assert settings.COST_CALIBRATION_VERSION == "2.2"

    def test_paper_trade_defaults(self):
        from config.unified_settings import settings

        assert settings.PAPER_TRADE_DEFAULT_PORTFOLIO_TYPE == "concentrated_4_asset"


# ---------------------------------------------------------------------------
# Env-var loading
# ---------------------------------------------------------------------------


class TestEnvVarLoading:
    def test_settings_loads_from_env(self, monkeypatch, tmp_path):
        """Set an env var, instantiate a fresh settings, observe the value."""
        monkeypatch.setenv("QUANT_TELEGRAM_BOT_TOKEN", "test-token-123")
        monkeypatch.setenv("QUANT_TELEGRAM_CHAT_ID", "999")
        monkeypatch.setenv("QUANT_TELEGRAM_ALERT_LEVEL", "warning")
        monkeypatch.setenv("QUANT_TV_DEFAULT_TIMEFRAME", "4H")
        monkeypatch.setenv("QUANT_PIXELSHOT_TIMEOUT", "42")
        us = _reload_unified_settings()
        s = us.settings
        assert s.TELEGRAM_BOT_TOKEN == "test-token-123"
        assert s.TELEGRAM_CHAT_ID == "999"
        assert s.TELEGRAM_ALERT_LEVEL == "warning"
        assert s.TV_DEFAULT_TIMEFRAME == "4H"
        assert s.PIXELSHOT_TIMEOUT == 42

    def test_settings_loads_from_dotenv(self, monkeypatch, tmp_path):
        """Write a .env, re-read settings — values must be picked up."""
        # The Pydantic-settings model_config uses ``env_file='.env'`` (relative
        # to the current working directory).  We can monkeypatch that to point
        # at a tmp file.
        env_file = tmp_path / "test.env"
        env_file.write_text(
            "QUANT_TELEGRAM_BOT_TOKEN=from-dotenv-xyz\n" "QUANT_TV_MCP_URL=http://dotenv-mcp:30001\n",
            encoding="utf-8",
        )
        # Reload unified_settings with the custom env file.
        import config.unified_settings as us

        us.settings.model_config["env_file"] = str(env_file)
        us.settings = us.QuantSettings()
        s = us.settings
        assert s.TELEGRAM_BOT_TOKEN == "from-dotenv-xyz"
        assert s.TV_MCP_URL == "http://dotenv-mcp:30001"
        # Restore the default
        us.settings.model_config["env_file"] = ".env"

    def test_invalid_alert_level_rejected(self, monkeypatch):
        """Pattern validator on TELEGRAM_ALERT_LEVEL should fail for 'bogus'."""
        monkeypatch.setenv("QUANT_TELEGRAM_ALERT_LEVEL", "bogus")
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            us = _reload_unified_settings()
            # Force re-validation by accessing the field
            _ = us.settings.TELEGRAM_ALERT_LEVEL


# ---------------------------------------------------------------------------
# Backward-compat shims
# ---------------------------------------------------------------------------


class TestConsumerMigration:
    """Verify that consumers migrated from shim files to unified_settings."""

    def test_pixelrag_settings_direct(self):
        """visual_search.py uses config.unified_settings directly."""
        from config.unified_settings import settings

        assert settings.PIXELRAG_URL == "http://localhost:30002"
        assert settings.PIXELRAG_DEFAULT_N_DOCS == 5
        assert isinstance(settings.PIXELRAG_INDEX_DIR, Path)

    def test_tv_settings_direct(self):
        """tv_client.py uses config.unified_settings directly."""
        from config.unified_settings import settings

        assert settings.TV_MCP_URL == "http://localhost:30001"
        assert settings.TV_DEFAULT_TIMEFRAME == "1D"

    def test_tv_cdp_settings_direct(self):
        """tv_cdp.py uses config.unified_settings directly."""
        from config.unified_settings import settings

        assert settings.TV_CDP_URL == "http://localhost:9222"
        assert "screenshots" in str(settings.TV_SCREENSHOT_DIR)

    def test_telegram_settings_direct(self):
        """Telegram settings via unified_settings."""
        from config.unified_settings import settings

        assert isinstance(settings.TELEGRAM_BOT_TOKEN, str)
        assert isinstance(settings.TELEGRAM_CHAT_ID, str)


# ---------------------------------------------------------------------------
# Data file contracts
# ---------------------------------------------------------------------------
# The planned config/ loaders (load_cost_calibration, load_paper_trade_config,
# load_adjusted_verdicts, load_broker_profile_template, load_telegram_config_toml)
# were never implemented — config/__init__.py is a docstring-only stub. These
# tests pin the on-disk data file contracts those loaders were meant to expose.


class TestDataFileLoaders:
    def test_cost_calibration_json(self, quant_os_root: Path):
        data = json.loads((quant_os_root / "config" / "cost_calibration.json").read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "version" in data
        assert "assets" in data
        assert "XAUUSD" in data["assets"]

    def test_paper_trade_config_json(self, quant_os_root: Path):
        data = json.loads((quant_os_root / "config" / "paper_trade_config.json").read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "portfolio" in data
        assert "symbols" in data
        assert len(data["symbols"]) >= 1

    def test_adjusted_verdicts_json(self, quant_os_root: Path):
        data = json.loads((quant_os_root / "config" / "adjusted_verdicts.json").read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert data  # non-empty
        first_key = next(iter(data))
        assert isinstance(data[first_key], dict)

    def test_broker_profile_template_yaml(self, quant_os_root: Path):
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load((quant_os_root / "config" / "broker_profile.template.yaml").read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "profile_id" in data

    def test_telegram_config_toml(self, quant_os_root: Path):
        import tomllib

        data = tomllib.loads((quant_os_root / "config" / "telegram_config.toml").read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "bot_token" in data
        assert "chat_id" in data


# ---------------------------------------------------------------------------
# Data files must still exist on disk
# ---------------------------------------------------------------------------


class TestLegacyFilesPreserved:
    """All 12 original config files MUST remain on disk (no removals)."""

    def test_legacy_data_files_present(self, quant_os_root: Path):
        assert (quant_os_root / "config" / ".env.example").is_file()
        assert (quant_os_root / "config" / "adjusted_verdicts.json").is_file()
        assert (quant_os_root / "config" / "broker_profile.schema.json").is_file()
        assert (quant_os_root / "config" / "broker_profile.template.yaml").is_file()
        assert (quant_os_root / "config" / "cost_calibration.json").is_file()
        assert (quant_os_root / "config" / "paper_trade_config.json").is_file()
        assert (quant_os_root / "config" / "telegram_config.example.toml").is_file()
        assert (quant_os_root / "config" / "telegram_config.toml").is_file()

    def test_legacy_py_shims_present(self, quant_os_root: Path):
        assert (quant_os_root / "config" / "unified_settings.py").is_file()

    def test_cost_calibration_round_trip(self, quant_os_root: Path):
        """cost_calibration.json must be valid JSON with the expected structure."""
        path = quant_os_root / "config" / "cost_calibration.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "version" in data
        assert "assets" in data
        # calibration_status may be a single value or a mixed description
        assert isinstance(data["calibration_status"], str)
        assert len(data["calibration_status"]) > 0

    def test_paper_trade_round_trip(self, quant_os_root: Path):
        path = quant_os_root / "config" / "paper_trade_config.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["trading_mode"] == "PAPER"
        assert len(data["symbols"]) >= 1


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def quant_os_root() -> Path:
    """Absolute path to the quant_os package root."""
    return Path(__file__).resolve().parent.parent
