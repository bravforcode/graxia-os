"""
Walk-Forward Visualization — Production HTML dashboard.

Serves a real-time HTML dashboard showing:
  - Model accuracy over walk-forward windows
  - Drift detection alerts
  - Training vs OOS performance
  - Retrain events

Usage:
  from core.walk_forward_production import WalkForwardDashboard
  dashboard = WalkForwardDashboard()
  dashboard.add_window(accuracy=0.59, oos_accuracy=0.55, window=1)
  html = dashboard.render_html()
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class WindowResult:
    window: int
    accuracy: float
    oos_accuracy: float = 0.0
    retrained: bool = False
    drifted: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class WalkForwardDashboard:
    """Production HTML dashboard for walk-forward validation."""

    def __init__(self):
        self._windows: list[WindowResult] = []

    def add_window(
        self,
        accuracy: float,
        oos_accuracy: float = 0.0,
        window: int = 0,
        retrained: bool = False,
        drifted: bool = False,
    ):
        self._windows.append(
            WindowResult(
                window=window or len(self._windows) + 1,
                accuracy=accuracy,
                oos_accuracy=oos_accuracy,
                retrained=retrained,
                drifted=drifted,
            )
        )

    def render_html(self) -> str:
        """Render HTML dashboard with Chart.js visualization."""
        windows_data = [asdict(w) for w in self._windows]
        accs = [w.accuracy for w in self._windows]
        oos = [w.oos_accuracy for w in self._windows if w.oos_accuracy > 0]
        drifts = sum(1 for w in self._windows if w.drifted)
        retraining = sum(1 for w in self._windows if w.retrained)
        avg_acc = sum(accs)/len(accs) if accs else 0.0
        avg_oos = sum(oos)/len(oos) if oos else None

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Walk-Forward Validation Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .card {{ background: white; border-radius: 8px; padding: 20px; margin: 10px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 20px 0; }}
        .stat {{ text-align: center; padding: 15px; background: #f8f9fa; border-radius: 6px; }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #333; }}
        .stat-label {{ font-size: 12px; color: #666; margin-top: 5px; }}
        .stat-good {{ color: #28a745; }}
        .stat-warn {{ color: #ffc107; }}
        .stat-bad {{ color: #dc3545; }}
        .chart-container {{ position: relative; height: 400px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        .drift {{ background: #fff3cd; }}
        .retrain {{ background: #d4edda; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Walk-Forward Validation Dashboard</h1>
        <p>Last updated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}</p>

        <div class="stats">
            <div class="stat">
                <div class="stat-value">{len(self._windows)}</div>
                <div class="stat-label">Total Windows</div>
            </div>
            <div class="stat">
                <div class="stat-value {'stat-good' if avg_acc > 0.55 else 'stat-warn' if avg_acc > 0.50 else 'stat-bad'}">{avg_acc:.1%}</div>
                <div class="stat-label">Avg Accuracy</div>
            </div>
            <div class="stat">
                <div class="stat-value {'stat-good' if avg_oos and avg_oos > 0.50 else 'stat-warn' if avg_oos and avg_oos > 0.45 else 'stat-bad'}">{f"{avg_oos:.1%}" if avg_oos is not None else 'N/A'}</div>
                <div class="stat-label">Avg OOS Accuracy</div>
            </div>
            <div class="stat">
                <div class="stat-value {'stat-good' if drifts == 0 else 'stat-warn' if drifts < 3 else 'stat-bad'}">{drifts}</div>
                <div class="stat-label">Drift Events</div>
            </div>
        </div>

        <div class="card">
            <h2>Accuracy Over Windows</h2>
            <div class="chart-container">
                <canvas id="accuracyChart"></canvas>
            </div>
        </div>

        <div class="card">
            <h2>Window Details</h2>
            <table>
                <thead>
                    <tr>
                        <th>Window</th>
                        <th>Accuracy</th>
                        <th>OOS Accuracy</th>
                        <th>Status</th>
                        <th>Timestamp</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(f'<tr class="{"drift" if w.drifted else "retrain" if w.retrained else ""}"><td>W{w.window}</td><td>{w.accuracy:.1%}</td><td>{f"{w.oos_accuracy:.1%}" if w.oos_accuracy else "-"}</td><td>{"DRIFT" if w.drifted else "RETRAIN" if w.retrained else "OK"}</td><td>{w.timestamp[:19]}</td></tr>' for w in self._windows)}
                </tbody>
            </table>
        </div>
    </div>

    <script>
        const ctx = document.getElementById('accuracyChart').getContext('2d');
        const windows = {windows_data};
        new Chart(ctx, {{
            type: 'line',
            data: {{
                labels: windows.map(w => 'W' + w.window),
                datasets: [{{
                    label: 'In-Sample Accuracy',
                    data: windows.map(w => w.accuracy * 100),
                    borderColor: '#007bff',
                    backgroundColor: 'rgba(0, 123, 255, 0.1)',
                    tension: 0.3,
                    fill: true
                }}, {{
                    label: 'OOS Accuracy',
                    data: windows.map(w => w.oos_accuracy * 100),
                    borderColor: '#28a745',
                    backgroundColor: 'rgba(40, 167, 69, 0.1)',
                    tension: 0.3,
                    fill: true
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    y: {{
                        beginAtZero: false,
                        min: 40,
                        max: 70,
                        title: {{ display: true, text: 'Accuracy (%)' }}
                    }}
                }},
                plugins: {{
                    annotation: {{
                        annotations: {{
                            line1: {{
                                type: 'line',
                                yMin: 50,
                                yMax: 50,
                                borderColor: 'red',
                                borderDash: [5, 5],
                                label: {{ content: 'Min Target', enabled: true }}
                            }}
                        }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>"""
        return html

    def save_html(self, path: str = "walk_forward_dashboard.html"):
        """Save HTML dashboard to file."""
        html = self.render_html()
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info("walk_forward_dashboard.saved", path=path)
