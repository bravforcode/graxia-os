"""Token ROI calculation for context optimization."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TokenRoiInput:
    tokens_saved: int
    retry_count: int
    retry_token_cost: int
    human_correction_count: int
    human_correction_cost: int
    quality_gate_passed: bool
    critical_context_lost: bool = False


@dataclass
class TokenRoiResult:
    retry_cost: int
    correction_cost: int
    net_roi: int
    profitable: bool
    recommendation: str


def evaluate_token_roi(data: TokenRoiInput) -> TokenRoiResult:
    retry_cost = data.retry_count * data.retry_token_cost
    correction_cost = data.human_correction_count * data.human_correction_cost
    quality_penalty = 0
    if not data.quality_gate_passed:
        quality_penalty += max(data.tokens_saved, 500)
    if data.critical_context_lost:
        quality_penalty += max(data.tokens_saved, 1000)

    net_roi = data.tokens_saved - retry_cost - correction_cost - quality_penalty
    profitable = net_roi > 0 and data.quality_gate_passed and not data.critical_context_lost
    recommendation = "keep"
    if not profitable:
        recommendation = "disable_or_escalate"
    elif retry_cost + correction_cost > data.tokens_saved // 2:
        recommendation = "review_compression"

    return TokenRoiResult(
        retry_cost=retry_cost,
        correction_cost=correction_cost,
        net_roi=net_roi,
        profitable=profitable,
        recommendation=recommendation,
    )
