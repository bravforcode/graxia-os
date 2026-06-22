"""Phase BE-P8 — Shadow pipeline runner. No order submission."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json


@dataclass
class ShadowSignal:
    signal_id: str = ""
    symbol: str = ""
    direction: str = ""
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    timestamp_utc: str = ""
    rejection_reason: str = ""
    event_blocked: bool = False
    health_blocked: bool = False
    hypothetical_pnl: float = 0.0
    cost_estimate: float = 0.0


@dataclass
class ShadowLedgerEntry:
    entry_index: int = 0
    previous_hash: str = ""
    record_hash: str = ""
    signal: ShadowSignal = None
    fill_price: float = 0.0
    exit_price: float = 0.0
    pnl_after_costs: float = 0.0
    
    def compute_hash(self) -> str:
        d = {
            "entry_index": self.entry_index,
            "previous_hash": self.previous_hash,
            "signal_id": self.signal.signal_id if self.signal else "",
            "fill_price": self.fill_price,
            "exit_price": self.exit_price,
            "pnl_after_costs": self.pnl_after_costs,
        }
        return hashlib.sha256(
            json.dumps(d, sort_keys=True, default=str).encode()
        ).hexdigest()


class ShadowPipeline:
    """Shadow pipeline: tick → signal → hypothetical fill → ledger. No broker submission."""
    
    def __init__(self):
        self._signals: list[ShadowSignal] = []
        self._ledger: list[ShadowLedgerEntry] = []
        self._sequence: int = 0
        self._session_start: str = ""
        self._incidents: list[dict] = []
        self._heartbeat_count: int = 0
    
    def start_session(self, session_id: str) -> None:
        self._session_start = datetime.now(timezone.utc).isoformat()
        self._sequence = 0
        self._signals = []
        self._ledger = []
        self._incidents = []
        self._heartbeat_count = 0
    
    def process_tick(self, tick: dict) -> ShadowSignal | None:
        """Process tick through shadow pipeline. Returns signal if eligible."""
        self._heartbeat_count += 1
        
        # Check health (simplified)
        if tick.get("bid", 0) <= 0 or tick.get("ask", 0) <= 0:
            self._record_incident("invalid_tick", "bid/ask <= 0")
            return None
        
        # Generate hypothetical signal (simplified strategy)
        signal = ShadowSignal(
            signal_id=f"SHADOW_{self._sequence:06d}",
            symbol=tick.get("symbol", ""),
            direction="BUY" if tick.get("bid", 0) < tick.get("ask", 0) else "SELL",
            entry_price=tick.get("bid", 0),
            stop_loss=tick.get("bid", 0) - 2.0,
            take_profit=tick.get("bid", 0) + 4.0,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
        )
        
        self._signals.append(signal)
        self._sequence += 1
        
        # Add to ledger (hypothetical fill at bid)
        entry = ShadowLedgerEntry(
            entry_index=self._sequence,
            previous_hash=self._ledger[-1].record_hash if self._ledger else "",
            signal=signal,
            fill_price=tick.get("bid", 0),
        )
        entry.record_hash = entry.compute_hash()
        self._ledger.append(entry)
        
        return signal
    
    def _record_incident(self, incident_type: str, detail: str) -> None:
        self._incidents.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": incident_type,
            "detail": detail,
        })
    
    def get_signals(self) -> list[ShadowSignal]:
        return self._signals.copy()
    
    def get_ledger(self) -> list[ShadowLedgerEntry]:
        return self._ledger.copy()
    
    def get_incidents(self) -> list[dict]:
        return self._incidents.copy()
    
    def get_heartbeat_count(self) -> int:
        return self._heartbeat_count
    
    def seal_ledger(self) -> str:
        """Compute ledger seal hash."""
        if not self._ledger:
            return ""
        return self._ledger[-1].record_hash
    
    def verify_ledger_integrity(self) -> bool:
        """Verify append-only hash chain."""
        for i, entry in enumerate(self._ledger):
            if i > 0 and entry.previous_hash != self._ledger[i-1].record_hash:
                return False
            if entry.record_hash != entry.compute_hash():
                return False
        return True
    
    def get_summary(self) -> dict:
        return {
            "session_start": self._session_start,
            "signals_generated": len(self._signals),
            "ledger_entries": len(self._ledger),
            "incidents": len(self._incidents),
            "heartbeat_count": self._heartbeat_count,
            "ledger_seal": self.seal_ledger(),
            "ledger_valid": self.verify_ledger_integrity(),
        }
