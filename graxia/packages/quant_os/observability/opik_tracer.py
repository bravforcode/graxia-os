"""Opik LLM Observability & Tracing Integration for quant_os.

Provides unified tracing for LLM calls, trading strategy decisions, and agent executions.
Supports Comet hosted Opik and self-hosted instances via environment configuration.
"""

import logging
import os
from collections.abc import Callable

logger = logging.getLogger(__name__)

_opik_client = None


def init_opik_tracer(
    project_name: str = "quant_os", api_key: str | None = None, workspace: str | None = None, disabled: bool = False
) -> bool:
    """Initialize Opik tracer for quant_os.

    Reads OPIK_API_KEY and OPIK_WORKSPACE from environment if not explicitly provided.
    """
    global _opik_client
    if disabled or os.getenv("OPIK_DISABLED", "false").lower() == "true":
        logger.info("Opik tracing disabled by configuration.")
        return False

    resolved_api_key = api_key or os.getenv("OPIK_API_KEY")
    resolved_workspace = workspace or os.getenv("OPIK_WORKSPACE")

    try:
        import opik

        if resolved_api_key:
            opik.configure(api_key=resolved_api_key, workspace=resolved_workspace)
        _opik_client = opik.Opik(project_name=project_name)
        logger.info(f"Opik tracer initialized successfully for project: {project_name}")
        return True
    except ImportError:
        logger.warning("opik library is not installed. Install with `pip install opik`.")
        return False
    except Exception as e:
        logger.warning(f"Failed to initialize Opik tracer: {e}")
        return False


def track_llm_execution(name: str, tags: list | None = None):
    """Decorator or wrapper to track LLM agent calls and strategy inference."""
    try:
        from opik import track

        return track(name=name, tags=tags or ["quant_os", "agent"])
    except ImportError:

        def dummy_decorator(func: Callable):
            return func

        return dummy_decorator


def log_agent_feedback(trace_id: str, name: str, value: float, category: str = "accuracy"):
    """Log evaluation feedback / metric for a trace in Opik."""
    global _opik_client
    if _opik_client:
        try:
            _opik_client.log_traces_feedback(  # type: ignore[attr-defined]
                trace_ids=[trace_id], feedback_scores=[{"name": name, "value": value, "category": category}]
            )
        except Exception as e:
            logger.debug(f"Failed to log feedback to Opik: {e}")
