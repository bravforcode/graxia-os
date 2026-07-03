"""Runtime capabilities — snapshot of what MT5 can do right now."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RuntimeCapabilities:
    mt5_initialized: bool = False
    terminal_connected: bool = False
    terminal_info: dict = field(default_factory=dict)
    account_info_redacted: dict = field(default_factory=dict)
    server_name: str = ""
    account_currency: str = ""
    symbols_available: list[str] = field(default_factory=list)
    tick_access: bool = False
    bar_access: bool = False
    order_calc_profit: bool = False
    order_calc_margin: bool = False
    positions_visible: bool = False
    orders_visible: bool = False
    history_visible: bool = False
    utc_offset_ms: int = 0
    issues: list[str] = field(default_factory=list)

    @property
    def has_critical_issues(self) -> bool:
        critical = [
            not self.mt5_initialized,
            not self.terminal_connected,
            not self.tick_access,
        ]
        return any(critical)
