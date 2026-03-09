"""
Post-Generation Evaluation & Refinement Loop.

Iterates over any RE pipeline output directory, evaluates cross-artifact
completeness, identifies gaps, and automatically fixes them to produce
a full architecture suitable for a coding pipeline.

Usage:
    # CLI
    python -m requirements_engineer.refinement <output_dir> --dry-run
    python -m requirements_engineer.refinement <output_dir> --max-iterations 5

    # Programmatic
    from requirements_engineer.refinement import RefinementLoop, ArtifactLoader
    loader = ArtifactLoader(output_dir)
    bundle = loader.load_all()
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class LoadStatus(Enum):
    """Status of loading a single artifact file."""
    LOADED = "loaded"
    MISSING = "missing"
    PARSE_ERROR = "parse_error"
    EMPTY = "empty"


class GapFixStrategy(Enum):
    """How a gap can be fixed."""
    AUTO_LINK = "auto_link"          # Programmatic cross-reference creation
    LLM_EXTEND = "llm_extend"       # LLM extends/enriches existing artifact
    GENERATOR = "generator"          # Re-invoke a pipeline generator
    MANUAL = "manual"                # Requires human input


class GapSeverity(Enum):
    """Impact level of a gap."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class FileLoadResult:
    """Result of loading a single artifact file."""
    path: str
    status: LoadStatus
    item_count: int = 0
    error: str = ""


@dataclass
class ArtifactBundle:
    """All artifacts loaded from an output directory."""
    output_dir: Path = field(default_factory=Path)

    # Core artifacts
    requirements: List[Any] = field(default_factory=list)
    user_stories: List[Any] = field(default_factory=list)
    epics: List[Any] = field(default_factory=list)
    test_cases: List[Any] = field(default_factory=list)
    api_endpoints: List[Any] = field(default_factory=list)
    screens: List[Any] = field(default_factory=list)
    screen_compositions: List[Any] = field(default_factory=list)
    entities: Dict[str, Any] = field(default_factory=dict)
    relationships: List[Any] = field(default_factory=list)
    tasks: List[Any] = field(default_factory=list)
    task_breakdown: Optional[Any] = None
    tech_stack: Optional[Any] = None
    ux_spec: Optional[Any] = None
    ui_spec: Optional[Any] = None
    arch_spec: Optional[Any] = None
    state_machines: List[Any] = field(default_factory=list)
    personas: List[Any] = field(default_factory=list)
    user_flows: List[Any] = field(default_factory=list)
    diagrams: Dict[str, str] = field(default_factory=dict)

    # Load metadata
    file_results: List[FileLoadResult] = field(default_factory=list)

    # Convenience indices (populated by ArtifactLoader._build_indices)
    req_by_id: Dict[str, Any] = field(default_factory=dict)
    story_by_id: Dict[str, Any] = field(default_factory=dict)
    epic_by_id: Dict[str, Any] = field(default_factory=dict)
    test_by_id: Dict[str, Any] = field(default_factory=dict)
    screen_by_id: Dict[str, Any] = field(default_factory=dict)
    task_by_id: Dict[str, Any] = field(default_factory=dict)
    endpoint_by_key: Dict[str, Any] = field(default_factory=dict)

    @property
    def loaded_count(self) -> int:
        return sum(1 for r in self.file_results if r.status == LoadStatus.LOADED)

    @property
    def missing_count(self) -> int:
        return sum(1 for r in self.file_results if r.status == LoadStatus.MISSING)

    def summary(self) -> Dict[str, int]:
        return {
            "requirements": len(self.requirements),
            "user_stories": len(self.user_stories),
            "epics": len(self.epics),
            "test_cases": len(self.test_cases),
            "api_endpoints": len(self.api_endpoints),
            "screens": len(self.screens),
            "entities": len(self.entities),
            "tasks": len(self.tasks),
            "state_machines": len(self.state_machines),
            "user_flows": len(self.user_flows),
            "diagrams": len(self.diagrams),
        }


@dataclass
class Gap:
    """A single completeness gap found during checking."""
    gap_id: str                          # GAP-001
    rule_id: str                         # e.g. "req_to_story"
    severity: GapSeverity = GapSeverity.MEDIUM
    title: str = ""
    description: str = ""
    affected_ids: List[str] = field(default_factory=list)
    current_value: float = 0.0           # Current metric
    target_value: float = 1.0            # Threshold
    fix_strategy: GapFixStrategy = GapFixStrategy.MANUAL
    generator_name: Optional[str] = None


@dataclass
class RuleResult:
    """Result of a single completeness rule check."""
    rule_id: str
    rule_name: str
    current_value: float                 # Raw metric
    target_value: float                  # Threshold
    score: float                         # 0.0-1.0 (clamped current/target)
    weight: float                        # Weight in overall score
    gaps: List[Gap] = field(default_factory=list)
    passed: bool = False


@dataclass
class CompletenessReport:
    """Result of all completeness checks."""
    rule_results: List[RuleResult] = field(default_factory=list)
    overall_score: float = 0.0
    timestamp: str = ""

    @property
    def all_gaps(self) -> List[Gap]:
        gaps = []
        for rr in self.rule_results:
            gaps.extend(rr.gaps)
        return gaps

    @property
    def scores(self) -> Dict[str, float]:
        return {rr.rule_id: rr.score for rr in self.rule_results}


@dataclass
class RefinementResult:
    """Result of the full refinement loop."""
    iterations: int = 0
    before_scores: Dict[str, float] = field(default_factory=dict)
    after_scores: Dict[str, float] = field(default_factory=dict)
    before_overall: float = 0.0
    after_overall: float = 0.0
    gaps_found: int = 0
    gaps_fixed: int = 0
    gaps_remaining: int = 0
    fix_log: List[str] = field(default_factory=list)
    total_llm_calls: int = 0
    total_cost_usd: float = 0.0
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Default Configuration
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS = {
    "req_to_story": 0.95,
    "story_to_test": 0.90,
    "story_to_screen": 0.80,
    "api_to_req": 0.90,
    "entity_to_req": 0.70,
    "state_machine_density": 0.60,
    "task_backlinks": 0.80,
    "task_ratio": 2.0,
    "component_count": 0.80,
    "flow_coverage": 0.80,
    "quality_gates": 1.0,
    "test_api_linkage": 0.50,
}

DEFAULT_WEIGHTS = {
    "req_to_story": 0.15,
    "story_to_test": 0.15,
    "story_to_screen": 0.10,
    "api_to_req": 0.08,
    "entity_to_req": 0.07,
    "state_machine_density": 0.05,
    "task_backlinks": 0.05,
    "task_ratio": 0.08,
    "component_count": 0.05,
    "flow_coverage": 0.07,
    "quality_gates": 0.05,
    "test_api_linkage": 0.10,
}
