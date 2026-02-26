"""
Requirements Metrics - Quality metrics for requirement validation.

Based on ai_scientist/treesearch/utils/metric.py
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from dataclasses_json import dataclass_json


@dataclass_json
@dataclass
class RequirementMetrics:
    """
    Multi-dimensional quality metrics for requirements.
    All scores are normalized to 0.0 - 1.0 range.
    """

    # Completeness: Are all aspects covered?
    completeness_score: float = 0.0
    missing_elements: List[str] = field(default_factory=list)

    # Consistency: No conflicts between requirements?
    consistency_score: float = 0.0
    conflicts_found: List[Tuple[str, str]] = field(default_factory=list)

    # Testability: Can requirements be verified?
    testability_score: float = 0.0
    untestable_requirements: List[str] = field(default_factory=list)

    # Clarity: Is the language unambiguous?
    clarity_score: float = 0.0
    ambiguous_terms: List[str] = field(default_factory=list)

    # Feasibility: Can it be implemented?
    feasibility_score: float = 0.0
    feasibility_risks: List[str] = field(default_factory=list)

    # Traceability: Are relationships clear?
    traceability_score: float = 0.0
    orphaned_requirements: List[str] = field(default_factory=list)

    # Coverage metrics
    functional_coverage: float = 0.0
    non_functional_coverage: float = 0.0

    def aggregate_score(self, weights: Dict[str, float] = None) -> float:
        """Calculate weighted average of all metrics."""
        if weights is None:
            weights = {
                "completeness": 0.20,
                "consistency": 0.20,
                "testability": 0.15,
                "clarity": 0.15,
                "feasibility": 0.15,
                "traceability": 0.15
            }

        return (
            self.completeness_score * weights.get("completeness", 0.2) +
            self.consistency_score * weights.get("consistency", 0.2) +
            self.testability_score * weights.get("testability", 0.15) +
            self.clarity_score * weights.get("clarity", 0.15) +
            self.feasibility_score * weights.get("feasibility", 0.15) +
            self.traceability_score * weights.get("traceability", 0.15)
        )

    def passes_thresholds(self, thresholds: Dict[str, float]) -> Tuple[bool, List[str]]:
        """
        Check if all metrics pass the given thresholds.
        Returns (passes, list of failed metrics).
        """
        failed = []

        if self.completeness_score < thresholds.get("min_completeness", 0.8):
            failed.append(f"completeness ({self.completeness_score:.2f} < {thresholds.get('min_completeness', 0.8)})")

        if self.consistency_score < thresholds.get("min_consistency", 0.9):
            failed.append(f"consistency ({self.consistency_score:.2f} < {thresholds.get('min_consistency', 0.9)})")

        if self.testability_score < thresholds.get("min_testability", 0.75):
            failed.append(f"testability ({self.testability_score:.2f} < {thresholds.get('min_testability', 0.75)})")

        if self.clarity_score < thresholds.get("min_clarity", 0.8):
            failed.append(f"clarity ({self.clarity_score:.2f} < {thresholds.get('min_clarity', 0.8)})")

        if self.feasibility_score < thresholds.get("min_feasibility", 0.75):
            failed.append(f"feasibility ({self.feasibility_score:.2f} < {thresholds.get('min_feasibility', 0.75)})")

        if self.traceability_score < thresholds.get("min_traceability", 0.8):
            failed.append(f"traceability ({self.traceability_score:.2f} < {thresholds.get('min_traceability', 0.8)})")

        return len(failed) == 0, failed

    def to_report(self) -> str:
        """Generate a human-readable metrics report."""
        report = "# Requirements Quality Metrics Report\n\n"

        report += "## Scores Overview\n\n"
        report += f"| Metric | Score | Status |\n"
        report += f"|--------|-------|--------|\n"
        report += f"| Completeness | {self.completeness_score:.2%} | {'✓' if self.completeness_score >= 0.8 else '✗'} |\n"
        report += f"| Consistency | {self.consistency_score:.2%} | {'✓' if self.consistency_score >= 0.9 else '✗'} |\n"
        report += f"| Testability | {self.testability_score:.2%} | {'✓' if self.testability_score >= 0.75 else '✗'} |\n"
        report += f"| Clarity | {self.clarity_score:.2%} | {'✓' if self.clarity_score >= 0.8 else '✗'} |\n"
        report += f"| Feasibility | {self.feasibility_score:.2%} | {'✓' if self.feasibility_score >= 0.75 else '✗'} |\n"
        report += f"| Traceability | {self.traceability_score:.2%} | {'✓' if self.traceability_score >= 0.8 else '✗'} |\n"
        report += f"\n**Aggregate Score: {self.aggregate_score():.2%}**\n\n"

        if self.missing_elements:
            report += "## Missing Elements\n"
            for elem in self.missing_elements:
                report += f"- {elem}\n"
            report += "\n"

        if self.conflicts_found:
            report += "## Conflicts Found\n"
            for req1, req2 in self.conflicts_found:
                report += f"- {req1} ↔ {req2}\n"
            report += "\n"

        if self.untestable_requirements:
            report += "## Untestable Requirements\n"
            for req in self.untestable_requirements:
                report += f"- {req}\n"
            report += "\n"

        if self.ambiguous_terms:
            report += "## Ambiguous Terms\n"
            for term in self.ambiguous_terms:
                report += f"- {term}\n"
            report += "\n"

        if self.feasibility_risks:
            report += "## Feasibility Risks\n"
            for risk in self.feasibility_risks:
                report += f"- {risk}\n"
            report += "\n"

        if self.orphaned_requirements:
            report += "## Orphaned Requirements (No Traceability)\n"
            for req in self.orphaned_requirements:
                report += f"- {req}\n"
            report += "\n"

        return report


@dataclass_json
@dataclass
class StageMetrics:
    """Metrics for a specific stage of requirement engineering."""
    stage_number: int
    stage_name: str

    # Progress
    iterations_completed: int = 0
    max_iterations: int = 0

    # Requirements processed
    requirements_processed: int = 0
    requirements_improved: int = 0
    requirements_validated: int = 0

    # Quality improvement
    initial_aggregate_score: float = 0.0
    final_aggregate_score: float = 0.0
    score_improvement: float = 0.0

    # Diagrams generated
    diagrams_generated: int = 0
    diagram_types: List[str] = field(default_factory=list)

    def calculate_improvement(self):
        """Calculate score improvement."""
        self.score_improvement = self.final_aggregate_score - self.initial_aggregate_score


@dataclass_json
@dataclass
class ProjectMetrics:
    """Overall metrics for a requirements engineering project."""
    project_name: str
    total_requirements: int = 0
    validated_requirements: int = 0

    # Stage metrics
    stage_metrics: List[StageMetrics] = field(default_factory=list)

    # Overall quality
    overall_metrics: Optional[RequirementMetrics] = None

    # Work breakdown
    features_count: int = 0
    services_count: int = 0
    applications_count: int = 0

    # Diagrams
    total_diagrams: int = 0
    diagrams_by_type: Dict[str, int] = field(default_factory=dict)

    def completion_percentage(self) -> float:
        """Calculate project completion percentage."""
        if self.total_requirements == 0:
            return 0.0
        return self.validated_requirements / self.total_requirements

    def summary(self) -> str:
        """Generate project summary."""
        summary = f"# Project Metrics: {self.project_name}\n\n"
        summary += f"- Total Requirements: {self.total_requirements}\n"
        summary += f"- Validated: {self.validated_requirements} ({self.completion_percentage():.1%})\n"
        summary += f"- Total Diagrams: {self.total_diagrams}\n\n"

        if self.overall_metrics:
            summary += f"## Quality Score: {self.overall_metrics.aggregate_score():.2%}\n\n"

        if self.stage_metrics:
            summary += "## Stage Progress\n\n"
            for sm in self.stage_metrics:
                summary += f"- Stage {sm.stage_number} ({sm.stage_name}): "
                summary += f"{sm.iterations_completed}/{sm.max_iterations} iterations, "
                summary += f"improvement: {sm.score_improvement:+.2%}\n"

        return summary


class MetricsManager:
    """
    Manages metrics for all requirements in a project.
    Provides aggregate calculations and threshold checking.
    """

    def __init__(self, thresholds: Dict[str, float] = None):
        """
        Initialize the metrics manager.

        Args:
            thresholds: Validation thresholds for metrics
        """
        self.thresholds = thresholds or {
            "min_completeness": 0.8,
            "min_consistency": 0.9,
            "min_testability": 0.75,
            "min_clarity": 0.8,
            "min_feasibility": 0.75,
            "min_traceability": 0.8
        }
        self.metrics: Dict[str, Dict[str, float]] = {}

    def add_requirement_metrics(
        self,
        requirement_id: str,
        completeness: float = 0.0,
        consistency: float = 0.0,
        testability: float = 0.0,
        clarity: float = 0.0,
        feasibility: float = 0.0,
        traceability: float = 0.0
    ) -> None:
        """Add or update metrics for a requirement."""
        self.metrics[requirement_id] = {
            "completeness": completeness,
            "consistency": consistency,
            "testability": testability,
            "clarity": clarity,
            "feasibility": feasibility,
            "traceability": traceability
        }

    def get_requirement_metrics(self, requirement_id: str) -> Optional[Dict[str, float]]:
        """Get metrics for a specific requirement."""
        return self.metrics.get(requirement_id)

    def get_aggregate_metrics(self) -> Dict[str, float]:
        """Calculate aggregate metrics across all requirements."""
        if not self.metrics:
            return {
                "completeness": 0.0,
                "consistency": 0.0,
                "testability": 0.0,
                "clarity": 0.0,
                "feasibility": 0.0,
                "traceability": 0.0
            }

        totals = {
            "completeness": 0.0,
            "consistency": 0.0,
            "testability": 0.0,
            "clarity": 0.0,
            "feasibility": 0.0,
            "traceability": 0.0
        }

        for req_metrics in self.metrics.values():
            for key in totals:
                totals[key] += req_metrics.get(key, 0.0)

        count = len(self.metrics)
        return {key: value / count for key, value in totals.items()}

    def check_thresholds(self) -> Tuple[bool, List[str]]:
        """
        Check if aggregate metrics pass thresholds.

        Returns:
            Tuple of (passes_all, list of failures)
        """
        aggregate = self.get_aggregate_metrics()
        failures = []

        threshold_map = {
            "completeness": "min_completeness",
            "consistency": "min_consistency",
            "testability": "min_testability",
            "clarity": "min_clarity",
            "feasibility": "min_feasibility",
            "traceability": "min_traceability"
        }

        for metric, threshold_key in threshold_map.items():
            threshold = self.thresholds.get(threshold_key, 0.75)
            if aggregate[metric] < threshold:
                failures.append(f"{metric}: {aggregate[metric]:.2%} < {threshold:.2%}")

        return len(failures) == 0, failures

    def to_dict(self) -> Dict[str, Any]:
        """Export metrics as dictionary."""
        return {
            "thresholds": self.thresholds,
            "metrics": self.metrics,
            "aggregate": self.get_aggregate_metrics()
        }
