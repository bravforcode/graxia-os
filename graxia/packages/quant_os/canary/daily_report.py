"""Phase BE-P10 — Daily campaign reporting."""
from dataclasses import dataclass


@dataclass
class DailyReport:
    date: str = ""
    health: str = "healthy"
    blocks: int = 0
    signals: int = 0
    orders: int = 0
    fills: int = 0
    slippage_avg: float = 0.0
    spread_avg: float = 0.0
    reconciliation_status: str = "reconciled"
    incidents: int = 0
    unresolved_incidents: int = 0
    
    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "health": self.health,
            "blocks": self.blocks,
            "signals": self.signals,
            "orders": self.orders,
            "fills": self.fills,
            "slippage_avg": self.slippage_avg,
            "spread_avg": self.spread_avg,
            "reconciliation_status": self.reconciliation_status,
            "incidents": self.incidents,
            "unresolved_incidents": self.unresolved_incidents,
        }
    
    def to_markdown(self) -> str:
        lines = [
            f"# Daily Report: {self.date}",
            "",
            f"**Health:** {self.health}",
            f"**Blocks:** {self.blocks}",
            f"**Signals:** {self.signals}",
            f"**Orders:** {self.orders}",
            f"**Fills:** {self.fills}",
            f"**Avg Slippage:** {self.slippage_avg:.4f}",
            f"**Avg Spread:** {self.spread_avg:.4f}",
            f"**Reconciliation:** {self.reconciliation_status}",
            f"**Incidents:** {self.incidents} ({self.unresolved_incidents} unresolved)",
        ]
        return "\n".join(lines)


class DailyReporter:
    """Collect and report daily campaign metrics."""
    
    def __init__(self):
        self._reports: list[DailyReport] = []
    
    def add_report(self, report: DailyReport) -> None:
        self._reports.append(report)
    
    def get_reports(self) -> list[DailyReport]:
        return self._reports.copy()
    
    def get_latest(self) -> DailyReport | None:
        return self._reports[-1] if self._reports else None
