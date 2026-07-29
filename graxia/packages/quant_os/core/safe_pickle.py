"""Secure pickle loading with RestrictedUnpickler.

The old implementation called pickle.load() FIRST (executing all embedded
code) then checked the result type — a classic deserialization RCE vector.
This module whitelists only safe classes and rejects everything else.

Also provides HMAC signing for pickle files so that trusted model objects
(sklearn, LGBM, XGBoost, CatBoost) can be loaded only when a valid
signature sidecar (``<path>.sig``) is present.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import pickle
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["RestrictedUnpickler", "TrustedUnpickler", "sign_model_file", "safe_load_model"]


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
        "numpy._core.multiarray._reconstruct",
        "numpy._core.multiarray.scalar",
    }

    def find_class(self, module: str, name: str) -> Any:
        key = f"{module}.{name}"

        # Allow specific numpy classes for dtype reconstruction
        # (both legacy numpy.core.multiarray and numpy._core.multiarray for numpy 2.x)
        if module == "numpy" and name in ("ndarray", "dtype"):
            return super().find_class(module, name)
        if module in ("numpy.core.multiarray", "numpy._core.multiarray") and name in ("_reconstruct", "scalar"):
            return super().find_class(module, name)
        if module == "numpy.ma.core" and name in ("MaskedArray",):
            return super().find_class(module, name)

        if key not in self.ALLOWED_MODULES:
            raise pickle.UnpicklingError(f"Forbidden class in pickle: {key} (module={module}, name={name})")

        return super().find_class(module, name)


# Modules allowed only in trusted (signed) mode
_TRUSTED_MODULE_PREFIXES = (
    "sklearn.",
    "lightgbm.",
    "xgboost.",
    "catboost.",
    "joblib.",
    "copyreg.",
)


class TrustedUnpickler(pickle.Unpickler):
    """Unpickler for signed pickle files — allows ML model classes.

    Permits classes from sklearn, lightgbm, xgboost, catboost, and their
    dependencies when the pickle file has a valid HMAC signature.
    Dangerous classes (os, subprocess, etc.) are still rejected.
    """

    FORBIDDEN_PREFIXES = ("os.", "subprocess.", "posixpath.", "ntpath.", "shutil.")
    TRUSTED_PREFIXES = _TRUSTED_MODULE_PREFIXES
    NUMPY_ALLOWLIST = {
        ("numpy", "ndarray"),
        ("numpy", "dtype"),
        ("numpy.core.multiarray", "_reconstruct"),
        ("numpy.core.multiarray", "scalar"),
        ("numpy._core.multiarray", "_reconstruct"),
        ("numpy._core.multiarray", "scalar"),
        ("numpy.ma.core", "MaskedArray"),
    }
    BUILTIN_ALLOWLIST = {
        "builtins.bytes",
        "builtins.bytearray",
        "builtins.dict",
        "builtins.float",
        "builtins.int",
        "builtins.list",
        "builtins.set",
        "builtins.str",
        "builtins.tuple",
        "builtins.range",
        "builtins.slice",
        "builtins.property",
        "builtins.staticmethod",
        "builtins.classmethod",
        "collections.defaultdict",
        "collections.OrderedDict",
        "copyreg._reconstructor",
    }

    def find_class(self, module: str, name: str) -> Any:
        # Block dangerous modules even in trusted mode
        for prefix in self.FORBIDDEN_PREFIXES:
            if module.startswith(prefix):
                raise pickle.UnpicklingError(
                    f"Forbidden class in pickle: {module}.{name} (module={module}, name={name})"
                )
        # Allow trusted ML modules
        for prefix in self.TRUSTED_PREFIXES:
            if module.startswith(prefix):
                return super().find_class(module, name)
        # Allow numpy/builtins
        if (module, name) in self.NUMPY_ALLOWLIST:
            return super().find_class(module, name)
        if f"{module}.{name}" in self.BUILTIN_ALLOWLIST:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"Forbidden class in pickle: {module}.{name} (module={module}, name={name})")


def _compute_hmac(path: Path, key: str) -> str:
    """Compute HMAC-SHA256 hex digest of a file's contents."""
    h = hmac.new(key.encode(), digestmod=hashlib.sha256)
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def sign_model_file(path: str | Path, signing_key: str) -> None:
    """Write an HMAC signature sidecar (``<path>.sig``) for a pickle file.

    This is called by ModelRegistry.register_model() after pickling.
    The signature binds the file content to the key so that tampering
    or unsigned loading is detectable.
    """
    path = Path(path)
    sig_path = path.with_suffix(path.suffix + ".sig")
    digest = _compute_hmac(path, signing_key)
    sig_path.write_text(digest, encoding="utf-8")


def safe_load_model(
    path: str | Path,
    *,
    expected_keys: set[str] | None = None,
    signing_key: str | None = None,
    allow_unsigned: bool = False,
) -> Any:
    """Load a pickle file through the RestrictedUnpickler.

    Parameters
    ----------
    path:
        Filesystem path to the pickle file.
    expected_keys:
        If provided and the top-level object is a dict, verify these keys exist.
    signing_key:
        If provided, verify the HMAC signature sidecar (``<path>.sig``).
        Real model objects (sklearn, LGBM, etc.) require a valid signature
        to pass the allowlist.
    allow_unsigned:
        RESEARCH/DEV ONLY. When True, permits TrustedUnpickler without
        HMAC-verified signature. Emits a warning on every load.
        MUST be False in production entry points (api/signal_service.py,
        ml/model_registry.py live paths) — model-substitution risk.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ValueError
        If the file is empty, unreasonably large (>100 MB), missing expected keys,
        or signature verification fails.
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

    # HMAC verification (when signing_key is provided)
    if signing_key is not None:
        sig_path = path.with_suffix(path.suffix + ".sig")
        if not sig_path.exists():
            raise ValueError(
                f"signature file not found: {sig_path} — file was not signed " f"or the .sig sidecar was deleted"
            )
        expected_digest = sig_path.read_text(encoding="utf-8").strip()
        actual_digest = _compute_hmac(path, signing_key)
        if not hmac.compare_digest(actual_digest, expected_digest):
            raise ValueError(
                f"signature verification failed for {path} — file may have been "
                f"tampered with or the signing key is incorrect"
            )

    # Select unpickler: signed → TrustedUnpickler (allows ML classes),
    # unsigned + allow_unsigned → TrustedUnpickler with warning,
    # unsigned + !allow_unsigned → RestrictedUnpickler (rejects ML classes).
    unpickler: type[TrustedUnpickler | RestrictedUnpickler]
    if signing_key is not None:
        unpickler = TrustedUnpickler
    elif allow_unsigned:
        import logging

        logging.getLogger(__name__).warning(
            "safe_load_model: loading unsigned model %s — no integrity verification. "
            "Model-substitution risk. Set MODEL_SIGNING_KEY + sign models for production.",
            path.name,
        )
        unpickler = TrustedUnpickler
    else:
        unpickler = RestrictedUnpickler

    with open(path, "rb") as f:
        raw = unpickler(f).load()

    if expected_keys and isinstance(raw, dict):
        missing = expected_keys - set(raw.keys())
        if missing:
            raise ValueError(f"Model missing expected keys: {missing}")

    return raw
