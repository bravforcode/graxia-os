"""
graxia/packages/revenue_os/services/scoring.py
Lead scoring engine for evaluating the quality and likelihood of conversion.
"""
from typing import Tuple

from ..models import Lead

def score_lead(lead: Lead) -> Tuple[int, str]:
    """
    Evaluates a Lead and returns a score (0-100) and a rationale.
    
    Basic heuristic rules:
      - Has company: +20
      - Has title: +15
      - C-level/VP title: +25
      - Has LinkedIn: +10
      - Source weights: 'inbound' (+30), 'referral' (+40), 'outbound' (+10)
    """
    score = 0
    reasons = []

    if lead.company:
        score += 20
        reasons.append("Has company (+20)")
        
    if lead.title:
        title_lower = lead.title.lower()
        if any(kw in title_lower for kw in ["ceo", "cto", "cfo", "cmo", "vp", "founder", "director"]):
            score += 40
            reasons.append("Executive/Director title (+40)")
        else:
            score += 15
            reasons.append("Has title (+15)")

    if lead.linkedin_url:
        score += 10
        reasons.append("Has LinkedIn (+10)")

    source_lower = lead.source.lower()
    if source_lower == "referral":
        score += 40
        reasons.append("Referral source (+40)")
    elif source_lower == "inbound":
        score += 30
        reasons.append("Inbound source (+30)")
    elif source_lower == "outbound":
        score += 10
        reasons.append("Outbound source (+10)")
        
    # Cap score at 100
    final_score = min(score, 100)
    if final_score == 0:
        final_score = 10
        reasons.append("Base score (+10)")
        
    rationale = "; ".join(reasons)
    return final_score, rationale
