from __future__ import annotations

from app.context_engine.token_roi import TokenRoiInput, evaluate_token_roi


def test_token_roi_penalizes_retry_heavy_compression() -> None:
    result = evaluate_token_roi(
        TokenRoiInput(
            tokens_saved=1200,
            retry_count=2,
            retry_token_cost=250,
            human_correction_count=1,
            human_correction_cost=150,
            quality_gate_passed=True,
        )
    )
    assert result.net_roi == 550
    assert result.profitable is True
    assert result.recommendation == "review_compression"


def test_token_roi_rejects_critical_context_loss() -> None:
    result = evaluate_token_roi(
        TokenRoiInput(
            tokens_saved=2000,
            retry_count=1,
            retry_token_cost=200,
            human_correction_count=0,
            human_correction_cost=0,
            quality_gate_passed=False,
            critical_context_lost=True,
        )
    )
    assert result.profitable is False
    assert result.recommendation == "disable_or_escalate"
