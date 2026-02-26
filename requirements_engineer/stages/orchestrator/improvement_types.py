"""
Improvement Types for Presentation Stage.

Defines the types of improvements that can be applied to HTML content
during the iterative improvement process.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime


class ImprovementType(Enum):
    """Types of improvements that can be applied to HTML."""
    ADD_SECTION = "add_section"
    ENHANCE_CONTENT = "enhance_content"
    FIX_STRUCTURE = "fix_structure"
    ADD_STYLING = "add_styling"
    GENERATE_DIAGRAM = "generate_diagram"
    MERGE_CONTENT = "merge_content"
    ADD_NAVIGATION = "add_navigation"
    FIX_ACCESSIBILITY = "fix_accessibility"
    OPTIMIZE_LAYOUT = "optimize_layout"
    ADD_INTERACTIVITY = "add_interactivity"


class ImprovementPriority(Enum):
    """Priority levels for improvements."""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


@dataclass
class ImprovementPlan:
    """
    Plan for applying improvements to HTML content.

    Contains a prioritized list of improvements to apply.
    """
    improvements: List["ImprovementItem"] = field(default_factory=list)
    target_quality: float = 0.8
    max_improvements: int = 10
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_improvement(self, improvement: "ImprovementItem") -> None:
        """Add an improvement to the plan."""
        self.improvements.append(improvement)
        # Keep sorted by priority
        self.improvements.sort(key=lambda x: x.priority.value)

    def get_by_type(self, improvement_type: ImprovementType) -> List["ImprovementItem"]:
        """Get improvements of a specific type."""
        return [i for i in self.improvements if i.type == improvement_type]

    def get_by_file(self, file_path: str) -> List["ImprovementItem"]:
        """Get improvements for a specific file."""
        return [i for i in self.improvements if i.target_file == file_path]

    def get_top_n(self, n: int) -> List["ImprovementItem"]:
        """Get top N improvements by priority."""
        return self.improvements[:n]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "improvements": [i.to_dict() for i in self.improvements],
            "target_quality": self.target_quality,
            "max_improvements": self.max_improvements,
            "created_at": self.created_at,
            "total_count": len(self.improvements)
        }


@dataclass
class ImprovementItem:
    """
    Single improvement item to apply.

    Describes what to improve, where, and how.
    """
    type: ImprovementType
    priority: ImprovementPriority
    target_file: str
    description: str
    suggestion: str
    target_selector: str = ""  # CSS selector or element ID
    content: str = ""  # New content to add/replace
    position: str = "replace"  # before, after, replace, append
    severity: str = "minor"  # critical, major, minor
    category: str = ""  # structure, content, styling, navigation, accessibility
    estimated_effort: str = "low"  # low, medium, high
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type.value,
            "priority": self.priority.name,
            "target_file": self.target_file,
            "description": self.description,
            "suggestion": self.suggestion,
            "target_selector": self.target_selector,
            "position": self.position,
            "severity": self.severity,
            "category": self.category,
            "estimated_effort": self.estimated_effort
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ImprovementItem":
        """Create from dictionary."""
        return cls(
            type=ImprovementType(data.get("type", "enhance_content")),
            priority=ImprovementPriority[data.get("priority", "MEDIUM")],
            target_file=data.get("target_file", ""),
            description=data.get("description", ""),
            suggestion=data.get("suggestion", ""),
            target_selector=data.get("target_selector", ""),
            content=data.get("content", ""),
            position=data.get("position", "replace"),
            severity=data.get("severity", "minor"),
            category=data.get("category", ""),
            estimated_effort=data.get("estimated_effort", "low"),
            metadata=data.get("metadata", {})
        )


@dataclass
class ImprovementResult:
    """
    Result of applying an improvement.

    Records whether the improvement was successful and any changes made.
    """
    improvement: ImprovementItem
    success: bool
    changes_made: str = ""
    error_message: str = ""
    quality_before: float = 0.0
    quality_after: float = 0.0
    duration_seconds: float = 0.0
    applied_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def quality_delta(self) -> float:
        """Calculate quality improvement."""
        return self.quality_after - self.quality_before

    @property
    def was_effective(self) -> bool:
        """Check if the improvement was effective."""
        return self.success and self.quality_delta > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "improvement": self.improvement.to_dict(),
            "success": self.success,
            "changes_made": self.changes_made,
            "error_message": self.error_message,
            "quality_before": self.quality_before,
            "quality_after": self.quality_after,
            "quality_delta": self.quality_delta,
            "duration_seconds": self.duration_seconds,
            "applied_at": self.applied_at,
            "was_effective": self.was_effective
        }


# Mapping from review categories to improvement types
CATEGORY_TO_IMPROVEMENT_TYPE = {
    "structure": [ImprovementType.FIX_STRUCTURE, ImprovementType.ADD_SECTION],
    "content": [ImprovementType.ENHANCE_CONTENT, ImprovementType.ADD_SECTION],
    "styling": [ImprovementType.ADD_STYLING, ImprovementType.OPTIMIZE_LAYOUT],
    "navigation": [ImprovementType.ADD_NAVIGATION, ImprovementType.FIX_STRUCTURE],
    "accessibility": [ImprovementType.FIX_ACCESSIBILITY],
    "diagrams": [ImprovementType.GENERATE_DIAGRAM],
}


def create_improvement_from_issue(
    issue: Dict[str, Any],
    target_file: str
) -> ImprovementItem:
    """
    Create an ImprovementItem from a quality issue.

    Args:
        issue: Quality issue dictionary from reviewer
        target_file: Target file path

    Returns:
        ImprovementItem ready to apply
    """
    severity = issue.get("severity", "minor")
    category = issue.get("category", "content")
    description = issue.get("description", "")
    suggestion = issue.get("suggestion", "")

    # Determine improvement type based on category
    improvement_types = CATEGORY_TO_IMPROVEMENT_TYPE.get(category, [ImprovementType.ENHANCE_CONTENT])
    improvement_type = improvement_types[0]

    # Determine priority based on severity
    priority_map = {
        "critical": ImprovementPriority.CRITICAL,
        "major": ImprovementPriority.HIGH,
        "minor": ImprovementPriority.MEDIUM
    }
    priority = priority_map.get(severity, ImprovementPriority.LOW)

    return ImprovementItem(
        type=improvement_type,
        priority=priority,
        target_file=target_file,
        description=description,
        suggestion=suggestion,
        severity=severity,
        category=category
    )


def create_improvement_plan(
    issues: List[Dict[str, Any]],
    target_quality: float = 0.8,
    max_improvements: int = 10
) -> ImprovementPlan:
    """
    Create an improvement plan from quality issues.

    Args:
        issues: List of quality issues from reviewer
        target_quality: Target quality score
        max_improvements: Maximum improvements to include

    Returns:
        ImprovementPlan with prioritized improvements
    """
    plan = ImprovementPlan(
        target_quality=target_quality,
        max_improvements=max_improvements
    )

    for issue in issues:
        target_file = issue.get("location", issue.get("target_file", ""))
        improvement = create_improvement_from_issue(issue, target_file)
        plan.add_improvement(improvement)

    # Limit to max improvements
    plan.improvements = plan.improvements[:max_improvements]

    return plan
