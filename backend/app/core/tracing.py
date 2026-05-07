"""
Distributed Tracing

OpenTelemetry-compatible tracing for request tracking.
"""
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Context variables
trace_id_var: ContextVar[str] = ContextVar('trace_id', default='')
span_id_var: ContextVar[str] = ContextVar('span_id', default='')


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Span:
    """Trace span."""
    span_id: str
    trace_id: str
    parent_span_id: str | None
    name: str
    start_time: datetime
    end_time: datetime | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list = field(default_factory=list)
    status: str = "ok"
    
    def set_attribute(self, key: str, value: Any):
        """Set span attribute."""
        self.attributes[key] = value
    
    def add_event(self, name: str, attributes: dict[str, Any] = None):
        """Add event to span."""
        self.events.append({
            "name": name,
            "timestamp": _utc_now().isoformat(),
            "attributes": attributes or {}
        })
    
    def set_status(self, status: str):
        """Set span status."""
        self.status = status
    
    def end(self):
        """End span."""
        self.end_time = _utc_now()
    
    def to_dict(self) -> dict[str, Any]:
        """Convert span to dictionary."""
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": (
                (self.end_time - self.start_time).total_seconds() * 1000
                if self.end_time else None
            ),
            "attributes": self.attributes,
            "events": self.events,
            "status": self.status,
        }


class Tracer:
    """Distributed tracer."""
    
    def __init__(self):
        self.spans: dict[str, Span] = {}
    
    def start_trace(self, name: str) -> str:
        """Start a new trace."""
        trace_id = str(uuid.uuid4())
        trace_id_var.set(trace_id)
        
        span = self.start_span(name)
        return trace_id
    
    def start_span(
        self,
        name: str,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] = None
    ) -> Span:
        """Start a new span."""
        trace_id = trace_id_var.get()
        if not trace_id:
            trace_id = str(uuid.uuid4())
            trace_id_var.set(trace_id)
        
        span_id = str(uuid.uuid4())
        span_id_var.set(span_id)
        
        span = Span(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id or span_id_var.get(),
            name=name,
            start_time=_utc_now(),
            attributes=attributes or {}
        )
        
        self.spans[span_id] = span
        return span
    
    def end_span(self, span: Span):
        """End a span."""
        span.end()
    
    def get_span(self, span_id: str) -> Span | None:
        """Get span by ID."""
        return self.spans.get(span_id)
    
    def get_trace_spans(self, trace_id: str) -> list:
        """Get all spans for a trace."""
        return [
            span for span in self.spans.values()
            if span.trace_id == trace_id
        ]
    
    def export_trace(self, trace_id: str) -> dict[str, Any]:
        """Export trace data."""
        spans = self.get_trace_spans(trace_id)
        return {
            "trace_id": trace_id,
            "spans": [span.to_dict() for span in spans],
            "span_count": len(spans),
        }


# Global tracer
tracer = Tracer()


class TraceContext:
    """Context manager for tracing."""
    
    def __init__(self, name: str, attributes: dict[str, Any] = None):
        self.name = name
        self.attributes = attributes
        self.span: Span | None = None
    
    def __enter__(self) -> Span:
        self.span = tracer.start_span(self.name, attributes=self.attributes)
        return self.span
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.span:
            if exc_type:
                self.span.set_status("error")
                self.span.set_attribute("error.type", exc_type.__name__)
                self.span.set_attribute("error.message", str(exc_val))
            tracer.end_span(self.span)


def trace_function(name: str = None):
    """Decorator to trace function execution."""
    def decorator(func):
        func_name = name or f"{func.__module__}.{func.__name__}"
        
        async def async_wrapper(*args, **kwargs):
            with TraceContext(func_name) as span:
                span.set_attribute("function", func.__name__)
                span.set_attribute("module", func.__module__)
                result = await func(*args, **kwargs)
                return result
        
        def sync_wrapper(*args, **kwargs):
            with TraceContext(func_name) as span:
                span.set_attribute("function", func.__name__)
                span.set_attribute("module", func.__module__)
                result = func(*args, **kwargs)
                return result
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator
