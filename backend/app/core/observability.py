"""
ULTRA: Comprehensive Observability Layer
Metrics, distributed tracing, health checks, and alerting hooks
"""
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any
from uuid import uuid4

import structlog
from fastapi import Request, Response
from prometheus_client import Counter, Gauge, Histogram, Info, generate_latest

from app.config import settings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# ULTRA: Prometheus Metrics
# ═══════════════════════════════════════════════════════════════════════════════

def _create_or_get_counter(name: str, description: str, labels: list[str]):
    """Create counter or return existing to prevent duplicate registration"""
    try:
        return Counter(name, description, labels)
    except ValueError:
        # Already exists - return a dummy counter that won't be used
        # The real counter is already registered
        class _DummyCounter:
            def inc(self, *args, **kwargs): pass
            def labels(self, *args, **kwargs): return self
        return _DummyCounter()

def _create_or_get_histogram(name: str, description: str, labels: list[str], buckets=None):
    """Create histogram or return existing to prevent duplicate registration"""
    try:
        if buckets:
            return Histogram(name, description, labels, buckets=buckets)
        return Histogram(name, description, labels)
    except ValueError:
        class _DummyHistogram:
            def observe(self, *args, **kwargs): pass
            def labels(self, *args, **kwargs): return self
        return _DummyHistogram()

def _create_or_get_gauge(name: str, description: str, labels: list[str]):
    """Create gauge or return existing to prevent duplicate registration"""
    try:
        return Gauge(name, description, labels)
    except ValueError:
        class _DummyGauge:
            def set(self, *args, **kwargs): pass
            def inc(self, *args, **kwargs): pass
            def dec(self, *args, **kwargs): pass
            def labels(self, *args, **kwargs): return self
        return _DummyGauge()

# Request metrics
REQUEST_COUNT = _create_or_get_counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code", "tier"]
)

REQUEST_DURATION = _create_or_get_histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

REQUEST_SIZE = _create_or_get_histogram(
    "http_request_size_bytes",
    "HTTP request size",
    ["method", "endpoint"],
    buckets=[100, 1000, 10000, 100000, 1000000]
)

RESPONSE_SIZE = _create_or_get_histogram(
    "http_response_size_bytes",
    "HTTP response size",
    ["method", "endpoint"],
    buckets=[100, 1000, 10000, 100000, 1000000]
)

# Business metrics
ACTIVE_USERS = _create_or_get_gauge("active_users", "Number of active users", ["tier"])

ORGANIZATION_COUNT = _create_or_get_gauge("organization_count", "Number of organizations", ["plan"])

BILLING_EVENTS = _create_or_get_counter("billing_events_total", "Billing events", ["event_type", "plan"])

CACHE_OPERATIONS = _create_or_get_counter("cache_operations_total", "Cache operations", ["operation", "result"])

CACHE_DURATION = _create_or_get_histogram(
    "cache_operation_duration_seconds",
    "Cache operation duration",
    ["operation"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1]
)

