"""
Magentic-One inspired Ledger System for AI-Scientist.

This module implements Task Ledger and Progress Ledger for self-reflection
and adaptive planning during research experiments.

Task Ledger: Central knowledge repository - What do we know?
Progress Ledger: Progress tracking - How far have we come?
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, TYPE_CHECKING

from dataclasses_json import DataClassJsonMixin

if TYPE_CHECKING:
    from .utils.metric import MetricValue

logger = logging.getLogger(__name__)


@dataclass
class FailedAttempt(DataClassJsonMixin):
    """Records a failed experiment attempt."""

    timestamp: float = field(default_factory=time.time)
    node_id: str = ""
    action_type: str = ""  # draft, debug, improve, tune, ablate
    error_type: Optional[str] = None  # Exception type if applicable
    error_message: str = ""
    attempted_fix: Optional[str] = None

    def __str__(self) -> str:
        return f"FailedAttempt({self.action_type}@{self.node_id[:8]}): {self.error_message[:50]}"


@dataclass
class ActionRecord(DataClassJsonMixin):
    """Records a single action in the Progress Ledger."""

    timestamp: float = field(default_factory=time.time)
    agent_name: str = ""  # coder, debugger, analyst, tuner, ablation, reviewer
    action_type: str = ""  # draft, debug, improve, tune, ablate, review
    node_id: str = ""
    success: bool = False
    metrics_before: Optional[Dict[str, Any]] = None  # Serialized MetricValue
    metrics_after: Optional[Dict[str, Any]] = None   # Serialized MetricValue
    notes: str = ""
    duration_seconds: float = 0.0

    def improvement_achieved(self) -> bool:
        """Check if this action resulted in metric improvement."""
        if not self.success or self.metrics_before is None or self.metrics_after is None:
            return False
        # Basic check - actual comparison should use MetricValue logic
        before_val = self.metrics_before.get("value")
        after_val = self.metrics_after.get("value")
        if before_val is None or after_val is None:
            return False
        maximize = self.metrics_after.get("maximize", True)
        if maximize:
            return after_val > before_val
        else:
            return after_val < before_val

    def __str__(self) -> str:
        status = "OK" if self.success else "FAIL"
        return f"Action({self.agent_name}/{self.action_type})[{status}]: {self.notes[:30]}"


@dataclass
class TaskLedger(DataClassJsonMixin):
    """
    Central knowledge repository - What do we know?

    Inspired by Magentic-One's Task Ledger, this tracks facts, hypotheses,
    constraints, and open questions discovered during research.
    """

    # Core knowledge
    facts: List[str] = field(default_factory=list)
    hypotheses: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)

    # Resource tracking
    resources: Dict[str, str] = field(default_factory=dict)  # name -> description

    # Research context
    research_goal: str = ""
    experiment_type: str = ""  # e.g., "classification", "generation", "optimization"

    # Insights from experiments
    insights: List[str] = field(default_factory=list)
    failed_approaches: List[str] = field(default_factory=list)

    def add_fact(self, fact: str) -> None:
        """Add a confirmed fact."""
        if fact not in self.facts:
            self.facts.append(fact)
            logger.debug(f"TaskLedger: Added fact - {fact[:50]}")

    def add_hypothesis(self, hypothesis: str) -> None:
        """Add a hypothesis to test."""
        if hypothesis not in self.hypotheses:
            self.hypotheses.append(hypothesis)
            logger.debug(f"TaskLedger: Added hypothesis - {hypothesis[:50]}")

    def confirm_hypothesis(self, hypothesis: str, as_fact: bool = True) -> None:
        """Mark a hypothesis as confirmed (optionally convert to fact)."""
        if hypothesis in self.hypotheses:
            self.hypotheses.remove(hypothesis)
            if as_fact:
                self.add_fact(f"[Confirmed] {hypothesis}")

    def reject_hypothesis(self, hypothesis: str, reason: str = "") -> None:
        """Mark a hypothesis as rejected."""
        if hypothesis in self.hypotheses:
            self.hypotheses.remove(hypothesis)
            rejection = f"[Rejected] {hypothesis}"
            if reason:
                rejection += f" - Reason: {reason}"
            self.failed_approaches.append(rejection)

    def add_constraint(self, constraint: str) -> None:
        """Add a known constraint."""
        if constraint not in self.constraints:
            self.constraints.append(constraint)

    def add_question(self, question: str) -> None:
        """Add an open question."""
        if question not in self.open_questions:
            self.open_questions.append(question)

    def answer_question(self, question: str, answer: str) -> None:
        """Answer an open question (converts to fact)."""
        if question in self.open_questions:
            self.open_questions.remove(question)
            self.add_fact(f"Q: {question} A: {answer}")

    def add_insight(self, insight: str) -> None:
        """Add an experimental insight."""
        if insight not in self.insights:
            self.insights.append(insight)

    def add_resource(self, name: str, description: str) -> None:
        """Register an available resource."""
        self.resources[name] = description

    def get_context_summary(self, max_items: int = 5) -> str:
        """Generate a summary for LLM context."""
        lines = []

        if self.research_goal:
            lines.append(f"Research Goal: {self.research_goal}")

        if self.facts:
            lines.append(f"Key Facts ({len(self.facts)}):")
            for fact in self.facts[-max_items:]:
                lines.append(f"  - {fact}")

        if self.hypotheses:
            lines.append(f"Active Hypotheses ({len(self.hypotheses)}):")
            for hyp in self.hypotheses[-max_items:]:
                lines.append(f"  - {hyp}")

        if self.constraints:
            lines.append(f"Constraints ({len(self.constraints)}):")
            for const in self.constraints[-max_items:]:
                lines.append(f"  - {const}")

        if self.insights:
            lines.append(f"Recent Insights ({len(self.insights)}):")
            for insight in self.insights[-max_items:]:
                lines.append(f"  - {insight}")

        return "\n".join(lines)

    def __str__(self) -> str:
        return (
            f"TaskLedger(facts={len(self.facts)}, hypotheses={len(self.hypotheses)}, "
            f"constraints={len(self.constraints)}, questions={len(self.open_questions)})"
        )


@dataclass
class ProgressLedger(DataClassJsonMixin):
    """
    Progress tracking - How far have we come?

    Inspired by Magentic-One's Progress Ledger, this tracks completed actions,
    failed attempts, and detects stagnation for adaptive replanning.
    """

    # Action tracking
    completed_actions: List[ActionRecord] = field(default_factory=list)
    failed_attempts: List[FailedAttempt] = field(default_factory=list)

    # Progress metrics
    current_best_node_id: Optional[str] = None
    current_best_metric: Optional[Dict[str, Any]] = None  # Serialized MetricValue

    # Stagnation detection
    stagnation_counter: int = 0
    last_improvement_step: int = 0
    total_steps: int = 0

    # Configuration
    stagnation_threshold: int = 3  # Steps without improvement before stagnation
    max_failed_attempts: int = 5  # Max consecutive failures before alert

    # Replan tracking
    replan_count: int = 0
    max_replans: int = 5

    def record_action(self, action: ActionRecord) -> None:
        """Record a completed action."""
        self.completed_actions.append(action)
        self.total_steps += 1

        if action.success and action.improvement_achieved():
            self.last_improvement_step = self.total_steps
            self.stagnation_counter = 0
            logger.info(f"ProgressLedger: Improvement achieved at step {self.total_steps}")
        elif action.success:
            self.stagnation_counter += 1

        logger.debug(f"ProgressLedger: Recorded action - {action}")

    def record_failure(self, failure: FailedAttempt) -> None:
        """Record a failed attempt."""
        self.failed_attempts.append(failure)
        self.stagnation_counter += 1
        logger.warning(f"ProgressLedger: Recorded failure - {failure}")

    def update_best(self, node_id: str, metric: Optional[Dict[str, Any]]) -> None:
        """Update the current best node and metric."""
        self.current_best_node_id = node_id
        self.current_best_metric = metric
        self.last_improvement_step = self.total_steps
        self.stagnation_counter = 0

    def detect_stagnation(self, threshold: Optional[int] = None) -> bool:
        """
        Detect if progress has stagnated.

        Returns True if no improvement in `threshold` steps.
        """
        thresh = threshold or self.stagnation_threshold
        return self.stagnation_counter >= thresh

    def should_replan(self) -> bool:
        """
        Determine if a plan revision is recommended.

        Triggers replan on stagnation, but respects max replan limit.
        """
        if self.replan_count >= self.max_replans:
            logger.warning("ProgressLedger: Max replans reached, not recommending replan")
            return False

        if self.detect_stagnation():
            logger.info(f"ProgressLedger: Stagnation detected, recommending replan")
            return True

        # Check for excessive consecutive failures
        recent_failures = self.failed_attempts[-self.max_failed_attempts:]
        if len(recent_failures) >= self.max_failed_attempts:
            logger.info("ProgressLedger: Excessive failures, recommending replan")
            return True

        return False

    def mark_replan(self) -> None:
        """Mark that a replan has occurred."""
        self.replan_count += 1
        self.stagnation_counter = 0
        logger.info(f"ProgressLedger: Replan #{self.replan_count} marked")

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

    def get_recent_actions(self, n: int = 5) -> List[ActionRecord]:
        """Get the n most recent actions."""
        return self.completed_actions[-n:]

    def get_progress_summary(self) -> str:
        """Generate a progress summary for logging/LLM context."""
        lines = [
            f"Total Steps: {self.total_steps}",
            f"Success Rate: {self.get_success_rate():.1%}",
            f"Improvement Rate: {self.get_improvement_rate():.1%}",
            f"Stagnation Counter: {self.stagnation_counter}/{self.stagnation_threshold}",
            f"Replans: {self.replan_count}/{self.max_replans}",
        ]

        if self.current_best_node_id:
            lines.append(f"Best Node: {self.current_best_node_id[:8]}...")

        if self.current_best_metric:
            metric_val = self.current_best_metric.get("value", "N/A")
            lines.append(f"Best Metric: {metric_val}")

        recent = self.get_recent_actions(3)
        if recent:
            lines.append("Recent Actions:")
            for action in recent:
                status = "OK" if action.success else "FAIL"
                lines.append(f"  [{status}] {action.agent_name}/{action.action_type}")

        return "\n".join(lines)

    def __str__(self) -> str:
        return (
            f"ProgressLedger(steps={self.total_steps}, "
            f"success_rate={self.get_success_rate():.1%}, "
            f"stagnation={self.stagnation_counter})"
        )


@dataclass
class LedgerManager:
    """
    Manages both Task and Progress Ledgers together.

    Provides a unified interface for the orchestrator to interact with
    the Magentic-One inspired ledger system.
    """

    task_ledger: TaskLedger = field(default_factory=TaskLedger)
    progress_ledger: ProgressLedger = field(default_factory=ProgressLedger)

    def initialize_from_task(self, task_desc: Dict[str, Any]) -> None:
        """Initialize ledgers from a task description."""
        self.task_ledger.research_goal = task_desc.get("Title", "")

        if "Abstract" in task_desc:
            self.task_ledger.add_fact(f"Abstract: {task_desc['Abstract']}")

        if "Short Hypothesis" in task_desc:
            self.task_ledger.add_hypothesis(task_desc["Short Hypothesis"])

        if "Experiments" in task_desc:
            self.task_ledger.add_fact(f"Planned experiments: {task_desc['Experiments']}")

        if "Risk Factors and Limitations" in task_desc:
            for risk in str(task_desc["Risk Factors and Limitations"]).split(","):
                self.task_ledger.add_constraint(risk.strip())

    def record_experiment_result(
        self,
        agent_name: str,
        action_type: str,
        node_id: str,
        success: bool,
        notes: str = "",
        metrics_before: Optional[Dict[str, Any]] = None,
        metrics_after: Optional[Dict[str, Any]] = None,
        duration: float = 0.0,
        error_info: Optional[Dict[str, str]] = None
    ) -> ActionRecord:
        """
        Record an experiment result in both ledgers.

        Returns the ActionRecord for further use.
        """
        action = ActionRecord(
            agent_name=agent_name,
            action_type=action_type,
            node_id=node_id,
            success=success,
            metrics_before=metrics_before,
            metrics_after=metrics_after,
            notes=notes,
            duration_seconds=duration
        )

        self.progress_ledger.record_action(action)

        if not success and error_info:
            failure = FailedAttempt(
                node_id=node_id,
                action_type=action_type,
                error_type=error_info.get("type"),
                error_message=error_info.get("message", ""),
                attempted_fix=error_info.get("fix")
            )
            self.progress_ledger.record_failure(failure)
            self.task_ledger.failed_approaches.append(
                f"{action_type} failed: {error_info.get('message', '')[:100]}"
            )

        if success and action.improvement_achieved():
            self.task_ledger.add_insight(
                f"Improvement via {action_type}: {notes[:100]}"
            )

        return action

    def get_combined_context(self, max_items: int = 5) -> str:
        """Get combined context from both ledgers for LLM prompts."""
        return (
            "=== Task Context ===\n"
            f"{self.task_ledger.get_context_summary(max_items)}\n\n"
            "=== Progress Status ===\n"
            f"{self.progress_ledger.get_progress_summary()}"
        )

    def should_trigger_replan(self) -> bool:
        """Check if conditions warrant a plan revision."""
        return self.progress_ledger.should_replan()

    def __str__(self) -> str:
        return f"LedgerManager({self.task_ledger}, {self.progress_ledger})"
