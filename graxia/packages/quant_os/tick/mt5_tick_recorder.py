"""Phase BE-P2 — MT5 tick recorder. READ-ONLY observation."""
import time
from datetime import datetime, timezone
from pathlib import Path


class MT5TickRecorder:
    """Records ticks from MT5 terminal. No order submission."""
    
    def __init__(self, storage, symbol: str = "XAUUSD"):
        self._storage = storage
        self._symbol = symbol
        self._sequence = 0
        self._recording = False
    
    def start(self) -> None:
        """Start recording."""
        self._recording = True
    
    def stop(self) -> None:
        """Stop recording."""
        self._recording = False
    
    def record_tick(self, mt5_tick) -> dict:
        """Record a single MT5 tick object."""
        if not self._recording:
            return {}
        
        self._sequence += 1
        
        # Extract from MT5 tick object
        tick = {
            "tick_id": self._sequence,
            "ingest_sequence": self._sequence,
            "source_timestamp_utc": datetime.fromtimestamp(
                mt5_tick.time, tz=timezone.utc
            ).isoformat(),
            "source_time_msc": mt5_tick.time_msc,
            "received_at_utc": datetime.now(timezone.utc).isoformat(),
            "received_monotonic_ns": time.monotonic_ns(),
            "broker": "mt5",
            "server_fingerprint": "",
            "account_mode": "DEMO",
            "symbol": self._symbol,
            "bid": mt5_tick.bid,
            "ask": mt5_tick.ask,
            "last": getattr(mt5_tick, "last", 0.0),
            "spread_price": mt5_tick.ask - mt5_tick.bid if mt5_tick.ask > 0 and mt5_tick.bid > 0 else 0,
            "spread_points": 0,
            "flags": mt5_tick.flags,
            "volume": getattr(mt5_tick, "volume", 0.0),
            "volume_real": getattr(mt5_tick, "volume_real", 0.0),
            "session_id": "",
            "contract_snapshot_id": "",
            "raw_payload_hash": "",
            "partition_hash": "",
        }
        
        # Store
        self._storage.store_tick(
            tick, "mt5", "metaquotes", self._symbol
        )
        
        return tick
    
    def get_sequence(self) -> int:
        return self._sequence
    
    def is_recording(self) -> bool:
        return self._recording
