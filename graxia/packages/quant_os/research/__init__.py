"""Automated research pipeline for quant_os."""

from __future__ import annotations

__all__ = ["ResearchPipeline", "PipelineResult", "SweepResult"]


def __getattr__(name: str):
    """Lazy import so ``import research`` works without triggering pipeline.py's
    relative-import chain (which only resolves inside the quant_os package)."""
    if name in __all__:
        from .pipeline import PipelineResult, ResearchPipeline, SweepResult

        return {"ResearchPipeline": ResearchPipeline, "PipelineResult": PipelineResult, "SweepResult": SweepResult}[
            name
        ]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
