"""Phase BE-P7 — EURUSD event calendar."""
from dataclasses import dataclass


@dataclass
class EconomicEvent:
    event_name: str
    country: str
    currency: str
    typical_impact: str  # HIGH, MEDIUM, LOW
    typical_frequency: str  # monthly, quarterly, etc.


class EURUSDEventCalendar:
    """EURUSD economic event mapping."""

    def __init__(self):
        self._events = [
            EconomicEvent("NFP", "US", "USD", "HIGH", "monthly"),
            EconomicEvent("FOMC", "US", "USD", "HIGH", "8x/year"),
            EconomicEvent("CPI", "US", "USD", "HIGH", "monthly"),
            EconomicEvent("GDP", "US", "USD", "HIGH", "quarterly"),
            EconomicEvent("ECB_RATE", "EU", "EUR", "HIGH", "6x/year"),
            EconomicEvent("ECB_PRESS_CONF", "EU", "EUR", "HIGH", "6x/year"),
            EconomicEvent("CPI_EU", "EU", "EUR", "HIGH", "monthly"),
            EconomicEvent("GDP_EU", "EU", "EUR", "HIGH", "quarterly"),
            EconomicEvent("PMI_US", "US", "USD", "MEDIUM", "monthly"),
            EconomicEvent("PMI_EU", "EU", "EUR", "MEDIUM", "monthly"),
            EconomicEvent("RETAIL_SALES_US", "US", "USD", "MEDIUM", "monthly"),
            EconomicEvent("UNEMPLOYMENT_US", "US", "USD", "MEDIUM", "monthly"),
        ]

    def get_events(self) -> list[EconomicEvent]:
        return self._events.copy()

    def get_high_impact(self) -> list[EconomicEvent]:
        return [e for e in self._events if e.typical_impact == "HIGH"]

    def get_by_currency(self, currency: str) -> list[EconomicEvent]:
        return [e for e in self._events if e.currency == currency]
