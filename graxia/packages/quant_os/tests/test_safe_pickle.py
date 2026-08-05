"""Tests for core.safe_pickle — RestrictedUnpickler allowlist coverage.

model_registry.py pickles whole fitted estimator objects (LGBMClassifier,
XGBClassifier, CatBoostClassifier, sklearn) and loads them back through
safe_load_model(). These tests confirm the allowlist actually accepts the
model formats the codebase produces, not just numpy/builtins in isolation.
"""

import pickle

import numpy as np
import pytest

from graxia.packages.quant_os.core.safe_pickle import safe_load_model, sign_model_file

SIGNING_KEY = "test-signing-key-do-not-use-in-prod"


def _make_xy():
    rng = np.random.default_rng(42)
    X = rng.standard_normal((60, 4))
    y = (X[:, 0] + X[:, 1] > 0).astype(int)
    return X, y


class TestNumpyAndBuiltins:
    def test_round_trip_dict(self, tmp_path):
        path = tmp_path / "dict.pkl"
        payload = {"a": 1, "b": [1, 2, 3], "c": np.array([1.0, 2.0, 3.0])}
        with open(path, "wb") as f:
            pickle.dump(payload, f)

        loaded = safe_load_model(path)
        assert loaded["a"] == 1
        assert loaded["b"] == [1, 2, 3]
        assert np.array_equal(loaded["c"], payload["c"])

    def test_expected_keys_enforced(self, tmp_path):
        path = tmp_path / "dict.pkl"
        with open(path, "wb") as f:
            pickle.dump({"a": 1}, f)

        with pytest.raises(ValueError, match="missing expected keys"):
            safe_load_model(path, expected_keys={"a", "b"})


class TestRealModelFormats:
    """The formats ml/model_registry.py actually pickles via pickle.dump().

    Real fitted model objects only load in "trusted" mode, which requires a
    valid HMAC signature (see core/safe_pickle.py). Each test signs the
    artifact the same way ModelRegistry.register_model() does.
    """

    def test_lgbm_classifier_round_trip(self, tmp_path):
        lgbm = pytest.importorskip("lightgbm")
        X, y = _make_xy()
        model = lgbm.LGBMClassifier(n_estimators=5, max_depth=2, verbose=-1)
        model.fit(X, y)

        path = tmp_path / "lgbm.pkl"
        with open(path, "wb") as f:
            pickle.dump(model, f)
        sign_model_file(path, SIGNING_KEY)

        loaded = safe_load_model(path, signing_key=SIGNING_KEY)
        assert np.array_equal(loaded.predict(X), model.predict(X))

    def test_xgb_classifier_round_trip(self, tmp_path):
        xgb = pytest.importorskip("xgboost")
        X, y = _make_xy()
        model = xgb.XGBClassifier(n_estimators=5, max_depth=2)
        model.fit(X, y)

        path = tmp_path / "xgb.pkl"
        with open(path, "wb") as f:
            pickle.dump(model, f)
        sign_model_file(path, SIGNING_KEY)

        loaded = safe_load_model(path, signing_key=SIGNING_KEY)
        assert np.array_equal(loaded.predict(X), model.predict(X))

    def test_catboost_classifier_round_trip(self, tmp_path):
        catboost = pytest.importorskip("catboost")
        X, y = _make_xy()
        model = catboost.CatBoostClassifier(iterations=5, depth=2, verbose=0)
        model.fit(X, y)

        path = tmp_path / "catboost.pkl"
        with open(path, "wb") as f:
            pickle.dump(model, f)
        sign_model_file(path, SIGNING_KEY)

        loaded = safe_load_model(path, signing_key=SIGNING_KEY)
        assert np.array_equal(loaded.predict(X), model.predict(X))

    def test_sklearn_estimator_round_trip(self, tmp_path):
        from sklearn.linear_model import LogisticRegression

        X, y = _make_xy()
        model = LogisticRegression().fit(X, y)

        path = tmp_path / "sklearn.pkl"
        with open(path, "wb") as f:
            pickle.dump(model, f)
        sign_model_file(path, SIGNING_KEY)

        loaded = safe_load_model(path, signing_key=SIGNING_KEY)
        assert np.array_equal(loaded.predict(X), model.predict(X))

    def test_sklearn_rejected_without_signing_key(self, tmp_path):
        """Regression guard: the strict/default path must still reject real
        model objects when no signing_key is supplied at all."""
        from sklearn.linear_model import LogisticRegression

        X, y = _make_xy()
        model = LogisticRegression().fit(X, y)

        path = tmp_path / "sklearn_unsigned.pkl"
        with open(path, "wb") as f:
            pickle.dump(model, f)

        with pytest.raises(pickle.UnpicklingError, match="Forbidden class"):
            safe_load_model(path)

    def test_sklearn_rejected_missing_signature_file(self, tmp_path):
        """A signing_key is supplied but the .sig sidecar was never written."""
        from sklearn.linear_model import LogisticRegression

        X, y = _make_xy()
        model = LogisticRegression().fit(X, y)

        path = tmp_path / "sklearn_nosig.pkl"
        with open(path, "wb") as f:
            pickle.dump(model, f)

        with pytest.raises(ValueError, match="signature"):
            safe_load_model(path, signing_key=SIGNING_KEY)

    def test_sklearn_rejected_tampered_after_signing(self, tmp_path):
        """A file modified after signing must fail signature verification."""
        from sklearn.linear_model import LogisticRegression

        X, y = _make_xy()
        model = LogisticRegression().fit(X, y)

        path = tmp_path / "sklearn_tampered.pkl"
        with open(path, "wb") as f:
            pickle.dump(model, f)
        sign_model_file(path, SIGNING_KEY)

        with open(path, "ab") as f:
            f.write(b"\x00")

        with pytest.raises(ValueError, match="signature"):
            safe_load_model(path, signing_key=SIGNING_KEY)

    def test_sklearn_rejected_with_wrong_signing_key(self, tmp_path):
        from sklearn.linear_model import LogisticRegression

        X, y = _make_xy()
        model = LogisticRegression().fit(X, y)

        path = tmp_path / "sklearn_wrongkey.pkl"
        with open(path, "wb") as f:
            pickle.dump(model, f)
        sign_model_file(path, SIGNING_KEY)

        with pytest.raises(ValueError, match="signature"):
            safe_load_model(path, signing_key="a-different-key")


