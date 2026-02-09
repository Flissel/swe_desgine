"""
Presentation Ledger System for Multi-Agent HTML Generation.

Implements the Magentic-One inspired Task and Progress Ledger pattern
for tracking presentation generation state, decisions, and progress.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum, auto
import logging
import json

log = logging.getLogger(__name__)


# ============================================
# Action Record Types
# ============================================

class ActionType(Enum):
    """Types of actions that can be recorded."""
    ANALYZE_CONTENT = auto()
    GENERATE_HTML = auto()
    REVIEW_HTML = auto()
    IMPROVE_HTML = auto()
    ADD_SECTION = auto()
    ENHANCE_CONTENT = auto()
    FIX_STRUCTURE = auto()
    ADD_STYLING = auto()
    GENERATE_DIAGRAM = auto()
    KILO_GENERATION = auto()
    CONSOLIDATE = auto()
    GENERATE_SCAFFOLD = auto()
    REVIEW_SCAFFOLD = auto()
    IMPROVE_SCAFFOLD = auto()
    PLACE_DOCUMENTS = auto()
    GENERATE_SCREEN = auto()
    REVIEW_SCREEN = auto()
    IMPROVE_SCREEN = auto()
    SAVE_SCREEN_FILES = auto()


@dataclass
class PresentationActionRecord:
    """
    Record of a single agent action in the presentation pipeline.

    Tracks what was done, by whom, and whether it improved quality.
    """
    agent_name: str
    action_type: ActionType
    target_page: Optional[str] = None
    description: str = ""
    success: bool = True
    quality_before: Optional[float] = None
    quality_after: Optional[float] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    duration_seconds: float = 0.0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def improvement_achieved(self) -> bool:
        """Check if this action improved quality."""
        if self.quality_before is None or self.quality_after is None:
            return False
        return self.quality_after > self.quality_before

    def improvement_delta(self) -> float:
        """Calculate the improvement delta."""
        if self.quality_before is None or self.quality_after is None:
            return 0.0
        return self.quality_after - self.quality_before

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "agent_name": self.agent_name,
            "action_type": self.action_type.name,
            "target_page": self.target_page,
            "description": self.description,
            "success": self.success,
            "quality_before": self.quality_before,
            "quality_after": self.quality_after,
            "timestamp": self.timestamp,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
            "metadata": self.metadata
        }


@dataclass
class FailedAttempt:
    """Record of a failed improvement attempt."""
    page_id: str
    action_type: ActionType
    error_type: Optional[str] = None
    error_message: str = ""
    attempted_fix: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# ============================================
# Task Ledger (What do we know?)
# ============================================

@dataclass
class PresentationTaskLedger:
    """
    Task Ledger - What do we know about the presentation task?

    Inspired by Magentic-One's Task Ledger, this tracks facts,
    design decisions, and the overall plan for HTML generation.
    """

    # Project context
    project_id: str = ""
    project_name: str = ""

    # Facts discovered during analysis
    facts: List[str] = field(default_factory=list)

    # Design decisions made
    design_decisions: List[str] = field(default_factory=list)

    # Artifact statistics from RE stages
    artifact_stats: Dict[str, int] = field(default_factory=dict)

    # Quality targets for each aspect
    quality_targets: Dict[str, float] = field(default_factory=lambda: {
        "structure": 0.8,
        "content": 0.8,
        "styling": 0.7,
        "navigation": 0.8,
        "accessibility": 0.7,
        "overall": 0.75
    })

    # Planned pages to generate
    page_plan: List[Dict[str, Any]] = field(default_factory=list)

    # Consolidation plan (what to merge/combine)
    consolidation_plan: List[str] = field(default_factory=list)

    # Failed approaches to avoid
    failed_approaches: List[str] = field(default_factory=list)

    # Open questions needing resolution
    open_questions: List[str] = field(default_factory=list)

    # Insights discovered during generation
    insights: List[str] = field(default_factory=list)

    def add_fact(self, fact: str) -> None:
        """Add a discovered fact."""
        if fact not in self.facts:
            self.facts.append(fact)
            log.debug(f"TaskLedger: Added fact - {fact[:50]}...")

    def add_design_decision(self, decision: str) -> None:
        """Record a design decision."""
        if decision not in self.design_decisions:
            self.design_decisions.append(decision)
            log.info(f"TaskLedger: Design decision - {decision[:50]}...")

    def add_artifact_stat(self, artifact_type: str, count: int) -> None:
        """Record artifact statistics."""
        self.artifact_stats[artifact_type] = count

    def add_page_to_plan(self, page_config: Dict[str, Any]) -> None:
        """Add a page to the generation plan."""
        self.page_plan.append(page_config)

    def add_insight(self, insight: str) -> None:
        """Record an insight discovered during generation."""
        if insight not in self.insights:
            self.insights.append(insight)
            log.info(f"TaskLedger: Insight - {insight[:50]}...")

    def mark_approach_failed(self, approach: str) -> None:
        """Mark an approach as failed to avoid repeating it."""
        if approach not in self.failed_approaches:
            self.failed_approaches.append(approach)
            log.warning(f"TaskLedger: Failed approach - {approach[:50]}...")

    def get_context_summary(self, max_items: int = 5) -> str:
        """Generate a summary for LLM context."""
        lines = []

        lines.append(f"Project: {self.project_name or self.project_id}")

        if self.artifact_stats:
            lines.append("Artifacts:")
            for artifact_type, count in sorted(self.artifact_stats.items()):
                lines.append(f"  - {artifact_type}: {count}")

        if self.facts:
            lines.append(f"\nKey Facts ({len(self.facts)}):")
            for fact in self.facts[-max_items:]:
                lines.append(f"  - {fact}")

        if self.design_decisions:
            lines.append(f"\nDesign Decisions ({len(self.design_decisions)}):")
            for decision in self.design_decisions[-max_items:]:
                lines.append(f"  - {decision}")

        if self.insights:
            lines.append(f"\nRecent Insights ({len(self.insights)}):")
            for insight in self.insights[-max_items:]:
                lines.append(f"  - {insight}")

        if self.failed_approaches:
            lines.append(f"\nFailed Approaches (avoid):")
            for approach in self.failed_approaches[-3:]:
                lines.append(f"  - {approach}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "facts": self.facts,
            "design_decisions": self.design_decisions,
            "artifact_stats": self.artifact_stats,
            "quality_targets": self.quality_targets,
            "page_plan": self.page_plan,
            "consolidation_plan": self.consolidation_plan,
            "failed_approaches": self.failed_approaches,
            "open_questions": self.open_questions,
            "insights": self.insights
        }

    def __str__(self) -> str:
        return (
            f"PresentationTaskLedger(facts={len(self.facts)}, "
            f"decisions={len(self.design_decisions)}, "
            f"pages_planned={len(self.page_plan)})"
        )


# ============================================
# Progress Ledger (How far have we come?)
# ============================================

@dataclass
class PresentationProgressLedger:
    """
    Progress Ledger - How far have we come?

    Tracks completed actions, quality scores over time, and detects
    stagnation for adaptive replanning.
    """

    # Action tracking
    completed_actions: List[PresentationActionRecord] = field(default_factory=list)
    failed_attempts: List[FailedAttempt] = field(default_factory=list)

    # Iteration tracking
    current_iteration: int = 0
    max_iterations: int = 5

    # Quality tracking per page
    page_quality_scores: Dict[str, List[float]] = field(default_factory=dict)

    # Overall quality history
    quality_history: List[Dict[str, float]] = field(default_factory=list)
    best_quality_score: float = 0.0

    # Stagnation detection
    stagnation_counter: int = 0
    stagnation_threshold: int = 2  # Iterations without improvement
    last_improvement_iteration: int = 0

    # Replan tracking
    replan_count: int = 0
    max_replans: int = 3

    # Configuration
    min_quality_threshold: float = 0.6  # Minimum acceptable quality
    target_quality: float = 0.8  # Target quality to achieve

    def record_action(self, action: PresentationActionRecord) -> None:
        """Record a completed action."""
        self.completed_actions.append(action)

        if action.success and action.improvement_achieved():
            self.last_improvement_iteration = self.current_iteration
            self.stagnation_counter = 0
            log.info(f"ProgressLedger: Improvement achieved - {action.action_type.name}")
        elif action.success:
            self.stagnation_counter += 1

        log.debug(f"ProgressLedger: Recorded action - {action.agent_name}/{action.action_type.name}")

    def record_failure(self, failure: FailedAttempt) -> None:
        """Record a failed attempt."""
        self.failed_attempts.append(failure)
        self.stagnation_counter += 1
        log.warning(f"ProgressLedger: Recorded failure - {failure.action_type.name}")

    def record_page_quality(self, page_id: str, quality: float) -> None:
        """Record quality score for a page."""
        if page_id not in self.page_quality_scores:
            self.page_quality_scores[page_id] = []
        self.page_quality_scores[page_id].append(quality)

    def record_iteration_quality(self, quality_scores: Dict[str, float]) -> None:
        """Record quality scores for an iteration."""
        self.quality_history.append(quality_scores)

        overall = quality_scores.get("overall", 0.0)
        if overall > self.best_quality_score:
            self.best_quality_score = overall
            self.last_improvement_iteration = self.current_iteration
            self.stagnation_counter = 0
            log.info(f"ProgressLedger: New best quality: {overall:.2f}")
        else:
            self.stagnation_counter += 1

    def advance_iteration(self) -> bool:
        """
        Advance to next iteration.

        Returns False if max iterations reached.
        """
        self.current_iteration += 1
        if self.current_iteration > self.max_iterations:
            log.warning(f"ProgressLedger: Max iterations ({self.max_iterations}) reached")
            return False
        return True

    def detect_stagnation(self) -> bool:
        """Detect if progress has stagnated."""
        return self.stagnation_counter >= self.stagnation_threshold

    def should_replan(self) -> bool:
        """Determine if a plan revision is recommended."""
        if self.replan_count >= self.max_replans:
            log.warning("ProgressLedger: Max replans reached")
            return False

        if self.detect_stagnation():
            log.info("ProgressLedger: Stagnation detected, recommending replan")
            return True

        # Check for excessive consecutive failures
        recent_failures = len([a for a in self.completed_actions[-5:] if not a.success])
        if recent_failures >= 3:
            log.info("ProgressLedger: Excessive failures, recommending replan")
            return True

        return False

    def mark_replan(self) -> None:
        """Mark that a replan has occurred."""
        self.replan_count += 1
        self.stagnation_counter = 0
        log.info(f"ProgressLedger: Replan #{self.replan_count} marked")

    def quality_target_reached(self) -> bool:
        """Check if target quality has been reached."""
        return self.best_quality_score >= self.target_quality

    def get_success_rate(self) -> float:
        """Calculate overall success rate."""
        if not self.completed_actions:
            return 0.0
        successful = sum(1 for a in self.completed_actions if a.success)
        return successful / len(self.completed_actions)

    def get_improvement_rate(self) -> float:
        """Calculate rate of actions that led to improvement."""
        if not self.completed_actions:
            return 0.0
        improved = sum(1 for a in self.completed_actions if a.improvement_achieved())
        return improved / len(self.completed_actions)

    def get_recent_actions(self, n: int = 5) -> List[PresentationActionRecord]:
        """Get the n most recent actions."""
        return self.completed_actions[-n:]

    def get_progress_summary(self) -> str:
        """Generate a progress summary for logging/LLM context."""
        lines = [
            f"Iteration: {self.current_iteration}/{self.max_iterations}",
            f"Best Quality: {self.best_quality_score:.1%}",
            f"Target Quality: {self.target_quality:.1%}",
            f"Success Rate: {self.get_success_rate():.1%}",
            f"Improvement Rate: {self.get_improvement_rate():.1%}",
            f"Stagnation: {self.stagnation_counter}/{self.stagnation_threshold}",
            f"Replans: {self.replan_count}/{self.max_replans}",
        ]

        if self.page_quality_scores:
            lines.append("\nPage Quality Scores:")
            for page_id, scores in self.page_quality_scores.items():
                if scores:
                    lines.append(f"  - {page_id}: {scores[-1]:.1%}")

        recent = self.get_recent_actions(3)
        if recent:
            lines.append("\nRecent Actions:")
            for action in recent:
                status = "OK" if action.success else "FAIL"
                delta = f"+{action.improvement_delta():.1%}" if action.improvement_achieved() else ""
                lines.append(f"  [{status}] {action.agent_name}/{action.action_type.name} {delta}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "current_iteration": self.current_iteration,
            "max_iterations": self.max_iterations,
            "best_quality_score": self.best_quality_score,
            "quality_history": self.quality_history,
            "page_quality_scores": self.page_quality_scores,
            "stagnation_counter": self.stagnation_counter,
            "replan_count": self.replan_count,
            "completed_actions": [a.to_dict() for a in self.completed_actions],
            "failed_attempts_count": len(self.failed_attempts)
        }

    def __str__(self) -> str:
        return (
            f"PresentationProgressLedger(iteration={self.current_iteration}, "
            f"best_quality={self.best_quality_score:.1%}, "
            f"stagnation={self.stagnation_counter})"
        )


# ============================================
# Ledger Manager
# ============================================

@dataclass
class PresentationLedgerManager:
    """
    Manages both Task and Progress Ledgers together.

    Provides a unified interface for the orchestrator to interact with
    the Magentic-One inspired ledger system.
    """

    task_ledger: PresentationTaskLedger = field(default_factory=PresentationTaskLedger)
    progress_ledger: PresentationProgressLedger = field(default_factory=PresentationProgressLedger)

    def initialize_from_project(
        self,
        project_id: str,
        project_name: str,
        artifact_stats: Dict[str, int],
        config: Optional[Dict[str, Any]] = None
    ) -> None:
        """Initialize ledgers from project context."""
        self.task_ledger.project_id = project_id
        self.task_ledger.project_name = project_name

        for artifact_type, count in artifact_stats.items():
            self.task_ledger.add_artifact_stat(artifact_type, count)
            if count > 0:
                self.task_ledger.add_fact(f"Project has {count} {artifact_type}(s)")

        if config:
            # Apply quality targets from config
            if "quality_targets" in config:
                self.task_ledger.quality_targets.update(config["quality_targets"])

            # Apply iteration limits
            if "max_iterations" in config:
                self.progress_ledger.max_iterations = config["max_iterations"]
            if "stagnation_threshold" in config:
                self.progress_ledger.stagnation_threshold = config["stagnation_threshold"]
            if "max_replans" in config:
                self.progress_ledger.max_replans = config["max_replans"]
            if "target_quality" in config:
                self.progress_ledger.target_quality = config["target_quality"]

        log.info(f"LedgerManager: Initialized for project {project_name}")

    def record_agent_action(
        self,
        agent_name: str,
        action_type: ActionType,
        success: bool,
        target_page: Optional[str] = None,
        description: str = "",
        quality_before: Optional[float] = None,
        quality_after: Optional[float] = None,
        duration: float = 0.0,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> PresentationActionRecord:
        """
        Record an agent action in both ledgers.

        Returns the ActionRecord for further use.
        """
        action = PresentationActionRecord(
            agent_name=agent_name,
            action_type=action_type,
            target_page=target_page,
            description=description,
            success=success,
            quality_before=quality_before,
            quality_after=quality_after,
            duration_seconds=duration,
            error_message=error_message,
            metadata=metadata or {}
        )

        self.progress_ledger.record_action(action)

        if not success and error_message:
            failure = FailedAttempt(
                page_id=target_page or "unknown",
                action_type=action_type,
                error_message=error_message
            )
            self.progress_ledger.record_failure(failure)
            self.task_ledger.mark_approach_failed(
                f"{action_type.name} on {target_page}: {error_message[:100]}"
            )

        if success and action.improvement_achieved():
            self.task_ledger.add_insight(
                f"Improvement via {action_type.name}: {description[:100]}"
            )

        return action

    def record_iteration_complete(self, quality_scores: Dict[str, float]) -> None:
        """Record completion of an iteration with quality scores."""
        self.progress_ledger.record_iteration_quality(quality_scores)

        for page_id, score in quality_scores.items():
            if page_id != "overall":
                self.progress_ledger.record_page_quality(page_id, score)

    def get_combined_context(self, max_items: int = 5) -> str:
        """Get combined context from both ledgers for LLM prompts."""
        return (
            "=== Task Context ===\n"
            f"{self.task_ledger.get_context_summary(max_items)}\n\n"
            "=== Progress Status ===\n"
            f"{self.progress_ledger.get_progress_summary()}"
        )

    def should_continue(self) -> bool:
        """Check if generation should continue."""
        # Stop if max iterations reached
        if self.progress_ledger.current_iteration >= self.progress_ledger.max_iterations:
            log.info("LedgerManager: Max iterations reached, stopping")
            return False

        # Stop if target quality achieved
        if self.progress_ledger.quality_target_reached():
            log.info("LedgerManager: Target quality reached, stopping")
            return False

        return True

    def should_trigger_replan(self) -> bool:
        """Check if conditions warrant a plan revision."""
        return self.progress_ledger.should_replan()

    def save_to_file(self, filepath: str) -> None:
        """Save ledger state to JSON file."""
        data = {
            "task_ledger": self.task_ledger.to_dict(),
            "progress_ledger": self.progress_ledger.to_dict(),
            "saved_at": datetime.now().isoformat()
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log.info(f"LedgerManager: Saved state to {filepath}")

    def __str__(self) -> str:
        return f"PresentationLedgerManager({self.task_ledger}, {self.progress_ledger})"
