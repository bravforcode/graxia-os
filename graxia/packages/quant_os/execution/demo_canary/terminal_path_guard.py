"""Guard: verify terminal path matches approved."""
APPROVED_TERMINAL_PATH_HASH = "ade8f62fe56071266d682245044bcf0aa6c07d2a6a2c52eea0b6f173e2c8cf67"

def verify_terminal_path(terminal_path: str) -> bool:
    """Verify terminal path fingerprint."""
    import hashlib
    path_hash = hashlib.sha256(terminal_path.encode()).hexdigest()
    return path_hash == APPROVED_TERMINAL_PATH_HASH