class TestForbiddenClasses:
    """Confirms the allowlist actually rejects dangerous classes."""

    def test_os_system_call_rejected(self, tmp_path):
        path = tmp_path / "evil.pkl"

        class _Evil:
            def __reduce__(self):
                import os

                return (os.system, ("echo pwned",))

        with open(path, "wb") as f:
            pickle.dump(_Evil(), f)

        with pytest.raises(pickle.UnpicklingError, match="Forbidden class"):
            safe_load_model(path)

    def test_subprocess_rejected(self, tmp_path):
        path = tmp_path / "evil2.pkl"

        class _Evil:
            def __reduce__(self):
                import subprocess

                return (subprocess.Popen, (["echo", "pwned"],))

        with open(path, "wb") as f:
            pickle.dump(_Evil(), f)

        with pytest.raises(pickle.UnpicklingError, match="Forbidden class"):
            safe_load_model(path)

    def test_os_system_rejected_even_with_valid_signing_key(self, tmp_path):
        """Defense in depth: a valid signature must not unlock the explicit
        forbidden-key blocklist, even in trusted mode."""
        path = tmp_path / "evil_signed.pkl"

        class _Evil:
            def __reduce__(self):
                import os

                return (os.system, ("echo pwned",))

        with open(path, "wb") as f:
            pickle.dump(_Evil(), f)
        sign_model_file(path, SIGNING_KEY)

        with pytest.raises(pickle.UnpicklingError, match="Forbidden class"):
            safe_load_model(path, signing_key=SIGNING_KEY)


class TestFileGuards:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            safe_load_model(tmp_path / "does_not_exist.pkl")

    def test_empty_file_raises(self, tmp_path):
        path = tmp_path / "empty.pkl"
        path.write_bytes(b"")
        with pytest.raises(ValueError, match="empty"):
            safe_load_model(path)
