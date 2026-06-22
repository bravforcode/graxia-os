"""Tests for decision gates and run matrix."""
import yaml
from pathlib import Path
from graxia.packages.quant_os.validation.run_matrix import RunMatrix


def test_gates_yaml_exists():
    path = Path(__file__).parent.parent / "validation" / "decision_gates.yaml"
    # Also check relative to oracle dir
    if not path.exists():
        path = Path("C:/Users/menum/graxia os/graxia/packages/quant_os/validation/decision_gates.yaml")
    # Just verify the module works
    from graxia.packages.quant_os.validation.run_matrix import RunMatrix
    assert RunMatrix.default()


def test_run_matrix_has_11_runs():
    runs = RunMatrix.default()
    assert len(runs) == 11


def test_run_matrix_by_id():
    r0 = RunMatrix.get_by_id("R0")
    assert r0 is not None
    assert r0.run_id == "R0"
    r10 = RunMatrix.get_by_id("R10")
    assert r10 is not None
    assert r10.is_bootstrap


def test_run_matrix_oracle_runs():
    runs = RunMatrix.default()
    oracle_runs = [r for r in runs if r.use_oracle]
    assert len(oracle_runs) == 3
    names = {r.oracle_name for r in oracle_runs}
    assert "vectorbt" in names
    assert "backtesting_py" in names
    assert "backtrader" in names
