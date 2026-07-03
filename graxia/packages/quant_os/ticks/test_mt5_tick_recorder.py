"""Tests for MT5 tick recorder."""

import tempfile
from types import SimpleNamespace

from graxia.packages.quant_os.tick.mt5_tick_recorder import MT5TickRecorder
from graxia.packages.quant_os.tick.tick_storage import TickStorage


def test_recorder_creates():
    with tempfile.TemporaryDirectory() as tmp:
        storage = TickStorage(tmp)
        recorder = MT5TickRecorder(storage, "XAUUSD")
        assert recorder.get_sequence() == 0
        assert not recorder.is_recording()


def test_recorder_start_stop():
    with tempfile.TemporaryDirectory() as tmp:
        storage = TickStorage(tmp)
        recorder = MT5TickRecorder(storage)
        recorder.start()
        assert recorder.is_recording()
        recorder.stop()
        assert not recorder.is_recording()


def test_recorder_records_tick():
    with tempfile.TemporaryDirectory() as tmp:
        storage = TickStorage(tmp)
        recorder = MT5TickRecorder(storage, "XAUUSD")
        recorder.start()

        mt5_tick = SimpleNamespace(
            time=1719052800,  # 2024-06-22
            time_msc=1719052800000,
            bid=2350.50,
            ask=2350.80,
            last=0.0,
            flags=2,
            volume=1.0,
            volume_real=1.0,
        )

        tick = recorder.record_tick(mt5_tick)
        assert tick["bid"] == 2350.50
        assert tick["ask"] == 2350.80
        assert tick["symbol"] == "XAUUSD"
        assert recorder.get_sequence() == 1


def test_recorder_skips_when_not_recording():
    with tempfile.TemporaryDirectory() as tmp:
        storage = TickStorage(tmp)
        recorder = MT5TickRecorder(storage, "XAUUSD")
        # Not started
        tick = recorder.record_tick(
            SimpleNamespace(time=0, time_msc=0, bid=100, ask=101, last=0, flags=0, volume=0, volume_real=0)
        )
        assert tick == {}
        assert recorder.get_sequence() == 0
