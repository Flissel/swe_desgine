"""
Trace Node - Unified wrapper for artifacts in the trace tree.

Provides a uniform interface for tree-search operations across
RequirementNode, UserStory, and TestCase artifacts.

Two-axis tree:
- Trace axis (horizontal): Epic → Requirement → UserStory → TestCase
- Version axis (vertical): draft → improve → improve (refinement history)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime


# Valid node types in the trace tree
NODE_TYPES = ("epic", "requirement", "user_story", "test_case")

# Valid stage names mirroring AI-Scientist's node stages
STAGE_NAMES = ("draft", "improve", "debug")


@dataclass
class TraceNode:
    """Uniform wrapper for any artifact in the trace tree.

    Wraps RequirementNode, UserStory, or TestCase to provide a consistent
    interface for evaluation, expansion, and iteration tracking.
    """

    # Identity
    node_id: str = ""                # e.g. "REQ-001", "US-001", "TC-001"
    node_type: str = "requirement"   # epic | requirement | user_story | test_case

    # The actual artifact (RequirementNode / UserStory / TestCase / Epic)
    artifact: Any = None

    # Trace axis (parent/children in domain model)
    parent_trace: Optional['TraceNode'] = None
    children_trace: List['TraceNode'] = field(default_factory=list)

    # Version axis (refinement history)
    versions: List[Any] = field(default_factory=list)
    current_version: int = 0

    # Quality scores
    quality_score: float = 0.0
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    is_complete: bool = False
    quality_issues: List[str] = field(default_factory=list)

    # Iteration tracking
    iteration_count: int = 0
    max_iterations: int = 3
    stage_name: str = "draft"        # draft | improve | debug

    # Audit trail
    refinement_log: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if self.node_type not in NODE_TYPES:
            raise ValueError(f"Invalid node_type: {self.node_type}. Must be one of {NODE_TYPES}")
        if self.stage_name not in STAGE_NAMES:
            raise ValueError(f"Invalid stage_name: {self.stage_name}. Must be one of {STAGE_NAMES}")
        # Store initial artifact as version 0
        if self.artifact is not None and not self.versions:
            self.versions.append(self.artifact)

    @property
    def depth(self) -> int:
        """Depth in the trace tree (epic=0, requirement=1, story=2, test=3)."""
        depth = 0
        node = self.parent_trace
        while node is not None:
            depth += 1
            node = node.parent_trace
        return depth

    @property
    def is_leaf(self) -> bool:
        """True if this node has no children in the trace axis."""
        return len(self.children_trace) == 0

    @property
    def trace_path(self) -> List[str]:
        """Full path from root to this node, e.g. ['EPIC-001', 'REQ-001', 'US-001']."""
        path = []
        node = self
        while node is not None:
            path.append(node.node_id)
            node = node.parent_trace
        return list(reversed(path))

    def record_refinement(self, new_artifact: Any, stage: str, score_before: float, score_after: float):
        """Record a refinement step in the audit trail."""
        self.versions.append(new_artifact)
        self.current_version = len(self.versions) - 1
        self.artifact = new_artifact
        self.iteration_count += 1
        self.stage_name = stage
        self.refinement_log.append(
            f"v{self.current_version} ({stage}): {score_before:.2f} → {score_after:.2f}"
        )

    def get_parent_context(self) -> Dict[str, Any]:
        """Extract context from trace parent for evaluation/expansion."""
        if self.parent_trace is None:
            return {}

        parent = self.parent_trace
        ctx = {
            "parent_id": parent.node_id,
            "parent_type": parent.node_type,
        }

        art = parent.artifact
        if parent.node_type == "epic":
            ctx["epic_title"] = getattr(art, "title", "")
            ctx["epic_description"] = getattr(art, "description", "")
            ctx["epic_requirements"] = getattr(art, "parent_requirements", [])
        elif parent.node_type == "requirement":
            ctx["req_id"] = getattr(art, "requirement_id", "")
            ctx["req_title"] = getattr(art, "title", "")
            ctx["req_description"] = getattr(art, "description", "")
            ctx["req_acceptance_criteria"] = getattr(art, "acceptance_criteria", [])
            ctx["req_type"] = getattr(art, "type", "functional")
            ctx["req_priority"] = getattr(art, "priority", "should")
        elif parent.node_type == "user_story":
            ctx["story_id"] = getattr(art, "id", "")
            ctx["story_title"] = getattr(art, "title", "")
            ctx["story_persona"] = getattr(art, "persona", "")
            ctx["story_action"] = getattr(art, "action", "")
            ctx["story_benefit"] = getattr(art, "benefit", "")
            criteria = getattr(art, "acceptance_criteria", [])
            ctx["story_acceptance_criteria"] = [
                {"given": getattr(ac, "given", ""), "when": getattr(ac, "when", ""), "then": getattr(ac, "then", "")}
                for ac in criteria
            ]

        return ctx

    def to_summary(self) -> Dict[str, Any]:
        """Compact summary for audit trail / reporting."""
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "quality_score": round(self.quality_score, 3),
            "is_complete": self.is_complete,
            "iterations": self.iteration_count,
            "versions": len(self.versions),
            "children": len(self.children_trace),
            "stage": self.stage_name,
            "dimension_scores": {k: round(v, 3) for k, v in self.dimension_scores.items()},
            "issues": self.quality_issues,
            "refinement_log": self.refinement_log,
        }


@dataclass
class TraceWalkResult:
    """Result of walking one epic's trace tree."""

    epic_id: str = ""
    epic_title: str = ""

    # Counts
    nodes_total: int = 0
    nodes_refined: int = 0       # Nodes that went through at least 1 refinement
    nodes_complete: int = 0      # Nodes that reached quality threshold

    # Quality
    avg_quality: float = 0.0
    min_quality: float = 0.0
    max_quality: float = 0.0

    # LLM usage
    llm_calls_used: int = 0

    # Per-node details
    node_summaries: List[Dict[str, Any]] = field(default_factory=list)

    # Timing
    duration_seconds: float = 0.0
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_markdown(self) -> str:
        """Generate markdown summary of the walk result."""
        md = f"## Trace Refinement: {self.epic_id} — {self.epic_title}\n\n"
        md += f"- **Nodes total:** {self.nodes_total}\n"
        md += f"- **Refined:** {self.nodes_refined}\n"
        md += f"- **Complete:** {self.nodes_complete}/{self.nodes_total}\n"
        md += f"- **Avg quality:** {self.avg_quality:.0%}\n"
        md += f"- **LLM calls:** {self.llm_calls_used}\n"
        md += f"- **Duration:** {self.duration_seconds:.1f}s\n\n"

        if self.node_summaries:
            md += "### Per-Node Details\n\n"
            md += "| Node | Type | Score | Iterations | Complete |\n"
            md += "|------|------|-------|------------|----------|\n"
            for ns in self.node_summaries:
                complete = "yes" if ns.get("is_complete") else "no"
                md += (
                    f"| {ns['node_id']} | {ns['node_type']} "
                    f"| {ns['quality_score']:.0%} | {ns['iterations']} | {complete} |\n"
                )
            md += "\n"

        return md