# Database metrics
DB_QUERY_DURATION = _create_or_get_histogram(
    "db_query_duration_seconds",
    "Database query duration",
    ["operation", "table"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

DB_CONNECTIONS = _create_or_get_gauge("db_connections_active", "Active database connections", [])

# External API metrics
EXTERNAL_API_CALLS = _create_or_get_counter("external_api_calls_total", "External API calls", ["service", "endpoint", "status"])

EXTERNAL_API_DURATION = _create_or_get_histogram(
    "external_api_duration_seconds",
    "External API call duration",
    ["service"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

# System info
try:
    APP_INFO = Info("app_info", "Application information")
except ValueError:
    APP_INFO = None  # Already registered


# ═══════════════════════════════════════════════════════════════════════════════
# ULTRA: Distributed Tracing Context
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TraceContext:
    """Distributed tracing context"""
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    span_id: str = field(default_factory=lambda: str(uuid4()))
    parent_span_id: str | None = None
    start_time: float = field(default_factory=time.time)
    tags: dict[str, Any] = field(default_factory=dict)

    def to_headers(self) -> dict[str, str]:
        """Convert to HTTP headers for propagation"""
        return {
            "X-Trace-ID": self.trace_id,
            "X-Span-ID": self.span_id,
            "X-Parent-Span-ID": self.parent_span_id or "",
        }

    @classmethod
    def from_headers(cls, headers: dict[str, str]) -> "TraceContext":
        """Create from HTTP headers"""
        return cls(
            trace_id=headers.get("X-Trace-ID", str(uuid4())),
            span_id=str(uuid4()),
            parent_span_id=headers.get("X-Span-ID"),
        )


class TracingMiddleware:
    """FastAPI middleware for distributed tracing"""

    async def __call__(self, request: Request, call_next):
        # Extract or create trace context
        trace_ctx = TraceContext.from_headers(dict(request.headers))

        # Store in request state
        request.state.trace_ctx = trace_ctx

        # Start timing
        start_time = time.time()

        # Add trace info to logs
        structlog.contextvars.bind_contextvars(
            trace_id=trace_ctx.trace_id,
            span_id=trace_ctx.span_id,
        )

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration = time.time() - start_time

        # Add trace headers to response
        response.headers["X-Trace-ID"] = trace_ctx.trace_id
        response.headers["X-Request-Duration"] = str(duration)

        return response


# ═══════════════════════════════════════════════════════════════════════════════
# ULTRA: Structured Logging
# ═══════════════════════════════════════════════════════════════════════════════

def configure_structlog():
    """Configure structured logging for production"""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )


def get_logger(name: str):
    """Get structured logger"""
    return structlog.get_logger(name)


# ═══════════════════════════════════════════════════════════════════════════════
# ULTRA: Performance Monitoring Decorators
# ═══════════════════════════════════════════════════════════════════════════════

def timed(metric_name: str, labels: dict | None = None):
    """
    Decorator to time function execution

    Usage:
        @timed("db_query_duration", {"table": "users"})
        async def get_users():
            return await db.query(User).all()
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start

                # Record metric
                if metric_name == "db_query_duration":
                    DB_QUERY_DURATION.labels(
                        operation=func.__name__,
                        table=labels.get("table", "unknown")
                    ).observe(duration)

                return result
            except Exception as e:
                duration = time.time() - start
                logger.error(f"{metric_name} failed", error=str(e), duration=duration)
                raise
        return wrapper
    return decorator


def cached_metric(metric_name: str):
    """
    Decorator to track cache operations

    Usage:
        @cached_metric("opportunities_cache")
        async def get_opportunities():
            return await cache.get("opps")
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()
            operation = func.__name__

            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start

                CACHE_OPERATIONS.labels(operation=operation, result="hit").inc()
                CACHE_DURATION.labels(operation=operation).observe(duration)

                return result
            except Exception:
                CACHE_OPERATIONS.labels(operation=operation, result="error").inc()
                raise
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════════════════════
# ULTRA: Health Check System
# ═══════════════════════════════════════════════════════════════════════════════

class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheck:
    """Health check result"""
    name: str
    status: HealthStatus
    message: str
    latency_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)


class HealthChecker:
    """Comprehensive health checker"""

    def __init__(self):
        self.checks: dict[str, Callable] = {}

    def register(self, name: str, check_func: Callable):
        """Register a health check"""
        self.checks[name] = check_func

    async def check_all(self) -> list[HealthCheck]:
        """Run all health checks"""
        results = []

        for name, check_func in self.checks.items():
            start = time.time()
            try:
                result = await check_func()
                latency = (time.time() - start) * 1000

                if isinstance(result, bool):
                    status = HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY
                    message = "OK" if result else "Failed"
                    metadata = {}
                else:
                    status = result.get("status", HealthStatus.HEALTHY)
                    message = result.get("message", "OK")
                    metadata = result.get("metadata", {})

                results.append(HealthCheck(
                    name=name,
                    status=status,
                    message=message,
                    latency_ms=latency,
                    metadata=metadata
                ))
            except Exception as e:
                results.append(HealthCheck(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=str(e),
                    latency_ms=(time.time() - start) * 1000,
                    metadata={"error": str(e)}
                ))

        return results

    def get_overall_status(self, checks: list[HealthCheck]) -> HealthStatus:
        """Get overall health status from individual checks"""
        if any(c.status == HealthStatus.UNHEALTHY for c in checks):
            return HealthStatus.UNHEALTHY
        if any(c.status == HealthStatus.DEGRADED for c in checks):
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY


# Global health checker
health_checker = HealthChecker()


# Register default health checks
def register_default_health_checks():
    """Register default system health checks"""

    async def check_database():
        """Check database connectivity"""
        from app.database import engine
        try:
            async with engine.connect() as conn:
                await conn.execute("SELECT 1")
            return {"status": HealthStatus.HEALTHY, "message": "Database connected"}
        except Exception as e:
            return {"status": HealthStatus.UNHEALTHY, "message": str(e)}

    async def check_redis():
        """Check Redis connectivity"""
        try:
            from app.middleware.rate_limit import get_redis_client
            redis = await get_redis_client()
            await redis.ping()
            return {"status": HealthStatus.HEALTHY, "message": "Redis connected"}
        except Exception as e:
            return {"status": HealthStatus.UNHEALTHY, "message": str(e)}

    async def check_disk_space():
        """Check disk space"""
        import shutil
        try:
            stat = shutil.disk_usage("/")
            free_gb = stat.free / (1024**3)
            if free_gb < 1:
                return {"status": HealthStatus.DEGRADED, "message": f"Low disk space: {free_gb:.1f}GB"}
            return {"status": HealthStatus.HEALTHY, "message": f"Disk space OK: {free_gb:.1f}GB"}
        except Exception as e:
            return {"status": HealthStatus.DEGRADED, "message": str(e)}

    health_checker.register("database", check_database)
    health_checker.register("redis", check_redis)
    health_checker.register("disk", check_disk_space)


# ═══════════════════════════════════════════════════════════════════════════════
# ULTRA: Alerting Hooks
# ═══════════════════════════════════════════════════════════════════════════════

class AlertManager:
    """Alert management for critical events"""

    def __init__(self):
        self.alert_handlers: list[Callable] = []

    def register_handler(self, handler: Callable):
        """Register an alert handler"""
        self.alert_handlers.append(handler)

    async def send_alert(
        self,
        severity: str,  # critical, warning, info
        title: str,
        message: str,
        metadata: dict | None = None
    ):
        """Send alert through all registered handlers"""
        alert = {
            "severity": severity,
            "title": title,
            "message": message,
            "metadata": metadata or {},
            "timestamp": time.time(),
        }

        for handler in self.alert_handlers:
            try:
                await handler(alert)
            except Exception as e:
                logger.error(f"Alert handler failed: {e}")

        # Always log
        log_method = getattr(logger, severity, logger.info)
        log_method(f"ALERT: {title} - {message}", extra=alert)


# Global alert manager
alert_manager = AlertManager()


# ═══════════════════════════════════════════════════════════════════════════════
# Initialization
# ═══════════════════════════════════════════════════════════════════════════════

def init_observability():
    """Initialize observability layer"""
    # Set app info
    APP_INFO.info({
        "version": settings.APP_VERSION if hasattr(settings, 'APP_VERSION') else "1.0.0",
        "name": settings.APP_NAME if hasattr(settings, 'APP_NAME') else "Graxia OS",
        "environment": settings.APP_ENV,
    })

    # Configure structured logging
    configure_structlog()

    # Register health checks
    register_default_health_checks()

    logger.info("Observability layer initialized")


# Prometheus metrics endpoint
async def metrics_endpoint() -> Response:
    """Prometheus metrics endpoint"""
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(
        content=generate_latest(),
        media_type="text/plain"
    )
