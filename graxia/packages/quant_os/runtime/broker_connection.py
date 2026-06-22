"""Phase BE-P0 — Broker connection with identity verification."""
from dataclasses import dataclass


@dataclass
class BrokerConnection:
    """MT5 broker connection with identity verification."""
    server: str
    login: int
    password: str
    account_mode: str
    account_currency: str

    @classmethod
    def from_mt5(cls, terminal_path: str = "") -> "BrokerConnection":
        """Create connection from MT5 terminal."""
        try:
            import MetaTrader5 as mt5
            if not mt5.initialize(path=terminal_path if terminal_path else None):
                raise ConnectionError("MT5 initialize failed")

            account = mt5.account_info()
            if account is None:
                raise ConnectionError("Failed to get account info")

            return cls(
                server=account.server,
                login=account.login,
                password="",  # Never stored
                account_mode="DEMO" if account.trade_mode == 0 else "LIVE",
                account_currency=account.currency,
            )
        except ImportError:
            raise ConnectionError("MetaTrader5 package not installed")

    def validate_against(self, expected_server: str, expected_login: int,
                         expected_mode: str) -> tuple[bool, str]:
        """Validate connection against expected profile."""
        issues = []

        if self.server != expected_server:
            issues.append(f"server_mismatch: expected={expected_server}, got={self.server}")

        if self.login != expected_login:
            issues.append(f"login_mismatch: expected={expected_login}, got={self.login}")

        if self.account_mode != expected_mode:
            issues.append(f"mode_mismatch: expected={expected_mode}, got={self.account_mode}")

        if issues:
            return False, "; ".join(issues)
        return True, "OK"

    def __repr__(self) -> str:
        """Never expose password."""
        return f"BrokerConnection(server={self.server}, login={self.login}, mode={self.account_mode})"
