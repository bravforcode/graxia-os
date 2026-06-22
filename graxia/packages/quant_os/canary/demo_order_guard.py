"""Phase BE-P9 — Demo order guard. Idempotency + SL/TP verification."""
from dataclasses import dataclass
import hashlib


@dataclass
class OrderIntent:
    signal_id: str
    symbol: str
    side: str  # BUY, SELL
    volume: float
    entry_price: float
    stop_loss: float
    take_profit: float = 0.0
    time_stop_minutes: int = 0
    idempotency_key: str = ""
    
    def __post_init__(self):
        if not self.idempotency_key:
            self.idempotency_key = hashlib.sha256(
                f"{self.signal_id}:{self.symbol}:{self.side}".encode()
            ).hexdigest()[:16]


class DemoOrderGuard:
    """Guard against duplicate submissions and missing SL."""
    
    def __init__(self):
        self._submitted_keys: set[str] = set()
    
    def check_idempotency(self, intent: OrderIntent) -> tuple[bool, str]:
        """Check if order already submitted."""
        if intent.idempotency_key in self._submitted_keys:
            return False, f"duplicate: {intent.idempotency_key}"
        return True, "OK"
    
    def check_stop_loss(self, intent: OrderIntent) -> tuple[bool, str]:
        """Check SL is present and valid."""
        if intent.stop_loss <= 0:
            return False, "missing_stop_loss"
        
        if intent.side == "BUY" and intent.stop_loss >= intent.entry_price:
            return False, "invalid_sl_buy"
        
        if intent.side == "SELL" and intent.stop_loss <= intent.entry_price:
            return False, "invalid_sl_sell"
        
        return True, "OK"
    
    def check_take_profit(self, intent: OrderIntent) -> tuple[bool, str]:
        """Check TP or time stop is present."""
        if intent.take_profit <= 0 and intent.time_stop_minutes <= 0:
            return False, "missing_tp_or_time_stop"
        return True, "OK"
    
    def preflight(self, intent: OrderIntent) -> tuple[bool, list[str]]:
        """Run all preflight checks."""
        issues = []
        
        ok, msg = self.check_idempotency(intent)
        if not ok:
            issues.append(msg)
        
        ok, msg = self.check_stop_loss(intent)
        if not ok:
            issues.append(msg)
        
        ok, msg = self.check_take_profit(intent)
        if not ok:
            issues.append(msg)
        
        return len(issues) == 0, issues
    
    def mark_submitted(self, intent: OrderIntent) -> None:
        """Mark order as submitted."""
        self._submitted_keys.add(intent.idempotency_key)
    
    def is_submitted(self, key: str) -> bool:
        return key in self._submitted_keys
