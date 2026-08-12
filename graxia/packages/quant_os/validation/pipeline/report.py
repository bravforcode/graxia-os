"""Report generator for validation pipeline results."""

from __future__ import annotations

import json
from pathlib import Path

from .gates import GateStatus
from .runner import PipelineResult


class ReportGenerator:
    """Generate Markdown + JSON reports from pipeline results."""

    def __init__(self, output_dir: Path = Path("reports/validation")):
        self.output_dir = output_dir

    def generate(self, result: PipelineResult) -> tuple[Path, Path]:
        """Generate both markdown and JSON reports. Returns (md_path, json_path)."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = result.timestamp
        md_path = self.output_dir / f"{timestamp}_validation_report.md"
        json_path = self.output_dir / f"{timestamp}_validation_report.json"

        # Write JSON
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, default=str)

        # Write Markdown
        md = self._render_markdown(result)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md)

        return md_path, json_path

    def _render_markdown(self, result: PipelineResult) -> str:
        lines = []
        lines.append(f"# Validation Report — {result.timestamp}")
        lines.append("")

        # Summary
        lines.append("## Summary")
        lines.append(f"- **Assets:** {', '.join(result.symbols)}")
        lines.append(f"- **Total Time:** {result.total_elapsed_sec:.1f}s")

        if result.gate_summary:
            summary = result.gate_summary
            verdict = summary.overall.value
            emoji = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️", "SKIP": "⏭️"}.get(verdict, "")
            lines.append(f"- **Overall Verdict:** {emoji} **{verdict}**")
            lines.append(
                f"- **Gates:** {sum(1 for g in summary.gates if g.status == GateStatus.PASS)}/{len(summary.gates)} PASS"
            )
        lines.append("")

        # Gate Results Table
        if result.gate_summary and result.gate_summary.gates:
            lines.append("## Gate Results")
            lines.append("")
            lines.append("| Gate | Status | Metric | Threshold | Details |")
            lines.append("|------|--------|--------|-----------|---------|")
            for gate in result.gate_summary.gates:
                emoji = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️", "SKIP": "⏭️"}.get(gate.status.value, "")
                lines.append(
                    f"| {gate.name} | {emoji} {gate.status.value} | "
                    f"{gate.metric:.4f} | {gate.threshold:.4f} | {gate.details} |"
                )
            lines.append("")

        # Workstream Details
        for name, ws in result.results.items():
            lines.append(f"## {name.upper().replace('_', ' ')}")
            lines.append("")
            if not ws.success:
                lines.append(f"> ❌ **FAILED:** {ws.error}")
            else:
                lines.append(f"- **Status:** ✅ Complete ({ws.elapsed_sec:.1f}s)")
                for key, val in ws.data.items():
                    if key in ("windows", "scenarios_tested"):
                        continue
                    if isinstance(val, float):
                        lines.append(f"- **{key}:** {val:.4f}")
                    else:
                        lines.append(f"- **{key}:** {val}")

                # Special rendering for WFA windows
                if name == "wfa" and "windows" in ws.data:
                    lines.append("")
                    lines.append("### Walk-Forward Windows")
                    lines.append("")
                    lines.append("| Window | Symbol | IS Sharpe | OOS Sharpe | WFE |")
                    lines.append("|--------|--------|-----------|------------|-----|")
                    for w in ws.data["windows"]:
                        lines.append(
                            f"| {w['window']} | {w['symbol']} | "
                            f"{w['is_sharpe']:.4f} | {w['oos_sharpe']:.4f} | "
                            f"{w['wfe']:.4f} |"
                        )
            lines.append("")

        # Recommendation
        lines.append("## Recommendation")
        lines.append("")
        if result.gate_summary:
            if result.gate_summary.overall == GateStatus.PASS:
                lines.append("✅ **All statistical gates passed.** Strategy demonstrates robustness across:")
                lines.append("- Walk-forward out-of-sample consistency")
                lines.append("- Monte Carlo survival probability")
                lines.append("- Deflated Sharpe significance (corrected for multiple testing)")
                lines.append("- Bootstrap confidence intervals")
                lines.append("")
                lines.append("**Next step:** Proceed to micro-lot live testing ($50-100 budget, 7 days).")
            elif result.gate_summary.overall == GateStatus.FAIL:
                lines.append("❌ **One or more gates failed.** Strategy shows signs of:")
                failed = [g for g in result.gate_summary.gates if g.status == GateStatus.FAIL]
                for g in failed:
                    lines.append(f"- {g.name}: {g.details}")
                lines.append("")
                lines.append("**Next step:** Review failed gates. Strategy needs improvement before live deployment.")
            else:
                lines.append("⚠️ **Warnings detected.** Review results carefully before proceeding.")
        else:
            lines.append("No gate evaluation available.")
        lines.append("")

        return "\n".join(lines)
