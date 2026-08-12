"""Tests for tick logger."""
import tempfile
from graxia.packages.quant_os.tick.tick_logger import TickLogger


def test_logger_creates():
    logger = TickLogger()
    assert logger.get_entries() == []


def test_logger_records():
    logger = TickLogger()
    logger.log_tick_received("XAUUSD", 2350.50, 2350.80, 1000)
    logger.log_quality_incident("invalid_bid", 1, "bid=-1")
    logger.log_gate_transition("CLEAR", "PRE_BLOCK", "NFP")
    entries = logger.get_entries()
    assert len(entries) == 3


def test_logger_flush():
    logger = TickLogger()
    logger.log_tick_received("XAUUSD", 2350.50, 2350.80, 1000)
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        logger.flush(f.name)
        lines = f.read().decode().strip().splitlines()
        assert len(lines) == 1
