import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from graxia.packages.quant_os.core.config import QuantConfig, reset_config
from graxia.packages.quant_os.execution.broker_adapter import MT5BrokerAdapter


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


def test_mt5_config_template_has_no_credential_keys() -> None:
    template_path = Path(__file__).resolve().parents[1] / "mt5_connector" / "config_template.yaml"
    content = template_path.read_text(encoding="utf-8")

    assert "login:" not in content
    assert "password:" not in content
    assert "server:" not in content
