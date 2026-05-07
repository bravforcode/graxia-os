"""
Metrics Service - re-exports from core.metrics for service layer access
"""

from app.core.metrics import (
    Metric,
    MetricsCollector,
)

# Create a singleton instance for the application
metrics = MetricsCollector()

__all__ = [
    "Metric",
    "MetricsCollector",
    "metrics",
]
