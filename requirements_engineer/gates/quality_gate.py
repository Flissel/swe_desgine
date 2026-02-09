"""
Quality Gate - Enforces quality thresholds between passes.

Quality gates ensure that outputs from each pass meet minimum
quality standards before proceeding to the next pass.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Literal, Set
from datetime import datetime
from enum import Enum

# Metrics that represent absolute counts (not ratios/percentages)
COUNT_METRICS: Set[str] = {"min_requirements", "min_user_stories", "min_test_cases"}


class GateStatus(Enum):
    """Status of a quality gate check."""
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class GateResult:
    """Result of a quality gate check."""
    status: GateStatus
    gate_name: str
    metrics_evaluated: Dict[str, float] = field(default_factory=dict)
    metrics_met: Dict[str, bool] = field(default_factory=dict)
    details: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    count_thresholds: Dict[str, int] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_markdown(self) -> str:
        """Convert to markdown format."""
        status_emoji = {
            GateStatus.PASS: "✅",
            GateStatus.WARN: "⚠️",
            GateStatus.FAIL: "❌"
        }

        md = f"### {status_emoji[self.status]} Quality Gate: {self.gate_name}\n\n"
        md += f"**Status:** {self.status.value.upper()}\n"
        md += f"**Timestamp:** {self.timestamp}\n\n"

        if self.metrics_evaluated:
            md += "**Metrics:**\n\n"
            md += "| Metric | Value | Threshold | Status |\n"
            md += "|--------|-------|-----------|--------|\n"
            for metric, value in self.metrics_evaluated.items():
                met = self.metrics_met.get(metric, False)
                status_str = "✅" if met else "❌"
                if metric in COUNT_METRICS:
                    # Display absolute counts, not percentages
                    threshold = self.count_thresholds.get(metric, 0)
                    md += f"| {metric} | {int(value)} | {int(threshold)} | {status_str} |\n"
                else:
                    md += f"| {metric} | {value:.2%} | - | {status_str} |\n"
            md += "\n"

        if self.details:
            md += "**Details:**\n"
            for detail in self.details:
                md += f"- {detail}\n"
            md += "\n"

        if self.warnings:
            md += "**Warnings:**\n"
            for warning in self.warnings:
                md += f"- ⚠️ {warning}\n"
            md += "\n"

        return md


class QualityGate:
    """
    Quality Gate for enforcing quality thresholds between passes.

    Gates are checked after each pass to determine if the outputs
    meet the minimum quality standards to proceed.
    """

    # Default thresholds for each gate transition
    DEFAULT_THRESHOLDS = {
        "pass1_to_pass2": {
            "completeness": 0.80,
            "stakeholder_coverage": 0.90,
            "min_requirements": 3
        },
        "pass2_to_pass3": {
            "consistency": 0.90,
            "decomposition_depth": 2,
            "min_user_stories": 3
        },
        "pass3_to_pass4": {
            "testability": 0.75,
            "diagram_validity": 0.80,
            "api_coverage": 0.70
        },
        "pass4_to_pass5": {
            "test_coverage": 0.80,
            "traceability": 0.90,
            "min_test_cases": 5
        },
        "final": {
            "overall_quality": 0.80,
            "documentation_completeness": 0.85
        }
    }

    # Threshold levels for WARN vs FAIL
    WARN_THRESHOLD = 0.9  # 90% of threshold = warning
    FAIL_THRESHOLD = 0.7  # 70% of threshold = fail

    def __init__(self, custom_thresholds: Dict[str, Dict[str, float]] = None):
        """
        Initialize Quality Gate with optional custom thresholds.

        Args:
            custom_thresholds: Optional custom thresholds to override defaults
        """
        self.thresholds = self.DEFAULT_THRESHOLDS.copy()
        if custom_thresholds:
            for gate, metrics in custom_thresholds.items():
                if gate in self.thresholds:
                    self.thresholds[gate].update(metrics)
                else:
                    self.thresholds[gate] = metrics

        self.gate_history: List[GateResult] = []

    def check_gate(
        self,
        gate_name: str,
        metrics: Dict[str, float],
        artifacts: Dict[str, Any] = None
    ) -> GateResult:
        """
        Check if metrics meet the threshold for a specific gate.

        Args:
            gate_name: Name of the gate (e.g., "pass1_to_pass2")
            metrics: Dictionary of metric values
            artifacts: Optional artifacts to validate

        Returns:
            GateResult with status and details
        """
        thresholds = self.thresholds.get(gate_name, {})
        if not thresholds:
            return GateResult(
                status=GateStatus.WARN,
                gate_name=gate_name,
                details=["No thresholds defined for this gate"],
                warnings=["Proceeding without quality validation"]
            )

        metrics_met = {}
        details = []
        warnings = []
        count_thresholds_map = {}

        # Check each threshold
        for metric, threshold in thresholds.items():
            if isinstance(threshold, (int, float)):
                value = metrics.get(metric, 0)

                if metric in COUNT_METRICS:
                    # Count metrics: compare absolute values directly
                    met = value >= threshold
                    count_thresholds_map[metric] = int(threshold)
                    if not met:
                        details.append(f"{metric}: {int(value)} below minimum {int(threshold)}")
                    else:
                        details.append(f"{metric}: {int(value)} meets minimum {int(threshold)}")
                else:
                    # Ratio metrics: compare as 0.0-1.0 ratios
                    met = value >= threshold

                    # Check for warning level
                    if not met and value >= threshold * self.WARN_THRESHOLD:
                        warnings.append(f"{metric}: {value:.2%} is close to threshold {threshold:.2%}")
                        met = True  # Count as met for overall status, but warn

                    if not met:
                        details.append(f"{metric}: {value:.2%} below threshold {threshold:.2%}")
                    else:
                        details.append(f"{metric}: {value:.2%} meets threshold {threshold:.2%}")

                metrics_met[metric] = met

        # Determine overall status
        all_met = all(metrics_met.values()) if metrics_met else True
        has_warnings = len(warnings) > 0

        if all_met and not has_warnings:
            status = GateStatus.PASS
        elif all_met and has_warnings:
            status = GateStatus.WARN
        else:
            status = GateStatus.FAIL

        result = GateResult(
            status=status,
            gate_name=gate_name,
            metrics_evaluated=metrics,
            metrics_met=metrics_met,
            details=details,
            warnings=warnings,
            count_thresholds=count_thresholds_map,
        )

        self.gate_history.append(result)
        return result

    def check_discovery_gate(
        self,
        requirements_count: int,
        stakeholder_coverage: float,
        completeness: float
    ) -> GateResult:
        """Check gate after Discovery pass (Pass 1)."""
        metrics = {
            "completeness": completeness,
            "stakeholder_coverage": stakeholder_coverage,
            "min_requirements": requirements_count,
        }
        return self.check_gate("pass1_to_pass2", metrics)

    def check_analysis_gate(
        self,
        consistency: float,
        user_stories_count: int,
        decomposition_depth: int
    ) -> GateResult:
        """Check gate after Analysis pass (Pass 2)."""
        metrics = {
            "consistency": consistency,
            "min_user_stories": user_stories_count,
            "decomposition_depth": decomposition_depth / max(self.thresholds["pass2_to_pass3"].get("decomposition_depth", 2), 1)
        }
        return self.check_gate("pass2_to_pass3", metrics)

    def check_specification_gate(
        self,
        testability: float,
        diagram_validity: float,
        api_coverage: float
    ) -> GateResult:
        """Check gate after Specification pass (Pass 3)."""
        metrics = {
            "testability": testability,
            "diagram_validity": diagram_validity,
            "api_coverage": api_coverage
        }
        return self.check_gate("pass3_to_pass4", metrics)

    def check_testing_gate(
        self,
        test_coverage: float,
        traceability: float,
        test_cases_count: int
    ) -> GateResult:
        """Check gate after Testing pass (Pass 4)."""
        metrics = {
            "test_coverage": min(test_coverage, 1.0),  # Cap at 100%
            "traceability": min(traceability, 1.0),
            "min_test_cases": test_cases_count,
        }
        return self.check_gate("pass4_to_pass5", metrics)

    def check_final_gate(
        self,
        overall_quality: float,
        documentation_completeness: float
    ) -> GateResult:
        """Check final quality gate."""
        metrics = {
            "overall_quality": overall_quality,
            "documentation_completeness": documentation_completeness
        }
        return self.check_gate("final", metrics)

    @staticmethod
    def compute_traceability(requirements, user_stories, test_cases) -> Dict[str, float]:
        """Compute real traceability metrics from artifact links.

        Returns:
            Dict with req_to_story, story_to_test, and overall ratios (0.0-1.0).
        """
        req_to_us = {}
        for us in user_stories:
            parent_req = getattr(us, 'parent_requirement_id', None)
            if parent_req:
                req_to_us.setdefault(parent_req, []).append(getattr(us, 'id', ''))

        us_to_tc = {}
        for tc in test_cases:
            parent_us = getattr(tc, 'parent_user_story_id', None)
            if parent_us:
                us_to_tc.setdefault(parent_us, []).append(getattr(tc, 'id', ''))

        req_ids = set()
        for req in requirements:
            rid = getattr(req, 'requirement_id', None) or getattr(req, 'id', '')
            if rid:
                req_ids.add(rid)

        req_coverage = len(req_to_us) / max(len(req_ids), 1)
        us_coverage = len(us_to_tc) / max(len(user_stories), 1)

        return {
            "req_to_story": min(req_coverage, 1.0),
            "story_to_test": min(us_coverage, 1.0),
            "overall": min((req_coverage + us_coverage) / 2, 1.0),
        }

    def get_gate_summary(self) -> str:
        """Get markdown summary of all gate checks."""
        md = "# Quality Gate Summary\n\n"
        md += f"**Total Gates Checked:** {len(self.gate_history)}\n"

        passed = sum(1 for g in self.gate_history if g.status == GateStatus.PASS)
        warned = sum(1 for g in self.gate_history if g.status == GateStatus.WARN)
        failed = sum(1 for g in self.gate_history if g.status == GateStatus.FAIL)

        md += f"- ✅ Passed: {passed}\n"
        md += f"- ⚠️ Warnings: {warned}\n"
        md += f"- ❌ Failed: {failed}\n\n"

        md += "---\n\n"

        for result in self.gate_history:
            md += result.to_markdown()
            md += "---\n\n"

        return md


# Test function
def test_quality_gate():
    """Test the QualityGate class."""
    gate = QualityGate()

    print("=== Testing Quality Gates ===\n")

    # Test Pass 1 → Pass 2 gate
    result1 = gate.check_discovery_gate(
        requirements_count=5,
        stakeholder_coverage=0.95,
        completeness=0.85
    )
    print(f"Discovery Gate: {result1.status.value}")

    # Test Pass 2 → Pass 3 gate (with warning)
    result2 = gate.check_analysis_gate(
        consistency=0.82,  # Below 90% but above warn level
        user_stories_count=4,
        decomposition_depth=2
    )
    print(f"Analysis Gate: {result2.status.value}")

    # Test Pass 3 → Pass 4 gate (failing)
    result3 = gate.check_specification_gate(
        testability=0.60,  # Below threshold
        diagram_validity=0.75,
        api_coverage=0.65
    )
    print(f"Specification Gate: {result3.status.value}")

    # Print summary
    print("\n" + gate.get_gate_summary())

    return gate


if __name__ == "__main__":
    test_quality_gate()
