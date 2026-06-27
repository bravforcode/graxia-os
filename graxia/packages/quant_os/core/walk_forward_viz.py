"""
Walk-Forward Visualization — ASCII chart of model performance over time.

Shows:
  - Accuracy over walk-forward windows
  - Drift detection points
  - Training vs OOS performance
  - Retrain events

Usage:
  from core.walk_forward_viz import WalkForwardViz
  viz = WalkForwardViz()
  viz.add_window(accuracy=0.59, oos_accuracy=0.55, window=1)
  viz.render()
"""
from __future__ import annotations

from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class WindowResult:
    window: int
    accuracy: float
    oos_accuracy: float = 0.0
    retrained: bool = False
    drifted: bool = False


class WalkForwardViz:
    """ASCII visualization of walk-forward validation results."""

    CHART_WIDTH = 50
    MIN_ACC = 0.40
    MAX_ACC = 0.70

    def __init__(self):
        self._windows: list[WindowResult] = []

    def add_window(self, accuracy: float, oos_accuracy: float = 0.0,
                   window: int = 0, retrained: bool = False, drifted: bool = False):
        self._windows.append(WindowResult(
            window=window or len(self._windows) + 1,
            accuracy=accuracy,
            oos_accuracy=oos_accuracy,
            retrained=retrained,
            drifted=drifted,
        ))

    def _bar(self, value: float, label: str = "") -> str:
        normalized = (value - self.MIN_ACC) / (self.MAX_ACC - self.MIN_ACC)
        normalized = max(0.0, min(1.0, normalized))
        filled = int(normalized * self.CHART_WIDTH)
        bar = "#" * filled + "-" * (self.CHART_WIDTH - filled)
        return f"  {label:>4} |{bar}| {value:.1%}"

    def render(self) -> str:
        if not self._windows:
            return "  No walk-forward data available."

        lines = [
            "",
            "  WALK-FORWARD VALIDATION",
            "  " + "=" * 60,
            "",
            f"  {'':>4} |{'#' * self.CHART_WIDTH}| Accuracy Range",
            f"  {'':>4} |{self.MIN_ACC:.0%}" + " " * (self.CHART_WIDTH - 8) + f"{self.MAX_ACC:.0%}|",
            "",
        ]

        for w in self._windows:
            marker = " [DRIFT]" if w.drifted else " [RETRAIN]" if w.retrained else ""
            lines.append(self._bar(w.accuracy, f"W{w.window}"))
            if w.oos_accuracy > 0:
                lines.append(self._bar(w.oos_accuracy, f" OOS"))
            if marker:
                lines[-1] += marker

        # Summary
        accs = [w.accuracy for w in self._windows]
        oos = [w.oos_accuracy for w in self._windows if w.oos_accuracy > 0]
        drifts = sum(1 for w in self._windows if w.drifted)

        lines.extend([
            "",
            "  " + "-" * 60,
            f"  Windows: {len(self._windows)} | "
            f"Avg Acc: {sum(accs)/len(accs):.1%} | "
            f"Avg OOS: {sum(oos)/len(oos):.1% if oos else 'N/A'} | "
            f"Drifts: {drifts}",
            "",
        ])

        text = "\n".join(lines)
        print(text)
        return text

    def to_markdown(self) -> str:
        """Generate markdown table for Obsidian/GitHub."""
        lines = [
            "| Window | Accuracy | OOS Accuracy | Status |",
            "|--------|----------|--------------|--------|",
        ]
        for w in self._windows:
            status = "DRIFT" if w.drifted else "RETRAIN" if w.retrained else "OK"
            lines.append(
                f"| W{w.window} | {w.accuracy:.1%} | {w.oos_accuracy:.1% if w.oos_accuracy else '-'} | {status} |"
            )
        return "\n".join(lines)
