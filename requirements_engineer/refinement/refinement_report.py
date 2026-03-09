"""
Refinement Report — generates markdown before/after comparison reports.
"""

from datetime import datetime
from typing import Dict, List, Optional

from . import CompletenessReport, Gap, GapSeverity, RefinementResult, RuleResult


def generate_report(
    result: RefinementResult,
    before_report: CompletenessReport,
    after_report: Optional[CompletenessReport] = None,
) -> str:
    """Generate a markdown refinement report."""
    md = "# Refinement Report\n\n"
    md += f"**Generated:** {datetime.now().isoformat()}\n\n"

    # Summary
    md += "## Summary\n\n"
    md += f"- **Iterations:** {result.iterations}\n"
    md += f"- **Overall Score:** {result.before_overall:.1%} → {result.after_overall:.1%}\n"
    md += f"- **Gaps Found:** {result.gaps_found}\n"
    md += f"- **Gaps Fixed:** {result.gaps_fixed}\n"
    md += f"- **Gaps Remaining:** {result.gaps_remaining}\n"
    if result.total_llm_calls > 0:
        md += f"- **LLM Calls:** {result.total_llm_calls}\n"
        md += f"- **Cost:** ${result.total_cost_usd:.4f}\n"
    md += f"- **Duration:** {result.duration_seconds:.1f}s\n\n"

    # Score comparison table
    md += "## Score Breakdown\n\n"
    md += "| Dimension | Before | After | Delta | Status |\n"
    md += "|-----------|--------|-------|-------|--------|\n"

    for rr in before_report.rule_results:
        before_score = rr.score
        after_score = result.after_scores.get(rr.rule_id, before_score)
        delta = after_score - before_score
        status = "PASS" if after_score >= 1.0 else ("IMPROVED" if delta > 0.01 else "—")
        md += (
            f"| {rr.rule_name} | {before_score:.1%} | {after_score:.1%} "
            f"| {'+' if delta >= 0 else ''}{delta:.1%} | {status} |\n"
        )

    md += "\n"

    # Gaps detail
    all_gaps = before_report.all_gaps
    if all_gaps:
        md += "## Gaps Found\n\n"

        # Group by severity
        for severity in [GapSeverity.CRITICAL, GapSeverity.HIGH, GapSeverity.MEDIUM, GapSeverity.LOW]:
            sev_gaps = [g for g in all_gaps if g.severity == severity]
            if not sev_gaps:
                continue
            md += f"### {severity.value.upper()} ({len(sev_gaps)})\n\n"
            for gap in sev_gaps:
                md += f"- **{gap.gap_id}** [{gap.rule_id}] {gap.title}"
                if gap.fix_strategy:
                    md += f" *(fix: {gap.fix_strategy.value})*"
                md += "\n"
            md += "\n"

    # Fix log
    if result.fix_log:
        md += "## Fix Log\n\n"
        for entry in result.fix_log:
            md += f"- {entry}\n"
        md += "\n"

    # Remaining manual gaps
    remaining_manual = [
        g for g in all_gaps
        if g.fix_strategy.value == "manual"
    ]
    if remaining_manual:
        md += "## Manual Action Required\n\n"
        for gap in remaining_manual:
            md += f"- **{gap.gap_id}** {gap.title}\n"
            if gap.description:
                md += f"  {gap.description}\n"
        md += "\n"

    return md


def generate_dry_run_report(report: CompletenessReport) -> str:
    """Generate a report for dry-run mode (evaluation only, no fixes)."""
    md = "# Completeness Evaluation Report\n\n"
    md += f"**Generated:** {report.timestamp}\n\n"

    # Overall score
    md += f"## Overall Score: {report.overall_score:.1%}\n\n"

    # Score table
    md += "## Dimension Scores\n\n"
    md += "| # | Dimension | Current | Target | Score | Status |\n"
    md += "|---|-----------|---------|--------|-------|--------|\n"

    for i, rr in enumerate(report.rule_results, 1):
        status = "PASS" if rr.passed else "FAIL"
        # Format current_value: if > 1.0 it's a ratio, otherwise percentage
        if rr.target_value > 1.0:
            current_fmt = f"{rr.current_value:.1f}"
            target_fmt = f"{rr.target_value:.1f}"
        else:
            current_fmt = f"{rr.current_value:.1%}"
            target_fmt = f"{rr.target_value:.1%}"
        md += (
            f"| {i} | {rr.rule_name} | {current_fmt} | {target_fmt} "
            f"| {rr.score:.1%} | {status} |\n"
        )

    md += "\n"

    # Gaps summary
    all_gaps = report.all_gaps
    if all_gaps:
        md += f"## Gaps ({len(all_gaps)} total)\n\n"

        # By fix strategy
        by_strategy: Dict[str, List[Gap]] = {}
        for gap in all_gaps:
            key = gap.fix_strategy.value
            by_strategy.setdefault(key, []).append(gap)

        md += "### By Fix Strategy\n\n"
        for strategy, gaps in sorted(by_strategy.items()):
            md += f"- **{strategy}**: {len(gaps)} gaps\n"
        md += "\n"

        # Detailed list
        md += "### Details\n\n"
        for gap in all_gaps:
            md += (
                f"- **{gap.gap_id}** [{gap.severity.value}] [{gap.rule_id}] "
                f"{gap.title} *(fix: {gap.fix_strategy.value})*\n"
            )
        md += "\n"

    return md
