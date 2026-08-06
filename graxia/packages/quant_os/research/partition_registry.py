"""H/I scope partition for Direction I (spec §1.8, A17).

Mechanism families owned by the parallel Direction H must not be
re-commended by Direction I mining/taxonomy without structural
justification. check_partition() is consumed by P1 ingest and P2
classification.
"""

from __future__ import annotations

PARTITION_RULES: list[dict] = [
    {
        "status": "CLOSED",
        "owner": "H",
        "match": {
            "mechanism": {"trend_continuity", "breakout_momentum_continuity"},
            "symbols": {"USDCAD", "USDCHF", "AUDUSD", "NZDUSD"},
            "timeframes": {"H1"},
        },
        "note": "Direction H trial 9001 REJECTED (t=-8.2..-17.4, measured costs). No re-test.",
    },
    {
        "status": "WATCH",
        "owner": "H",
        "match": {
            "mechanism": {"rsi_mean_reversion", "rsi_mr"},
            "symbols": {"USDCAD", "USDCHF", "AUDUSD", "NZDUSD"},
            "timeframes": {"H1"},
        },
        "note": "Direction H trial 9002 FROZEN, in-flight. Absorb verdict as citation when resolved.",
    },
    {
        "status": "WATCH",
        "owner": "H",
        "match": {
            "mechanism": {"tf_probe_family", "session_breakout", "breakout"},
            "symbols": {"EURUSD"},
            "timeframes": {"H4"},
        },
        "note": "EURUSD H4 TF-probe gross Sharpe 3.46 — waits for Sub-project B Direction H decision (tier0 spec §11.3).",
    },
]


def check_partition(mechanism: str, symbol: str, timeframe: str) -> dict:
    m = mechanism.lower().replace(" ", "_")
    s = symbol.upper()
    tf = timeframe.upper()
    for rule in PARTITION_RULES:
        match = rule["match"]
        if (
            m in match.get("mechanism", set())
            and s in match.get("symbols", set())
            and tf in match.get("timeframes", set())
        ):
            return {"status": rule["status"], "owner": rule["owner"], "note": rule["note"]}
    return {"status": "FREE", "owner": None, "note": ""}
