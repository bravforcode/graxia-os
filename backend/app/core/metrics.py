"""
Metrics Collection

Prometheus-compatible metrics for monitoring.
"""
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Metric:
    """Base metric class."""
    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


class MetricsCollector:
    """Collect and expose metrics."""
    
    def __init__(self):
        self.counters: dict[str, float] = defaultdict(float)
        self.gauges: dict[str, float] = {}
        self.histograms: dict[str, list[float]] = defaultdict(list)
        self.timers: dict[str, list[float]] = defaultdict(list)
    
    def increment_counter(self, name: str, value: float = 1.0, labels: dict[str, str] = None):
        """Increment a counter metric."""
        key = self._make_key(name, labels)
        self.counters[key] += value
    
    def set_gauge(self, name: str, value: float, labels: dict[str, str] = None):
        """Set a gauge metric."""
        key = self._make_key(name, labels)
        self.gauges[key] = value
    
    def observe_histogram(self, name: str, value: float, labels: dict[str, str] = None):
        """Observe a value in histogram."""
        key = self._make_key(name, labels)
        self.histograms[key].append(value)
    
    def record_timer(self, name: str, duration: float, labels: dict[str, str] = None):
        """Record a timer duration."""
        key = self._make_key(name, labels)
        self.timers[key].append(duration)
    
    def get_counter(self, name: str, labels: dict[str, str] = None) -> float:
        """Get counter value."""
        key = self._make_key(name, labels)
        return self.counters.get(key, 0.0)
    
    def get_gauge(self, name: str, labels: dict[str, str] = None) -> float:
        """Get gauge value."""
        key = self._make_key(name, labels)
        return self.gauges.get(key, 0.0)
    
    def get_histogram_stats(self, name: str, labels: dict[str, str] = None) -> dict[str, float]:
        """Get histogram statistics."""
        key = self._make_key(name, labels)
        values = self.histograms.get(key, [])
        
        if not values:
            return {"count": 0, "sum": 0, "min": 0, "max": 0, "avg": 0}
        
        return {
            "count": len(values),
            "sum": sum(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "p50": self._percentile(values, 50),
            "p95": self._percentile(values, 95),
            "p99": self._percentile(values, 99),
        }
    
    def get_timer_stats(self, name: str, labels: dict[str, str] = None) -> dict[str, float]:
        """Get timer statistics."""
        return self.get_histogram_stats(name, labels)
    
    def export_prometheus(self) -> str:
        """Export metrics in Prometheus format."""
        lines = []
        
        # Counters
        for key, value in self.counters.items():
            lines.append(f"{key} {value}")
        
        # Gauges
        for key, value in self.gauges.items():
            lines.append(f"{key} {value}")
        
        # Histograms
        for key, values in self.histograms.items():
            stats = self.get_histogram_stats(key.split("{")[0])
            lines.append(f"{key}_count {stats['count']}")
            lines.append(f"{key}_sum {stats['sum']}")
            lines.append(f"{key}_avg {stats['avg']}")
        
        return "\n".join(lines)
    
    def reset(self):
        """Reset all metrics."""
        self.counters.clear()
        self.gauges.clear()
        self.histograms.clear()
        self.timers.clear()
    
    def _make_key(self, name: str, labels: dict[str, str] = None) -> str:
        """Make metric key with labels."""
        if not labels:
            return name
        
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
    
    def _percentile(self, values: list[float], percentile: int) -> float:
        """Calculate percentile."""
        if not values:
            return 0.0
        
        sorted_values = sorted(values)
        index = int(len(sorted_values) * percentile / 100)
        return sorted_values[min(index, len(sorted_values) - 1)]


# Global metrics collector
metrics = MetricsCollector()


# Common metrics
class CommonMetrics:
    """Common application metrics."""
    
    @staticmethod
    def record_request(method: str, path: str, status_code: int, duration: float):
        """Record HTTP request metrics."""
        metrics.increment_counter(
            "http_requests_total",
            labels={"method": method, "path": path, "status": str(status_code)}
        )
        metrics.record_timer(
            "http_request_duration_seconds",
            duration,
            labels={"method": method, "path": path}
        )
    
    @staticmethod
    def record_db_query(operation: str, duration: float):
        """Record database query metrics."""
        metrics.increment_counter(
            "db_queries_total",
            labels={"operation": operation}
        )
        metrics.record_timer(
            "db_query_duration_seconds",
            duration,
            labels={"operation": operation}
        )
    
    @staticmethod
    def record_llm_call(model: str, tokens: int, cost: float, duration: float):
        """Record LLM API call metrics."""
        metrics.increment_counter(
            "llm_calls_total",
            labels={"model": model}
        )
        metrics.increment_counter(
            "llm_tokens_total",
            value=tokens,
            labels={"model": model}
        )
        metrics.increment_counter(
            "llm_cost_total",
            value=cost,
            labels={"model": model}
        )
        metrics.record_timer(
            "llm_call_duration_seconds",
            duration,
            labels={"model": model}
        )
    
    @staticmethod
    def record_scraper_run(scraper: str, success: bool, items_found: int):
        """Record scraper run metrics."""
        metrics.increment_counter(
            "scraper_runs_total",
            labels={"scraper": scraper, "success": str(success)}
        )
        metrics.set_gauge(
            "scraper_items_found",
            items_found,
            labels={"scraper": scraper}
        )
    
    @staticmethod
    def record_agent_execution(agent: str, success: bool, duration: float):
        """Record agent execution metrics."""
        metrics.increment_counter(
            "agent_executions_total",
            labels={"agent": agent, "success": str(success)}
        )
        metrics.record_timer(
            "agent_execution_duration_seconds",
            duration,
            labels={"agent": agent}
        )
    
    @staticmethod
    def set_system_health(component: str, healthy: bool):
        """Set system health status."""
        metrics.set_gauge(
            "system_health",
            1.0 if healthy else 0.0,
            labels={"component": component}
        )


class Timer:
    """Context manager for timing operations."""
    
    def __init__(self, metric_name: str, labels: dict[str, str] = None):
        self.metric_name = metric_name
        self.labels = labels
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        metrics.record_timer(self.metric_name, duration, self.labels)
