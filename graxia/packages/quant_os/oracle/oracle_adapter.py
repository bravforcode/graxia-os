"""Phase BE-P5 — Oracle adapter base class."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class OracleConfig:
    name: str
    version: str
    framework: str  # vectorbt, backtesting_py, backtrader
    environment_path: str = ""
    has_real_strategy: bool = False


class OracleAdapter(ABC):
    """Base class for oracle adapters."""

    def __init__(self, config: OracleConfig):
        self._config = config
        self._signals: list[dict] = []
        self._trades: list[dict] = []

    @abstractmethod
    def load_strategy(self, strategy_ir: dict) -> bool:
        """Load strategy from IR. Returns True if real logic loaded."""
        pass

    @abstractmethod
    def run(self, data: list[dict]) -> list[dict]:
        """Run strategy on data. Returns list of signals."""
        pass

    def get_signals(self) -> list[dict]:
        return self._signals.copy()

    def get_trades(self) -> list[dict]:
        return self._trades.copy()

    def get_config(self) -> OracleConfig:
        return self._config

    def is_stub(self) -> bool:
        """Check if adapter is a stub (no real strategy)."""
        return not self._config.has_real_strategy


class StubOracle(OracleAdapter):
    """Stub oracle for testing. Returns no signals."""

    def __init__(self):
        super().__init__(
            OracleConfig(
                name="stub",
                version="0.0.1",
                framework="none",
                has_real_strategy=False,
            )
        )

    def load_strategy(self, strategy_ir: dict) -> bool:
        return False

    def run(self, data: list[dict]) -> list[dict]:
        return []
