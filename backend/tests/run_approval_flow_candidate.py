"""Run approval contracts without dotenv reads, network, bytecode, or pytest cache."""
import faulthandler
import ipaddress
import os
import socket
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

from pydantic_settings.sources import DotEnvSettingsSource
import pytest

original_connect = socket.socket.connect

def local_connect(sock, address):
    # Windows asyncio creates its self-pipe with a loopback socketpair.
    if isinstance(address, tuple) and ipaddress.ip_address(address[0]).is_loopback:
        return original_connect(sock, address)
    raise RuntimeError("candidate_network_disabled")

if __name__ == "__main__":
    faulthandler.dump_traceback_later(90, exit=True)
    with patch.object(DotEnvSettingsSource, "_read_env_files", return_value={}), patch.object(
        socket.socket, "connect", new=local_connect
    ), patch.object(
        socket.socket, "connect_ex", side_effect=RuntimeError("candidate_network_disabled")
    ):
        raise SystemExit(pytest.main([
            "-p", "no:cacheprovider", "-p", "pytest_asyncio.plugin",
            "tests/test_approval_flow_contracts.py", "-q", *sys.argv[1:]
        ]))
