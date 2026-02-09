"""
Base Research Agent for Magentic-One inspired AI-Scientist architecture.

This module defines the abstract base class that all specialized research
agents inherit from, along with supporting data structures for agent
communication and context management.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Dict, Any, TYPE_CHECKING

from dataclasses_json import DataClassJsonMixin

if TYPE_CHECKING:
    from ..journal import Node, Journal
    from ..ledger import TaskLedger, ProgressLedger, ActionRecord
    from ..utils.metric import MetricValue

logger = logging.getLogger(__name__)


class AgentCapability(Enum):
    """Capabilities that agents can have."""
    CODE_GENERATION = auto()
    CODE_DEBUGGING = auto()
    CODE_IMPROVEMENT = auto()
    HYPERPARAMETER_TUNING = auto()
    ABLATION_ANALYSIS = auto()
    VLM_ANALYSIS = auto()
    METRIC_PARSING = auto()
    STAGE_REVIEW = auto()
    PLOT_GENERATION = auto()


class TaskType(Enum):
    """Types of tasks agents can handle."""
    DRAFT = "draft"
    DEBUG = "debug"
    IMPROVE = "improve"
    TUNE = "tune"
    ABLATE = "ablate"
    ANALYZE = "analyze"
    REVIEW = "review"
    PLOT = "plot"


@dataclass
class AgentContext(DataClassJsonMixin):
    """
    Context provided to an agent for task execution.

    Contains all necessary information from the ledger system, current state,
    and configuration for the agent to perform its task.
    """

    # Ledger context (Magentic-One pattern)
    task_ledger_summary: str = ""
    progress_ledger_summary: str = ""

    # Current experiment state
    current_node: Optional[Dict[str, Any]] = None  # Serialized Node
    parent_node: Optional[Dict[str, Any]] = None   # Serialized parent Node
    journal_summary: str = ""

    # Stage information
    stage_name: str = ""
    stage_goals: str = ""
    stage_number: int = 0

    # Task description
    task_description: str = ""
    experiment_type: str = ""

    # Configuration
    config: Dict[str, Any] = field(default_factory=dict)

    # Additional context from previous agents
    previous_agent_feedback: List[str] = field(default_factory=list)

    # Best results so far
    best_node_id: Optional[str] = None
    best_metric: Optional[Dict[str, Any]] = None

    def get_llm_context(self) -> str:
        """Generate context string suitable for LLM prompts."""
        parts = []

        if self.task_description:
            parts.append(f"## Task\n{self.task_description}")

        if self.stage_name:
            parts.append(f"## Current Stage\n{self.stage_name} (Stage {self.stage_number})")
            if self.stage_goals:
                parts.append(f"Goals: {self.stage_goals}")

        if self.task_ledger_summary:
            parts.append(f"## Knowledge Context\n{self.task_ledger_summary}")

        if self.progress_ledger_summary:
            parts.append(f"## Progress\n{self.progress_ledger_summary}")

        if self.journal_summary:
            parts.append(f"## Experiment History\n{self.journal_summary}")

        if self.previous_agent_feedback:
            parts.append("## Feedback from Previous Steps")
            for feedback in self.previous_agent_feedback[-3:]:
                parts.append(f"- {feedback}")

        return "\n\n".join(parts)


@dataclass
class AgentResult(DataClassJsonMixin):
    """
    Result returned by an agent after task execution.

    Contains the outcome, any generated artifacts, and recommendations
    for the orchestrator and subsequent agents.
    """

    # Execution status
    success: bool = False
    error_message: str = ""

    # Generated artifacts
    node_id: Optional[str] = None
    code: Optional[str] = None
    plan: Optional[str] = None
    analysis: Optional[str] = None

    # Metrics
    metrics: Optional[Dict[str, Any]] = None

    # Action record for ledger
    action_type: str = ""
    duration_seconds: float = 0.0
    notes: str = ""

    # Recommendations for orchestrator
    recommendations: List[str] = field(default_factory=list)
    suggested_next_agent: Optional[str] = None
    confidence: float = 0.5  # 0-1, agent's confidence in result

    # Flags for orchestrator decisions
    needs_debugging: bool = False
    needs_improvement: bool = False
    stage_complete: bool = False


@dataclass
class ProgressUpdate(DataClassJsonMixin):
    """
    Progress update from an agent for the Progress Ledger.

    Agents emit these during long-running tasks to keep the
    orchestrator informed of their status.
    """

    agent_name: str = ""
    status: str = ""  # running, waiting, completed, failed
    progress_percent: float = 0.0
    current_step: str = ""
    estimated_remaining_steps: int = 0
    notes: str = ""


class BaseResearchAgent(ABC):
    """
    Abstract base class for Magentic-One inspired research agents.

    Each specialized agent inherits from this class and implements
    the abstract methods for its specific domain.

    Attributes:
        name: Unique identifier for the agent
        description: Human-readable description of agent's purpose
        capabilities: Set of capabilities this agent provides
    """

    def __init__(
        self,
        name: str,
        description: str,
        capabilities: List[AgentCapability],
        config: Optional[Dict[str, Any]] = None
    ):
        self.name = name
        self.description = description
        self.capabilities = set(capabilities)
        self.config = config or {}

        # Internal state
        self._is_running = False
        self._current_context: Optional[AgentContext] = None

        logger.info(f"Initialized agent: {self.name} with capabilities {self.capabilities}")

    @property
    def is_running(self) -> bool:
        """Check if agent is currently executing a task."""
        return self._is_running

    def can_handle(self, task_type: TaskType) -> bool:
        """
        Determine if this agent can handle the given task type.

        Override in subclasses for more sophisticated capability matching.

        Args:
            task_type: The type of task to check

        Returns:
            True if agent can handle this task type
        """
        capability_map = {
            TaskType.DRAFT: AgentCapability.CODE_GENERATION,
            TaskType.DEBUG: AgentCapability.CODE_DEBUGGING,
            TaskType.IMPROVE: AgentCapability.CODE_IMPROVEMENT,
            TaskType.TUNE: AgentCapability.HYPERPARAMETER_TUNING,
            TaskType.ABLATE: AgentCapability.ABLATION_ANALYSIS,
            TaskType.ANALYZE: AgentCapability.VLM_ANALYSIS,
            TaskType.REVIEW: AgentCapability.STAGE_REVIEW,
            TaskType.PLOT: AgentCapability.PLOT_GENERATION,
        }

        required_capability = capability_map.get(task_type)
        return required_capability in self.capabilities if required_capability else False

    @abstractmethod
    def execute(self, context: AgentContext) -> AgentResult:
        """
        Execute the agent's primary task.

        This is the main entry point for agent execution. Subclasses
        must implement this method with their specific logic.

        Args:
            context: The context containing all necessary information

        Returns:
            AgentResult with execution outcome and artifacts
        """
        pass

    def prepare(self, context: AgentContext) -> None:
        """
        Prepare the agent for execution.

        Called before execute() to allow agents to set up any
        necessary state or validate the context.

        Args:
            context: The context that will be used for execution
        """
        self._current_context = context
        self._is_running = True
        logger.debug(f"Agent {self.name} prepared for execution")

    def cleanup(self) -> None:
        """
        Clean up after execution.

        Called after execute() completes (success or failure) to
        release resources and reset state.
        """
        self._is_running = False
        self._current_context = None
        logger.debug(f"Agent {self.name} cleaned up")

    def report_progress(self) -> ProgressUpdate:
        """
        Report current progress for long-running tasks.

        Override in subclasses that perform lengthy operations
        to provide progress updates to the orchestrator.

        Returns:
            ProgressUpdate with current status
        """
        return ProgressUpdate(
            agent_name=self.name,
            status="running" if self._is_running else "idle",
            progress_percent=0.0,
            current_step="unknown",
            notes=""
        )

    def validate_context(self, context: AgentContext) -> List[str]:
        """
        Validate the provided context.

        Returns a list of validation errors. Empty list means valid.

        Args:
            context: The context to validate

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        if not context.task_description:
            errors.append("Missing task description")

        if not context.stage_name:
            errors.append("Missing stage name")

        return errors

    def get_recommendations(self, result: AgentResult) -> List[str]:
        """
        Generate recommendations based on the execution result.

        Override in subclasses for agent-specific recommendations.

        Args:
            result: The result from execute()

        Returns:
            List of recommendation strings
        """
        recommendations = []

        if result.needs_debugging:
            recommendations.append("Run debugger agent to fix issues")

        if result.needs_improvement and not result.needs_debugging:
            recommendations.append("Run improvement agent to enhance results")

        if result.success and result.confidence > 0.8:
            recommendations.append("High confidence result - consider moving to next stage")

        return recommendations

    def __str__(self) -> str:
        caps = ", ".join(c.name for c in self.capabilities)
        return f"{self.name}[{caps}]"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name}, running={self._is_running})>"
