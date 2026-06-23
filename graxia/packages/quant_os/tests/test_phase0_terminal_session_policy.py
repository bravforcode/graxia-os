import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from graxia.packages.quant_os.core.config import (
    QuantConfig,
    reject_broker_credential_config,
    reset_config,
)
from graxia.packages.quant_os.execution.broker_adapter import MT5BrokerAdapter
from graxia.packages.quant_os.mt5_connector.shadow_runner import ShadowRunnerV2
from graxia.packages.quant_os.mt5_connector.terminal_session_policy import (
    load_terminal_session_config,
)


@pytest.mark.parametrize("env_key, env_value", [
    ("MT5_LOGIN", "12345678"),
    ("MT5_PASSWORD", "secret123"),
    ("MT5_SERVER", "Pepperstone-Demo"),
])
def test_quant_config_rejects_broker_credential_env(monkeypatch, env_key: str, env_value: str) -> None:
    monkeypatch.setenv(env_key, env_value)

    with pytest.raises(ValueError, match="terminal-session-only MT5 authentication"):
        QuantConfig()

    monkeypatch.delenv(env_key, raising=False)
    reset_config()


def test_mt5_broker_adapter_initializes_without_broker_credentials(monkeypatch) -> None:
    initialize_calls: list[dict] = []

    def fake_initialize(**kwargs):
        initialize_calls.append(kwargs)
        return True

    fake_mt5 = SimpleNamespace(
        initialize=fake_initialize,
        account_info=lambda: object(),
        shutdown=lambda: None,
    )

    for env_key in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER"):
        monkeypatch.delenv(env_key, raising=False)

    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)
    reset_config()
    adapter = MT5BrokerAdapter()

    assert asyncio.run(adapter.connect()) is True
    assert initialize_calls == [{
        "path": adapter.config.mt5_path,
        "timeout": adapter.config.mt5_timeout_ms,
    }]

    asyncio.run(adapter.disconnect())
    reset_config()


def test_quant_config_rejects_nested_broker_credential_config_without_echoing_value() -> None:
    with pytest.raises(ValueError, match="mt5.login") as exc_info:
        reject_broker_credential_config({"mt5": {"login": "12345678"}}, context="test config")

    assert "12345678" not in str(exc_info.value)


def test_terminal_session_config_loader_rejects_credential_keys_without_echoing_value(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "mt5:\n"
        "  path: C:\\\\Program Files\\\\MetaTrader 5\\\\terminal64.exe\n"
        "  timeout: 10000\n"
        "  login: 12345678\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="mt5.login") as exc_info:
        load_terminal_session_config(str(config_path))

    assert "12345678" not in str(exc_info.value)


def test_shadow_runner_connect_logs_redacted_identity(tmp_path: Path, caplog) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "mt5:\n"
        "  path: C:\\\\Program Files\\\\MetaTrader 5\\\\terminal64.exe\n"
        "  timeout: 10000\n",
        encoding="utf-8",
    )
    runner = ShadowRunnerV2(config_path=str(config_path))
    runner._mt5 = SimpleNamespace(
        connect=lambda **_: True,
        get_account_info=lambda: SimpleNamespace(
            login=12345678,
            server="Pepperstone-Demo",
            balance=10000.0,
        ),
        disconnect=lambda: None,
    )

    with caplog.at_level("INFO"):
        assert runner.connect() is True

    assert "login_sha256=" in caplog.text
    assert "server_sha256=" in caplog.text
    assert "12345678" not in caplog.text
    assert "Pepperstone-Demo" not in caplog.text


def test_mt5_config_template_has_no_credential_keys() -> None:
    template_path = Path(__file__).resolve().parents[1] / "mt5_connector" / "config_template.yaml"
    content = template_path.read_text(encoding="utf-8")

    assert "login:" not in content
    assert "password:" not in content
    assert "server:" not in content
