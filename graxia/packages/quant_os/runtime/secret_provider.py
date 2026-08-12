"""Phase BE-P0 — Secret provider. Never returns secrets to logs."""
from dataclasses import dataclass
from pathlib import Path
import os


@dataclass
class SecretRef:
    """Reference to a secret, not the secret itself."""
    name: str
    source: str  # "env", "file", "keychain"
    env_var: str = ""
    file_path: str = ""


class SecretProvider:
    """Provides secrets from environment or file references."""

    def __init__(self, references: dict[str, SecretRef] = None):
        self._references = references or {}
        self._cache: dict[str, str] = {}

    def add_reference(self, name: str, ref: SecretRef) -> None:
        self._references[name] = ref

    def get_secret(self, name: str) -> str:
        """Get secret value. Never logged."""
        if name in self._cache:
            return self._cache[name]

        ref = self._references.get(name)
        if ref is None:
            raise ValueError(f"Secret reference '{name}' not configured")

        value = self._resolve(ref)
        self._cache[name] = value
        return value

    def _resolve(self, ref: SecretRef) -> str:
        """Resolve secret from its source."""
        if ref.source == "env":
            value = os.environ.get(ref.env_var, "")
            if not value:
                raise ValueError(f"Environment variable {ref.env_var} not set")
            return value
        elif ref.source == "file":
            path = Path(ref.file_path)
            if not path.exists():
                raise ValueError(f"Secret file {ref.file_path} not found")
            return path.read_text().strip()
        else:
            raise ValueError(f"Unknown secret source: {ref.source}")

    def __repr__(self) -> str:
        """Never expose secret values in repr."""
        return f"SecretProvider(refs={list(self._references.keys())})"

    def __str__(self) -> str:
        """Never expose secret values in str."""
        return self.__repr__()
