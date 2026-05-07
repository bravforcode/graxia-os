import time
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from core.logger import logger

STATE_DIR = Path(".state")
TASK_COSTS_FILE = STATE_DIR / "task_costs.json"

class TaskCostTracker:
    """Tracks task execution duration and cost estimation based on tokens."""
    
    @staticmethod
    async def log_cost(task_id: str, agent_name: str, duration: float, prompt_tokens: int, completion_tokens: int):
        # Arbitrary enterprise rates ($0.01 / 1k prompt, $0.03 / 1k completion)
        cost = (prompt_tokens / 1000 * 0.01) + (completion_tokens / 1000 * 0.03)
        
        def _write():
            TASK_COSTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = []
            if TASK_COSTS_FILE.exists():
                try:
                    with open(TASK_COSTS_FILE, "r") as f:
                        data = json.load(f)
                except json.JSONDecodeError:
                    pass
            data.append({
                "task_id": task_id,
                "agent_name": agent_name,
                "duration_seconds": round(duration, 2),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "estimated_cost_usd": round(cost, 4),
                "timestamp": datetime.now().isoformat()
            })
            with open(TASK_COSTS_FILE, "w") as f:
                json.dump(data, f, indent=2)
                
        await asyncio.to_thread(_write)
        logger.info(f"Logged task {task_id} cost: ${cost:.4f}")

@dataclass
class TelemetryReport:
    """Standard report structure for telemetry data."""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    latencies: Dict[str, float] = field(default_factory=dict)
    tokens: Dict[str, int] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

class LatencyTracker:
    """Tracks latency across different layers of the architecture."""

    def __init__(self):
        self._start_times = {}
        self._latencies = {}

    def start(self, layer: str):
        """Start tracking latency for a specific layer."""
        self._start_times[layer] = time.perf_counter()

    def stop(self, layer: str):
        """Stop tracking latency for a specific layer and store the duration."""
        if layer in self._start_times:
            duration = time.perf_counter() - self._start_times[layer]
            self._latencies[layer] = duration
            return duration
        return 0.0

    @property
    def latencies(self) -> Dict[str, float]:
        """Returns all recorded latencies."""
        return self._latencies

class TokenAuditor:
    """Audits token usage and calculates savings from caching."""

    def __init__(self):
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cached_tokens = 0

    def add_usage(self, prompt: int = 0, completion: int = 0, cached: int = 0):
        """Record token usage."""
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.cached_tokens += cached

    @property
    def usage(self) -> Dict[str, int]:
        """Returns current usage stats."""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
            "cached_tokens": self.cached_tokens,
            "tokens_saved": self.cached_tokens
        }

class TelemetrySystem:
    """Orchestrates latency tracking and token auditing."""

    def __init__(self):
        self.latency_tracker = LatencyTracker()
        self.token_auditor = TokenAuditor()

    def get_report(self) -> TelemetryReport:
        """Generates a complete telemetry report."""
        return TelemetryReport(
            latencies=self.latency_tracker.latencies,
            tokens=self.token_auditor.usage
        )

    def log_report(self):
        """Logs the report using the enterprise logger."""
        report = self.get_report()
        logger.info("Telemetry Report", extra={"telemetry": asdict(report)})
