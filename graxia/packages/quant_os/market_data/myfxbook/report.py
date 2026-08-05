"""Render the nightly collection report as markdown (auditable artifact)."""


def _status(result: dict) -> str:
    if result.get("error"):
        return "ERROR"
    return "PASS" if result.get("filter_pass") else "FAIL"


def render_markdown(results: list[dict], run_date: str) -> str:
    n_pass = sum(1 for r in results if r.get("filter_pass") and not r.get("error"))
    n_risk = sum(1 for r in results if r.get("martingale_risky") and not r.get("error"))
    lines = [f"# Myfxbook Collection — {run_date}", ""]
    lines.append(f"{len(results)} accounts, {n_pass} passed filter, {n_risk} martingale-risk")
    lines.append("")
    for r in results:
        status = _status(r)
        header = f"- {status} {r['system']} ({r['account_id']})"
        if r.get("error"):
            lines.append(f"{header}: {r['error']}")
            continue
        gain = r.get("gain_pct")
        dd = r.get("max_drawdown_pct")
        lines.append(
            f"{header}: gain={gain if gain is None else f'{gain:.2f}%'} " f"dd={dd if dd is None else f'{dd:.2f}%'}"
        )
        for reason in r.get("filter_reasons", []):
            lines.append(f"  - filter: {reason}")
        for signal in r.get("martingale_signals", []):
            lines.append(f"  - martingale: {signal}")
    lines.append("")
    return "\n".join(lines)
