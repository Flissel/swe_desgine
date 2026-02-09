"""
Requirements Journal - Node and Journal classes for tracking requirement versions.

Based on ai_scientist/treesearch/journal.py
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Set, Literal, Any
from dataclasses_json import dataclass_json
from datetime import datetime
import uuid
import json


RequirementType = Literal["functional", "non_functional", "constraint", "assumption", "dependency"]
PriorityType = Literal["must", "should", "could", "wont"]
ValidationStatus = Literal["draft", "analyzed", "specified", "validated"]
NodeStageType = Literal["draft", "debug", "improve"]  # Tree-search stage type


@dataclass_json
@dataclass
class RequirementNode:
    """
    A single requirement node in the journal tree.
    Represents a version of a requirement specification.
    """
    # Identification
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    requirement_id: str = ""  # REQ-001, REQ-002, etc.

    # Core requirement data
    title: str = ""
    description: str = ""
    type: RequirementType = "functional"
    priority: PriorityType = "should"

    # Detailed information
    rationale: str = ""
    source: str = ""  # Where the requirement came from

    # Acceptance criteria
    acceptance_criteria: List[str] = field(default_factory=list)
    testable: bool = True

    # Relationships
    parent_requirement: Optional[str] = None  # For decomposition
    dependencies: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    related_requirements: List[str] = field(default_factory=list)

    # Work breakdown
    work_package: str = ""  # Feature/Service/Application name
    estimated_effort: Optional[str] = None
    assigned_to: Optional[str] = None

    # Mermaid diagrams
    mermaid_diagrams: Dict[str, str] = field(default_factory=dict)
    # Example: {"flowchart": "graph TD\n...", "sequence": "sequenceDiagram\n..."}

    # Validation status
    validation_status: ValidationStatus = "draft"

    # Quality metrics (0.0 - 1.0)
    completeness_score: float = 0.0
    consistency_score: float = 0.0
    testability_score: float = 0.0
    clarity_score: float = 0.0
    feasibility_score: float = 0.0
    traceability_score: float = 0.0

    # Iteration tracking (tree structure)
    version: int = 1
    parent_version_id: Optional[str] = None
    children_version_ids: Set[str] = field(default_factory=set)

    # LLM feedback
    analysis: str = ""
    improvement_suggestions: List[str] = field(default_factory=list)

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    stage: int = 1  # Which stage created this node

    # Flags
    is_buggy: bool = False
    is_complete: bool = False

    # Tree-search fields (from AI-Scientist)
    stage_name: NodeStageType = "draft"  # draft, debug, or improve
    quality_issues: List[str] = field(default_factory=list)  # List of quality problems
    draft_perspective: str = ""  # technical, business, user (for parallel drafts)

    @property
    def debug_depth(self) -> int:
        """Count consecutive debug stages in parent chain (for max_debug_depth check)."""
        if self.stage_name != "debug":
            return 0
        # This would need journal access to traverse parents - simplified version
        return 1 if self.parent_version_id else 0

    def check_quality(self, thresholds: Dict[str, float]) -> bool:
        """
        Check if node meets quality thresholds.
        Sets is_buggy and quality_issues based on results.

        Args:
            thresholds: Dict with min_completeness, min_consistency, etc.

        Returns:
            True if all thresholds are met, False otherwise.
        """
        from ..utils.metrics import check_thresholds

        scores = {
            "completeness": self.completeness_score,
            "consistency": self.consistency_score,
            "testability": self.testability_score,
            "clarity": self.clarity_score,
            "feasibility": self.feasibility_score,
            "traceability": self.traceability_score,
        }

        self.quality_issues = check_thresholds(scores, thresholds)
        self.is_buggy = len(self.quality_issues) > 0
        return not self.is_buggy

    def aggregate_score(self, weights: Dict[str, float] = None) -> float:
        """Calculate weighted average of all quality metrics.

        Args:
            weights: Optional dict mapping metric name to weight.
                     If None, uses default weights.
                     Weights are from re_config.yaml 'metric_weights' section.
        """
        from ..utils.metrics import weighted_score

        scores = {
            "completeness": self.completeness_score,
            "consistency": self.consistency_score,
            "testability": self.testability_score,
            "clarity": self.clarity_score,
            "feasibility": self.feasibility_score,
            "traceability": self.traceability_score,
        }

        if weights is None:
            weights = {
                "completeness": 0.20,
                "consistency": 0.20,
                "testability": 0.15,
                "clarity": 0.15,
                "feasibility": 0.15,
                "traceability": 0.15,
            }

        return weighted_score(scores, weights)

    def to_markdown(self) -> str:
        """Convert requirement to markdown format."""
        md = f"## {self.requirement_id}: {self.title}\n\n"
        md += f"**Type:** {self.type}\n"
        md += f"**Priority:** {self.priority.upper()}\n"
        md += f"**Status:** {self.validation_status}\n\n"

        md += f"### Description\n{self.description}\n\n"

        if self.rationale:
            md += f"### Rationale\n{self.rationale}\n\n"

        if self.acceptance_criteria:
            md += "### Acceptance Criteria\n"
            for i, criterion in enumerate(self.acceptance_criteria, 1):
                md += f"{i}. {criterion}\n"
            md += "\n"

        if self.dependencies:
            md += f"### Dependencies\n{', '.join(self.dependencies)}\n\n"

        if self.mermaid_diagrams:
            md += "### Diagrams\n"
            for diagram_type, diagram_code in self.mermaid_diagrams.items():
                md += f"#### {diagram_type.title()}\n```mermaid\n{diagram_code}\n```\n\n"

        return md


@dataclass_json
@dataclass
class RequirementSet:
    """A set of related requirements (e.g., for a feature or service)."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    name: str = ""
    description: str = ""
    work_breakdown_type: str = "per_feature"  # per_feature, per_service, per_application
    requirements: List[str] = field(default_factory=list)  # List of requirement IDs

    # Aggregate metrics
    total_requirements: int = 0
    completed_requirements: int = 0
    aggregate_score: float = 0.0

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class RequirementJournal:
    """
    Journal for tracking all requirement versions and iterations.
    Maintains a tree structure of requirement specifications.
    """

    def __init__(self, project_name: str = ""):
        self.project_name = project_name
        self.nodes: Dict[str, RequirementNode] = {}
        self.requirement_sets: Dict[str, RequirementSet] = {}
        self.root_nodes: List[str] = []  # IDs of root nodes (no parent)
        self.current_stage: int = 1
        self.created_at: str = datetime.now().isoformat()

        # Counter for requirement IDs
        self._req_counter: int = 0

    def generate_requirement_id(self, prefix: str = "REQ", padding: int = 3) -> str:
        """Generate a new requirement ID."""
        self._req_counter += 1
        return f"{prefix}-{str(self._req_counter).zfill(padding)}"

    def add_node(self, node: RequirementNode) -> str:
        """Add a requirement node to the journal."""
        if not node.requirement_id:
            node.requirement_id = self.generate_requirement_id()

        self.nodes[node.id] = node

        if node.parent_version_id is None:
            self.root_nodes.append(node.id)
        else:
            # Update parent's children
            if node.parent_version_id in self.nodes:
                self.nodes[node.parent_version_id].children_version_ids.add(node.id)

        return node.id

    def get_node(self, node_id: str) -> Optional[RequirementNode]:
        """Get a requirement node by ID."""
        return self.nodes.get(node_id)

    def get_by_requirement_id(self, req_id: str) -> Optional[RequirementNode]:
        """Get the latest version of a requirement by requirement ID."""
        matching = [n for n in self.nodes.values() if n.requirement_id == req_id]
        if not matching:
            return None
        # Return the one with highest version
        return max(matching, key=lambda x: x.version)

    def get_all_requirements(self) -> List[RequirementNode]:
        """Get all requirement nodes."""
        return list(self.nodes.values())

    def get_good_nodes(self) -> List[RequirementNode]:
        """Get all non-buggy requirement nodes."""
        return [n for n in self.nodes.values() if not n.is_buggy]

    def get_validated_nodes(self) -> List[RequirementNode]:
        """Get all validated requirement nodes."""
        return [n for n in self.nodes.values() if n.validation_status == "validated"]

    def get_best_node(self, metric_weights: Dict[str, float] = None) -> Optional[RequirementNode]:
        """Get the best requirement specification based on aggregate score."""
        good_nodes = self.get_good_nodes()
        if not good_nodes:
            return None
        return max(good_nodes, key=lambda n: n.aggregate_score(metric_weights))

    def get_nodes_by_stage(self, stage: int) -> List[RequirementNode]:
        """Get all nodes created in a specific stage."""
        return [n for n in self.nodes.values() if n.stage == stage]

    def get_draft_nodes(self) -> List[RequirementNode]:
        """Get all draft nodes (root level, not debug/improve)."""
        return [n for n in self.nodes.values() if n.stage_name == "draft"]

    def get_debug_depth(self, node: RequirementNode) -> int:
        """Calculate the debug depth by traversing parent chain."""
        depth = 0
        current = node
        while current.stage_name == "debug" and current.parent_version_id:
            depth += 1
            parent = self.get_node(current.parent_version_id)
            if parent is None:
                break
            current = parent
        return depth

    def get_best_draft(self, metric_weights: Dict[str, float] = None) -> Optional[RequirementNode]:
        """Get the best draft node based on aggregate score."""
        drafts = self.get_draft_nodes()
        good_drafts = [d for d in drafts if not d.is_buggy]
        if not good_drafts:
            # Fall back to all drafts if none are good
            good_drafts = drafts
        if not good_drafts:
            return None
        return max(good_drafts, key=lambda n: n.aggregate_score(metric_weights))

    def get_buggy_nodes(self) -> List[RequirementNode]:
        """Get all nodes with quality issues."""
        return [n for n in self.nodes.values() if n.is_buggy]

    def create_requirement_set(
        self,
        name: str,
        requirement_ids: List[str],
        work_breakdown_type: str = "per_feature"
    ) -> RequirementSet:
        """Create a requirement set for work breakdown."""
        req_set = RequirementSet(
            name=name,
            work_breakdown_type=work_breakdown_type,
            requirements=requirement_ids,
            total_requirements=len(requirement_ids)
        )

        # Calculate aggregate metrics
        nodes = [self.get_by_requirement_id(rid) for rid in requirement_ids]
        nodes = [n for n in nodes if n is not None]

        if nodes:
            req_set.completed_requirements = sum(1 for n in nodes if n.is_complete)
            req_set.aggregate_score = sum(n.aggregate_score() for n in nodes) / len(nodes)

        self.requirement_sets[req_set.id] = req_set
        return req_set

    def generate_traceability_matrix(self) -> Dict[str, Any]:
        """Generate a traceability matrix of all requirements."""
        matrix = {
            "requirements": [],
            "dependencies": [],
            "conflicts": []
        }

        for node in self.get_good_nodes():
            req_info = {
                "id": node.requirement_id,
                "title": node.title,
                "type": node.type,
                "priority": node.priority,
                "status": node.validation_status,
                "work_package": node.work_package,
                "score": node.aggregate_score()
            }
            matrix["requirements"].append(req_info)

            for dep in node.dependencies:
                matrix["dependencies"].append({
                    "from": node.requirement_id,
                    "to": dep
                })

            for conflict in node.conflicts:
                matrix["conflicts"].append({
                    "req1": node.requirement_id,
                    "req2": conflict
                })

        return matrix

    def to_markdown(self) -> str:
        """Export journal to markdown format."""
        md = f"# Requirements Specification: {self.project_name}\n\n"
        md += f"Generated: {datetime.now().isoformat()}\n\n"

        # Summary
        all_nodes = self.get_good_nodes()
        md += "## Summary\n\n"
        md += f"- Total Requirements: {len(all_nodes)}\n"
        md += f"- Validated: {len(self.get_validated_nodes())}\n"

        # Group by type
        by_type = {}
        for node in all_nodes:
            by_type.setdefault(node.type, []).append(node)

        for req_type, nodes in by_type.items():
            md += f"\n## {req_type.replace('_', ' ').title()} Requirements\n\n"
            for node in sorted(nodes, key=lambda x: x.requirement_id):
                md += node.to_markdown()
                md += "---\n\n"

        return md

    def to_dict(self) -> Dict[str, Any]:
        """Convert journal to dictionary."""
        return {
            "project_name": self.project_name,
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "requirement_sets": {k: v.to_dict() for k, v in self.requirement_sets.items()},
            "root_nodes": self.root_nodes,
            "current_stage": self.current_stage,
            "created_at": self.created_at,
            "_req_counter": self._req_counter
        }

    def save(self, filepath: str):
        """Save journal to JSON file."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, filepath: str) -> "RequirementJournal":
        """Load journal from JSON file."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        journal = cls(data.get("project_name", ""))
        journal.nodes = {k: RequirementNode.from_dict(v) for k, v in data.get("nodes", {}).items()}
        journal.requirement_sets = {k: RequirementSet.from_dict(v) for k, v in data.get("requirement_sets", {}).items()}
        journal.root_nodes = data.get("root_nodes", [])
        journal.current_stage = data.get("current_stage", 1)
        journal.created_at = data.get("created_at", datetime.now().isoformat())
        journal._req_counter = data.get("_req_counter", 0)

        return journal
