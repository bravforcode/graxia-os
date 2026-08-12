"""Structured metrics for pipeline monitoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class PipelineMetrics:
    headlines_processed: int = 0
    signals_generated: int = 0
    orders_placed: int = 0
    signals_blocked: int = 0
    regime_changes: int = 0
    current_regime: str = "NORMAL"
    current_position_mult: float = 1.0
    last_update: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        return {
            k: (v.isoformat() if isinstance(v, datetime) else v)
            for k, v in self.__dict__.items()
        }

    def log_summary(self, logger) -> None:
        data = self.to_dict()
        try:
            logger.info("pipeline.metrics", **data)
        except TypeError:
            logger.info("pipeline.metrics %s", data)
