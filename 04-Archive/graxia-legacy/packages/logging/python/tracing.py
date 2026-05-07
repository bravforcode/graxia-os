from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.sdk.resources import SERVICE_NAME, Resource

def setup_tracing(service_name: str = "bravos-service") -> trace.Tracer:
    """
    Initializes OpenTelemetry tracing with a basic Console exporter for observability.
    In production, ConsoleSpanExporter would be replaced with an OTLPSpanExporter (Jaeger/Honeycomb).
    """
    resource = Resource(attributes={
        SERVICE_NAME: service_name
    })

    provider = TracerProvider(resource=resource)
    
    # Processor to batch and export spans
    # Using ConsoleSpanExporter as a stub for local development/hardening verification
    processor = BatchSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)

    # Sets the global default tracer provider
    trace.set_tracer_provider(provider)

    return trace.get_tracer(service_name)

# Usage example
tracer = setup_tracing()

def get_tracer():
    """Helper to retrieve the global tracer."""
    return trace.get_tracer("bravos-service")
