"""
Heuristic fallback scorer — used when LLM is unavailable.
Returns same structure as LLM scorer JSON output.
"""
from __future__ import annotations


def _extract_prize_number(prize_amount: str | None) -> float:
    if not prize_amount:
        return 0.0
    import re
    nums = re.findall(r"[\d,]+", prize_amount.replace(",", ""))
    if nums:
        return float(nums[0])
    return 0.0


def score_heuristic(opportunity_data: dict, weights: dict) -> dict:
    t = opportunity_data.get("type", "")
    platform = (opportunity_data.get("source_platform") or "").lower()
    location = opportunity_data.get("location_type", "")
    tags = [x.lower() for x in (opportunity_data.get("tags") or [])]
    prize_num = _extract_prize_number(opportunity_data.get("prize_amount"))
    days = opportunity_data.get("days_until_deadline")

    # money_score
    if prize_num > 500000:
        money_score = 10
    elif prize_num > 100000:
        money_score = 8
    elif prize_num > 50000:
        money_score = 7
    elif prize_num > 10000:
        money_score = 5
    elif prize_num > 0:
        money_score = 3
    else:
        money_score = 4

    # brand_score
    if platform in ("devpost", "f6s"):
        brand_score = 7
    elif location == "global":
        brand_score = 8
    elif location == "asean":
        brand_score = 6
    elif location == "thailand":
        brand_score = 5
    else:
        brand_score = 4

    # startup_score
    if t in ("accelerator", "fellowship"):
        startup_score = 9
    elif t == "competition" and "startup" in tags:
        startup_score = 8
    elif t == "hackathon":
        startup_score = 6
    elif t == "grant":
        startup_score = 5
    elif t == "freelance":
        startup_score = 2
    else:
        startup_score = 4

    # effort_score (higher = more effort = inversed in total)
    if t == "freelance":
        effort_score = 3
    elif t == "competition":
        effort_score = 6
    elif t in ("accelerator", "fellowship"):
        effort_score = 8
    else:
        effort_score = 5

    # network_score
    if t in ("accelerator", "fellowship"):
        network_score = 8
    elif location == "global":
        network_score = 7
    elif location == "asean":
        network_score = 6
    else:
        network_score = 4

    w_money = weights.get("money", 0.30)
    w_brand = weights.get("brand", 0.20)
    w_startup = weights.get("startup_relevance", 0.25)
    w_network = weights.get("network", 0.10)
    w_effort = weights.get("effort_inverse", 0.15)

    total = (
        money_score * w_money
        + brand_score * w_brand
        + startup_score * w_startup
        + network_score * w_network
        + (10 - effort_score) * w_effort
    )

    if total >= 7.0 or (total >= 5.5 and days is not None and days < 7):
        action_priority = "do_now"
    elif total < 4.0:
        action_priority = "skip"
    else:
        action_priority = "queue"

    if days is not None and days < 3:
        deadline_urgency = "critical"
    elif days is not None and days < 7:
        deadline_urgency = "soon"
    elif days is not None:
        deadline_urgency = "comfortable"
    else:
        deadline_urgency = "none"

    return {
        "money_score": money_score,
        "brand_score": brand_score,
        "network_score": network_score,
        "startup_score": startup_score,
        "effort_score": effort_score,
        "total_score": round(total, 2),
        "action_priority": action_priority,
        "scoring_rationale": "[Heuristic score — AI unavailable at time of scoring]",
        "red_flags": [],
        "deadline_urgency": deadline_urgency,
    }
