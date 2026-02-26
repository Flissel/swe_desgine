"""
Feature-based Work Breakdown Structure

Breaks down requirements into feature-centric work packages.
This is the recommended default breakdown method.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
import json


@dataclass_json
@dataclass
class FeatureWorkPackage:
    """A work package representing a feature."""
    feature_id: str
    feature_name: str
    description: str
    requirements: List[str]  # Requirement IDs
    priority: str  # must, should, could, wont
    estimated_complexity: str  # low, medium, high
    dependencies: List[str] = field(default_factory=list)  # Other feature IDs
    acceptance_criteria: List[str] = field(default_factory=list)
    mermaid_diagrams: Dict[str, str] = field(default_factory=dict)
    notes: str = ""


class FeatureBreakdown:
    """
    Breaks down requirements into feature-based work packages.

    Features are user-facing capabilities that deliver value.
    This is the recommended breakdown method for most projects.
    """

    def __init__(self):
        self.features: Dict[str, FeatureWorkPackage] = {}
        self.requirement_to_feature: Dict[str, str] = {}

    def create_feature(
        self,
        feature_id: str,
        feature_name: str,
        description: str,
        priority: str = "should",
        estimated_complexity: str = "medium"
    ) -> FeatureWorkPackage:
        """Create a new feature work package."""
        feature = FeatureWorkPackage(
            feature_id=feature_id,
            feature_name=feature_name,
            description=description,
            requirements=[],
            priority=priority,
            estimated_complexity=estimated_complexity
        )
        self.features[feature_id] = feature
        return feature

    def assign_requirement(self, requirement_id: str, feature_id: str) -> bool:
        """Assign a requirement to a feature."""
        if feature_id not in self.features:
            return False

        if requirement_id not in self.features[feature_id].requirements:
            self.features[feature_id].requirements.append(requirement_id)
        self.requirement_to_feature[requirement_id] = feature_id
        return True

    def add_dependency(self, feature_id: str, depends_on: str) -> bool:
        """Add a dependency between features."""
        if feature_id not in self.features or depends_on not in self.features:
            return False

        if depends_on not in self.features[feature_id].dependencies:
            self.features[feature_id].dependencies.append(depends_on)
        return True

    def get_feature_for_requirement(self, requirement_id: str) -> Optional[str]:
        """Get the feature ID for a requirement."""
        return self.requirement_to_feature.get(requirement_id)

    def get_features_by_priority(self, priority: str) -> List[FeatureWorkPackage]:
        """Get all features with a specific priority."""
        return [f for f in self.features.values() if f.priority == priority]

    def get_dependency_order(self) -> List[str]:
        """
        Get features in dependency order (topological sort).
        Features with no dependencies come first.
        """
        visited = set()
        order = []

        def visit(feature_id: str):
            if feature_id in visited:
                return
            visited.add(feature_id)

            feature = self.features.get(feature_id)
            if feature:
                for dep in feature.dependencies:
                    visit(dep)
            order.append(feature_id)

        for feature_id in self.features:
            visit(feature_id)

        return order

    def generate_breakdown_from_requirements(
        self,
        requirements: List[Any],
        groupings: List[Dict[str, Any]]
    ) -> None:
        """
        Generate feature breakdown from requirements and groupings.

        Args:
            requirements: List of RequirementNode objects
            groupings: List of requirement groups from analysis
        """
        # Create features from groupings
        for i, group in enumerate(groupings):
            feature_id = f"FEAT-{i+1:03d}"
            feature_name = group.get("name", f"Feature {i+1}")

            # Determine priority based on requirements in group
            req_ids = group.get("requirements", [])
            priority = self._determine_group_priority(requirements, req_ids)
            complexity = self._estimate_complexity(len(req_ids))

            self.create_feature(
                feature_id=feature_id,
                feature_name=feature_name,
                description=f"Feature encompassing: {', '.join(req_ids)}",
                priority=priority,
                estimated_complexity=complexity
            )

            # Assign requirements to feature
            for req_id in req_ids:
                self.assign_requirement(req_id, feature_id)

    def _determine_group_priority(
        self,
        requirements: List[Any],
        req_ids: List[str]
    ) -> str:
        """Determine feature priority based on its requirements."""
        priority_order = {"must": 0, "should": 1, "could": 2, "wont": 3}

        highest_priority = "wont"
        for req in requirements:
            if req.requirement_id in req_ids:
                if priority_order.get(req.priority, 3) < priority_order.get(highest_priority, 3):
                    highest_priority = req.priority

        return highest_priority

    def _estimate_complexity(self, num_requirements: int) -> str:
        """Estimate complexity based on number of requirements."""
        if num_requirements <= 3:
            return "low"
        elif num_requirements <= 7:
            return "medium"
        else:
            return "high"

    def to_markdown(self) -> str:
        """Export breakdown as Markdown."""
        lines = ["# Feature Work Breakdown Structure\n"]

        # Summary
        lines.append("## Summary\n")
        lines.append(f"- Total Features: {len(self.features)}")
        lines.append(f"- Must-have: {len(self.get_features_by_priority('must'))}")
        lines.append(f"- Should-have: {len(self.get_features_by_priority('should'))}")
        lines.append(f"- Could-have: {len(self.get_features_by_priority('could'))}")
        lines.append(f"- Won't-have: {len(self.get_features_by_priority('wont'))}\n")

        # Features in dependency order
        lines.append("## Features (Dependency Order)\n")
        for feature_id in self.get_dependency_order():
            feature = self.features[feature_id]
            lines.append(f"### {feature.feature_id}: {feature.feature_name}\n")
            lines.append(f"**Priority:** {feature.priority.upper()}")
            lines.append(f"**Complexity:** {feature.estimated_complexity.capitalize()}")
            lines.append(f"\n{feature.description}\n")

            if feature.requirements:
                lines.append("**Requirements:**")
                for req_id in feature.requirements:
                    lines.append(f"- {req_id}")
                lines.append("")

            if feature.dependencies:
                lines.append(f"**Dependencies:** {', '.join(feature.dependencies)}\n")

            if feature.acceptance_criteria:
                lines.append("**Acceptance Criteria:**")
                for ac in feature.acceptance_criteria:
                    lines.append(f"- {ac}")
                lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Export breakdown as dictionary."""
        return {
            "breakdown_type": "feature",
            "features": {fid: f.to_dict() for fid, f in self.features.items()},
            "requirement_mapping": self.requirement_to_feature,
            "dependency_order": self.get_dependency_order()
        }
