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
    compression_ratio: float = 0.0
    cache_hit_rate: float = 0.0
    quality_gate_failures: int = 0
    auto_escalations: int = 0
    stale_context_incidents: int = 0


@dataclass
class TokenRoiResult:
    tokens_saved: int
    retry_cost: int
    correction_cost: int
    quality_penalty: int
    escalation_penalty: int
    stale_context_penalty: int
    cache_credit: int
    net_roi: int
    profitable: bool
    recommendation: str
    compression_ratio: float
    cache_hit_rate: float
    quality_gate_failures: int
    auto_escalations: int
    stale_context_incidents: int


def evaluate_token_roi(data: TokenRoiInput) -> TokenRoiResult:
    retry_cost = data.retry_count * data.retry_token_cost
    correction_cost = data.human_correction_count * data.human_correction_cost
    quality_penalty = max(0, data.quality_gate_failures) * 100
    if not data.quality_gate_passed:
        quality_penalty += max(data.tokens_saved, 500)
    if data.critical_context_lost:
        quality_penalty += max(data.tokens_saved, 1000)
    escalation_penalty = max(0, data.auto_escalations) * 75
    stale_context_penalty = max(0, data.stale_context_incidents) * 200
    cache_hit_rate = min(max(data.cache_hit_rate, 0.0), 1.0)
    compression_ratio = min(max(data.compression_ratio, 0.0), 1.0)
    cache_credit = int(data.tokens_saved * cache_hit_rate * 0.1)
    compression_penalty = 100 if compression_ratio > 0.85 else 0

    net_roi = (
        data.tokens_saved
        + cache_credit
        - retry_cost
        - correction_cost
        - quality_penalty
        - escalation_penalty
        - stale_context_penalty
        - compression_penalty
    )
    profitable = net_roi > 0 and data.quality_gate_passed and not data.critical_context_lost
    recommendation = "keep"
    if not profitable:
        recommendation = "disable_or_escalate"
    elif (
        retry_cost + correction_cost > data.tokens_saved // 2
        or data.quality_gate_failures > 0
        or data.stale_context_incidents > 0
        or compression_ratio > 0.85
    ):
        recommendation = "review_compression"
    elif cache_hit_rate < 0.2 and data.tokens_saved > 0:
        recommendation = "improve_cache"

    return TokenRoiResult(
        tokens_saved=data.tokens_saved,
        retry_cost=retry_cost,
        correction_cost=correction_cost,
        quality_penalty=quality_penalty,
        escalation_penalty=escalation_penalty,
        stale_context_penalty=stale_context_penalty,
        cache_credit=cache_credit,
        net_roi=net_roi,
        profitable=profitable,
        recommendation=recommendation,
        compression_ratio=compression_ratio,
        cache_hit_rate=cache_hit_rate,
        quality_gate_failures=max(0, data.quality_gate_failures),
        auto_escalations=max(0, data.auto_escalations),
        stale_context_incidents=max(0, data.stale_context_incidents),
    )
