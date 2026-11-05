"""Canonical email identity helpers shared by auth and persistence."""


def normalize_email(email: str) -> str:
    """Trim and case-fold an email before comparing or storing it."""
    if not isinstance(email, str):
        raise TypeError("email must be a string")
    normalized = email.strip().lower()
    if not normalized:
        raise ValueError("email must not be empty")
    return normalized
