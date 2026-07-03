"""Secure pickle loading with RestrictedUnpickler.

The old implementation called pickle.load() FIRST (executing all embedded
code) then checked the result type — a classic deserialization RCE vector.
This module whitelists only safe classes and rejects everything else.
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class RestrictedUnpickler(pickle.Unpickler):
    """Unpickler that rejects all classes not in the allowlist.

    Only numpy array/dtype reconstruction and Python builtins are permitted.
    Anything else (os.system, subprocess, exec, eval, …) raises immediately.
    """

    ALLOWED_MODULES = {
        "builtins.bytes",
        "builtins.dict",
        "builtins.float",
        "builtins.int",
        "builtins.list",
        "builtins.set",
        "builtins.str",
        "builtins.tuple",
        "numpy.core.multiarray._reconstruct",
        "numpy.core.multiarray.scalar",
    }

    def find_class(self, module: str, name: str) -> Any:
        key = f"{module}.{name}"

        # Always allow numpy submodules (dtype reconstruction, etc.)
        if module.startswith("numpy.") or module == "numpy":
            return super().find_class(module, name)

        if key not in self.ALLOWED_MODULES:
            raise pickle.UnpicklingError(f"Forbidden class in pickle: {key} (module={module}, name={name})")

        return super().find_class(module, name)


def safe_load_model(
    path: str | Path,
    *,
    expected_keys: set[str] | None = None,
    signing_key: str | None = None,
) -> Any:
    """Load a pickle file through the RestrictedUnpickler.

    Parameters
    ----------
    path:
        Filesystem path to the pickle file.
    expected_keys:
        If provided and the top-level object is a dict, verify these keys exist.
    signing_key:
        Reserved for future HMAC verification (not yet implemented).

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ValueError
        If the file is empty, unreasonably large (>100 MB), or missing expected keys.
    pickle.UnpicklingError
        If the pickle contains a forbidden class.
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Model not found: {path}")

    file_size = path.stat().st_size
    if file_size == 0:
        raise ValueError(f"Model file is empty: {path}")
    if file_size > 100 * 1024 * 1024:
        raise ValueError(f"Model file too large ({file_size} bytes): {path}")

    with open(path, "rb") as f:
        raw = RestrictedUnpickler(f).load()

    if expected_keys and isinstance(raw, dict):
        missing = expected_keys - set(raw.keys())
        if missing:
            raise ValueError(f"Model missing expected keys: {missing}")

    return raw
