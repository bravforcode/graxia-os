"""Phase 5 verdict tests."""

from graxia.packages.quant_os.validation.phase_5_verdict import evaluate_phase5


def test_all_pass():
    v = evaluate_phase5(
        deflated_sharpe=1.5,
        pbo=0.02,
        cost_survives=True,
        stability_score=0.8,
        bootstrap_lower=0.01,
        oos_positive=True,
    )
    assert v.verdict == "PASS_TO_6"
    assert len(v.failed_checks) == 0
    assert len(v.passed_checks) == 6


def test_deflated_sharpe_fail():
    v = evaluate_phase5(
        deflated_sharpe=-0.5,
        pbo=0.02,
        cost_survives=True,
        stability_score=0.8,
        bootstrap_lower=0.01,
        oos_positive=True,
    )
    assert v.verdict == "CONDITIONAL_PASS"
    assert any("deflated_sharpe" in c for c in v.failed_checks)


def test_multiple_failures():
    v = evaluate_phase5(
        deflated_sharpe=-1.0,
        pbo=0.5,
        cost_survives=False,
        stability_score=0.1,
        bootstrap_lower=-0.01,
        oos_positive=False,
    )
    assert v.verdict == "NO_GO"
    assert len(v.failed_checks) > 2
