"""Guard: verify symbol is XAUUSD only."""
def verify_symbol(symbol: str) -> bool:
    return symbol == "XAUUSD"
