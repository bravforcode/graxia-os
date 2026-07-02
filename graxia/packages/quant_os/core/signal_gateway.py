"""
Signal Gateway — production signal ingestion, validation, deduplication, and audit.

Handles raw signal payloads from multiple sources (TradingView, EAs, Python, ML),
validates them via Pydantic, deduplicates within a 5-second window, appends to an
immutable audit log, and pushes accepted signals onto an asyncio.Queue for downstream
consumers (EventBus, risk engine, execution layer).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

import structlog
from pydantic import BaseModel, Field, field_validator

from .news_blackout import NewsBlackout
from .session_filter import SessionFilter
from .session_manager import AssetClass

AUDIT_LOG_PATH = Path(__file__).resolve().parent.parent / "state" / "audit_log.jsonl"
DEDUP_WINDOW_SECONDS = 5.0

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class SignalSource(str, Enum):
    TRADINGVIEW = "tradingview"
    EA = "ea"
    PYTHON = "python"
    ML = "ml"


# ---------------------------------------------------------------------------
# Domain model (frozen dataclass)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Signal:
    """Immutable trading signal with deterministic ID generation."""

    symbol: str
    asset_class: AssetClass
    side: Side
    conviction: float
    strategy: str
    entry_price: float
    stop_loss: float
    take_profit: float
    timestamp: datetime
    source: SignalSource
    regime: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def signal_id(self) -> str:
        """Deterministic 16-char hex ID derived from core signal fields."""
        raw = f"{self.symbol}:{self.side.value}:{self.strategy}:{self.timestamp.strftime('%Y%m%d%H%M')}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "signal_id": self.signal_id,
            "symbol": self.symbol,
            "asset_class": self.asset_class.value,
            "side": self.side.value,
            "conviction": self.conviction,
            "strategy": self.strategy,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source.value,
            "regime": self.regime,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Pydantic validation schema
# ---------------------------------------------------------------------------


class RawSignalPayload(BaseModel):
    """Pydantic model for incoming raw signal dicts before domain mapping."""

    symbol: str = Field(..., min_length=1, max_length=20)
    asset_class: str = Field(...)
    side: str = Field(...)
    conviction: float = Field(..., ge=0.0, le=1.0)
    strategy: str = Field(..., min_length=1, max_length=100)
    entry_price: float = Field(..., gt=0)
    stop_loss: float = Field(..., gt=0)
    take_profit: float = Field(..., gt=0)
    timestamp: Optional[str] = None
    regime: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("asset_class")
    @classmethod
    def validate_asset_class(cls, v: str) -> str:
        allowed = {e.value for e in AssetClass}
        if v.lower() not in allowed:
            raise ValueError(f"asset_class must be one of {allowed}, got '{v}'")
        return v.lower()

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        allowed = {e.value for e in Side}
        if v.upper() not in allowed:
            raise ValueError(f"side must be one of {allowed}, got '{v}'")
        return v.upper()

    @field_validator("stop_loss", "take_profit")
    @classmethod
    def validate_levels_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("stop_loss and take_profit must be > 0")
        return v


# ---------------------------------------------------------------------------
# Audit logger
# ---------------------------------------------------------------------------


def _append_audit(record: Dict[str, Any]) -> None:
    """Append a single JSON line to the immutable audit log."""
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


# ---------------------------------------------------------------------------
# Signal Gateway
# ---------------------------------------------------------------------------


class SignalGateway:
    """
    Production signal gateway.

    Responsibilities:
    - Validate raw payloads via Pydantic.
    - Map validated dicts to frozen Signal dataclass instances.
    - Deduplicate signals within a configurable time window.
    - Append accepted/rejected/deduped events to audit log.
    - Push accepted signals onto an asyncio.Queue for downstream consumers.
    """

    def __init__(
        self,
        queue: asyncio.Queue[Signal],
        dedup_window: float = DEDUP_WINDOW_SECONDS,
        news_blackout: NewsBlackout | None = None,
        session_filter: SessionFilter | None = None,
    ) -> None:
        self._queue = queue
        self._dedup_window = dedup_window
        self._seen: Dict[str, float] = {}  # signal_id → monotonic timestamp
        self._lock = asyncio.Lock()
        self._news_blackout = news_blackout or NewsBlackout()
        self._session_filter = session_filter

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ingest(
        self, raw: Dict[str, Any], source: SignalSource | str
    ) -> Optional[Signal]:
        """
        Ingest a raw signal dict.

        Returns the accepted Signal, or None if rejected/deduped.
        Accepted signals are pushed onto the internal asyncio.Queue.
        """
        if isinstance(source, str):
            source = SignalSource(source)

        # 1. Validate payload
        try:
            validated = RawSignalPayload(**raw)
        except Exception as exc:
            logger.warning("signal.rejected", reason="validation_error", error=str(exc), raw=raw)
            _append_audit(
                {
                    "event": "signal.rejected",
                    "reason": "validation_error",
                    "error": str(exc),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            return None

        # 2. Build domain signal
        ts = (
            datetime.fromisoformat(validated.timestamp)
            if validated.timestamp
            else datetime.now(UTC)
        )
        signal = Signal(
            symbol=validated.symbol,
            asset_class=AssetClass(validated.asset_class),
            side=Side(validated.side),
            conviction=validated.conviction,
            strategy=validated.strategy,
            entry_price=validated.entry_price,
            stop_loss=validated.stop_loss,
            take_profit=validated.take_profit,
            timestamp=ts,
            source=source,
            regime=validated.regime,
            metadata=validated.metadata,
        )

        # 2b. News blackout gate
        if self._news_blackout.is_blocked():
            remaining = self._news_blackout.remaining_seconds()
            logger.info(
                "signal.blocked_by_news",
                signal_id=signal.signal_id,
                symbol=signal.symbol,
                side=signal.side.value,
                remaining_seconds=round(remaining),
            )
            _append_audit(
                {
                    "event": "signal.blocked_by_news",
                    "signal_id": signal.signal_id,
                    "symbol": signal.symbol,
                    "side": signal.side.value,
                    "remaining_seconds": round(remaining),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            return None

        # 2c. Session filter gate
        if self._session_filter is not None:
            sf = SessionFilter(now=ts)
            if not sf.is_active():
                logger.info(
                    "signal.blocked_by_session",
                    signal_id=signal.signal_id,
                    symbol=signal.symbol,
                    side=signal.side.value,
                    session=sf.current_session.value,
                )
                _append_audit(
                    {
                        "event": "signal.blocked_by_session",
                        "signal_id": signal.signal_id,
                        "symbol": signal.symbol,
                        "side": signal.side.value,
                        "session": sf.current_session.value,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
                return None

        # 3. Deduplication
        async with self._lock:
            now = asyncio.get_event_loop().time()
            self._evict_expired(now)

            sid = signal.signal_id
            if sid in self._seen:
                logger.info("signal.deduped", signal_id=sid, symbol=signal.symbol)
                _append_audit(
                    {
                        "event": "signal.deduped",
                        "signal_id": sid,
                        "symbol": signal.symbol,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
                return None

            self._seen[sid] = now

        # 4. Accept
        logger.info(
            "signal.accepted",
            signal_id=sid,
            symbol=signal.symbol,
            side=signal.side.value,
            strategy=signal.strategy,
            source=source.value,
        )
        _append_audit(
            {
                "event": "signal.accepted",
                **signal.to_dict(),
            }
        )

        # 5. Push to queue
        await self._queue.put(signal)
        return signal

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _evict_expired(self, now: float) -> None:
        """Remove entries older than dedup window."""
        expired = [sid for sid, ts in self._seen.items() if now - ts > self._dedup_window]
        for sid in expired:
            del self._seen[sid]
