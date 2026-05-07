import time
from prometheus_client import Counter, Histogram, Gauge, start_http_server
import logging

logger = logging.getLogger(__name__)

# Metrics Definitions
TOKEN_USAGE = Counter(
    'graxia_token_usage_total', 
    'Total token usage per agent', 
    ['agent_name', 'model', 'type'] # type: prompt or completion
)

LLM_LATENCY = Histogram(
    'graxia_llm_latency_seconds', 
    'Latency of LLM calls in seconds', 
    ['model', 'provider'],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60)
)

CACHE_HITS = Counter(
    'graxia_cache_hits_total', 
    'Number of semantic cache hits',
    ['status'] # status: hit or miss
)

DLQ_DEPTH = Gauge(
    'graxia_dlq_depth',
    'Current number of tasks in the Dead Letter Queue'
)

AGENT_ITERATIONS = Counter(
    'graxia_agent_iterations_total',
    'Total number of autonomous agent iterations',
    ['agent_name']
)

class MetricsManager:
    """Manages Prometheus metrics exposition."""
    _started = False

    @classmethod
    def start_server(cls, port: int = 9090):
        """Starts the Prometheus metrics server."""
        if not cls._started:
            try:
                start_http_server(port)
                logger.info(f"Prometheus metrics server started on port {port}")
                cls._started = True
            except Exception as e:
                logger.error(f"Failed to start Prometheus server: {e}")

    @staticmethod
    def track_llm_call(model: str, provider: str):
        """Context manager to track LLM latency."""
        return LLM_LATENCY.labels(model=model, provider=provider).time()

metrics_manager = MetricsManager()
