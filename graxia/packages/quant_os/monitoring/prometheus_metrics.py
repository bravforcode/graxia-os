"""Pure-Python Prometheus-style metrics exporter (no prometheus_client dependency)."""

import time
import threading
from collections import defaultdict
from typing import Dict, List, Optional


class TradeCounter:
    """Counts total trades by symbol, side, strategy."""

    def __init__(self):
        self._counts: Dict[tuple, int] = defaultdict(int)
        self._lock = threading.Lock()

    def inc(self, symbol: str = "", side: str = "", strategy: str = "", n: int = 1):
        with self._lock:
            self._counts[(symbol, side, strategy)] += n

    def value(self, symbol: str = "", side: str = "", strategy: str = "") -> int:
        with self._lock:
            return self._counts.get((symbol, side, strategy), 0)

    def render(self, name: str = "quant_os_trades_total") -> str:
        lines = [f"# TYPE {name} counter"]
        with self._lock:
            for (sym, side, strat), val in sorted(self._counts.items()):
                labels = []
                if sym:
                    labels.append(f'symbol="{sym}"')
                if side:
                    labels.append(f'side="{side}"')
                if strat:
                    labels.append(f'strategy="{strat}"')
                lbl = "," + ",".join(labels) if labels else ""
                lines.append(f'{name}{lbl} {val}')
        return "\n".join(lines)


class PnLHistogram:
    """Tracks PnL distribution via fixed buckets."""

    DEFAULT_BUCKETS = (-100, -50, -20, -10, -5, -2, 0, 2, 5, 10, 20, 50, 100, float("inf"))

    def __init__(self, buckets: Optional[tuple] = None):
        self._buckets = buckets or self.DEFAULT_BUCKETS
        self._counts = [0] * (len(self._buckets) - 1)
        self._total = 0.0
        self._count = 0
        self._lock = threading.Lock()

    def observe(self, value: float):
        with self._lock:
            self._total += value
            self._count += 1
            for i in range(len(self._buckets) - 1):
                if self._buckets[i] <= value < self._buckets[i + 1]:
                    self._counts[i] += 1
                    break

    def render(self, name: str = "quant_os_pnl") -> str:
        lines = [f"# TYPE {name} histogram"]
        cum = 0
        with self._lock:
            for i, bucket in enumerate(self._buckets):
                if bucket == float("inf"):
                    break
                cum += self._counts[i]
                lines.append(f'{name}_bucket{{le="{bucket}"}} {cum}')
            cum_all = sum(self._counts)
            lines.append(f'{name}_bucket{{le="+Inf"}} {cum_all}')
            lines.append(f'{name}_sum {self._total:.6f}')
            lines.append(f'{name}_count {self._count}')
        return "\n".join(lines)


class RiskGauge:
    """Current risk level (0-100)."""

    def __init__(self):
        self._value: float = 0.0
        self._lock = threading.Lock()

    def set(self, value: float):
        with self._lock:
            self._value = max(0.0, min(100.0, value))

    def get(self) -> float:
        with self._lock:
            return self._value

    def render(self, name: str = "quant_os_risk_level") -> str:
        with self._lock:
            val = self._value
        return f"# TYPE {name} gauge\n{name} {val:.1f}"


class LatencyHistogram:
    """Signal-to-order latency in seconds."""

    DEFAULT_BUCKETS = (0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, float("inf"))

    def __init__(self, buckets: Optional[tuple] = None):
        self._buckets = buckets or self.DEFAULT_BUCKETS
        self._counts = [0] * (len(self._buckets) - 1)
        self._total = 0.0
        self._count = 0
        self._lock = threading.Lock()

    def observe(self, value: float):
        with self._lock:
            self._total += value
            self._count += 1
            for i in range(len(self._buckets) - 1):
                if self._buckets[i] <= value < self._buckets[i + 1]:
                    self._counts[i] += 1
                    break

    def render(self, name: str = "quant_os_latency_seconds") -> str:
        lines = [f"# TYPE {name} histogram"]
        cum = 0
        with self._lock:
            for i, bucket in enumerate(self._buckets):
                if bucket == float("inf"):
                    break
                cum += self._counts[i]
                lines.append(f'{name}_bucket{{le="{bucket}"}} {cum}')
            cum_all = sum(self._counts)
            lines.append(f'{name}_bucket{{le="+Inf"}} {cum_all}')
            lines.append(f'{name}_sum {self._total:.6f}')
            lines.append(f'{name}_count {self._count}')
        return "\n".join(lines)


class ExposureGauge:
    """Current portfolio exposure (absolute notional)."""

    def __init__(self):
        self._value: float = 0.0
        self._lock = threading.Lock()

    def set(self, value: float):
        with self._lock:
            self._value = max(0.0, value)

    def get(self) -> float:
        with self._lock:
            return self._value

    def render(self, name: str = "quant_os_exposure") -> str:
        with self._lock:
            val = self._value
        return f"# TYPE {name} gauge\n{name} {val:.2f}"


class MetricsRegistry:
    """Collects all metrics and renders combined Prometheus text output."""

    def __init__(self):
        self.trades = TradeCounter()
        self.pnl = PnLHistogram()
        self.risk = RiskGauge()
        self.latency = LatencyHistogram()
        self.exposure = ExposureGauge()

    def render(self) -> str:
        parts = [
            self.trades.render(),
            self.pnl.render(),
            self.risk.render(),
            self.latency.render(),
            self.exposure.render(),
        ]
        return "\n".join(parts) + "\n"
