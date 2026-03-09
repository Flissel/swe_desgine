"""
Gap Classifier — categorizes and prioritizes completeness gaps for fixing.

Sorts gaps by impact (severity × weight × deficit) so the highest-value
fixes are applied first within each budget iteration.
"""

from dataclasses import dataclass, field
from typing import Dict, List

from . import DEFAULT_WEIGHTS, Gap, GapFixStrategy, GapSeverity


_SEVERITY_WEIGHT = {
    GapSeverity.CRITICAL: 4.0,
    GapSeverity.HIGH: 3.0,
    GapSeverity.MEDIUM: 2.0,
    GapSeverity.LOW: 1.0,
}


@dataclass
class ClassifiedGaps:
    """Gaps organized by fix strategy, sorted by priority."""
    auto_link: List[Gap] = field(default_factory=list)
    llm_extend: List[Gap] = field(default_factory=list)
    generator: List[Gap] = field(default_factory=list)
    manual: List[Gap] = field(default_factory=list)

    @property
    def fixable_count(self) -> int:
        return len(self.auto_link) + len(self.llm_extend) + len(self.generator)

    @property
    def total_count(self) -> int:
        return self.fixable_count + len(self.manual)


def _gap_priority(gap: Gap) -> float:
    """Compute priority score for a gap (higher = fix first)."""
    severity = _SEVERITY_WEIGHT.get(gap.severity, 1.0)
    rule_weight = DEFAULT_WEIGHTS.get(gap.rule_id, 0.05)
    deficit = max(gap.target_value - gap.current_value, 0.01)
    return severity * rule_weight * deficit


def classify_gaps(gaps: List[Gap]) -> ClassifiedGaps:
    """Classify gaps by fix strategy and sort by priority within each category."""
    result = ClassifiedGaps()

    for gap in gaps:
        bucket = {
            GapFixStrategy.AUTO_LINK: result.auto_link,
            GapFixStrategy.LLM_EXTEND: result.llm_extend,
            GapFixStrategy.GENERATOR: result.generator,
            GapFixStrategy.MANUAL: result.manual,
        }.get(gap.fix_strategy, result.manual)
        bucket.append(gap)

    # Sort each bucket by priority (highest first)
    result.auto_link.sort(key=_gap_priority, reverse=True)
    result.llm_extend.sort(key=_gap_priority, reverse=True)
    result.generator.sort(key=_gap_priority, reverse=True)
    result.manual.sort(key=_gap_priority, reverse=True)

    return result
