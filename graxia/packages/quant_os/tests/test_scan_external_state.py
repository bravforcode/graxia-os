"""C0.3: external-state scanner detects file/live-cache reads in generate_signal."""

from pathlib import Path

from quant_os.scripts.scan_external_state import scan_strategy_file


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "s.py"
    p.write_text(body, encoding="utf-8")
    return p


def test_clean_strategy(tmp_path):
    p = _write(tmp_path, "def generate_signal(self, symbol, ohlcv_data, indicators, current_time):\n    return None\n")
    assert scan_strategy_file(p) == []


def test_file_read_detected(tmp_path):
    p = _write(
        tmp_path,
        "import pathlib\ndef generate_signal(self, symbol, ohlcv_data, indicators, current_time):\n    x = pathlib.Path('f.csv').read_text()\n    return None\n",
    )
    assert len(scan_strategy_file(p)) >= 1


def test_cache_read_detected(tmp_path):
    p = _write(
        tmp_path,
        "def generate_signal(self, symbol, ohlcv_data, indicators, current_time):\n    v = _GLOBAL_CACHE['x']\n    return None\n",
    )
    assert len(scan_strategy_file(p)) >= 1
