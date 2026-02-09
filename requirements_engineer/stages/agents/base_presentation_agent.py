"""
Base Presentation Agent for Multi-Agent HTML Generation.

This module defines the abstract base class for all Presentation Stage agents,
following the Magentic-One pattern with specialized roles and capabilities.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from pathlib import Path

from dataclasses_json import DataClassJsonMixin

if TYPE_CHECKING:
    from ..orchestrator.presentation_ledger import PresentationTaskLedger, PresentationProgressLedger

logger = logging.getLogger(__name__)


class AgentRole(Enum):
    """Roles for presentation agents."""
    CONTENT_ANALYZER = auto()    # Analyzes artifacts from Stages 1-4
    HTML_GENERATOR = auto()      # Generates HTML pages
    HTML_REVIEWER = auto()       # Evaluates quality
    HTML_IMPROVER = auto()       # Applies improvements
    KILO_INTEGRATION = auto()    # Interfaces with Kilo CLI
    ORCHESTRATOR = auto()        # Coordinates all agents
    PROJECT_SCAFFOLD = auto()    # Generates project directory structure
    SCAFFOLD_REVIEWER = auto()   # Reviews scaffold quality
    SCAFFOLD_IMPROVER = auto()   # Improves scaffold structure
    SCREEN_GENERATOR = auto()    # Generates screen designs with wireframes
    SCREEN_REVIEWER = auto()     # Reviews screen quality
    SCREEN_IMPROVER = auto()     # Improves screen designs


class AgentCapability(Enum):
    """Capabilities for presentation agents."""
    ARTIFACT_PARSING = auto()     # Parse requirements, stories, diagrams
    HTML_GENERATION = auto()      # Generate HTML content
    CSS_STYLING = auto()          # Apply CSS styles
    QUALITY_EVALUATION = auto()   # Evaluate HTML quality
    CONTENT_ENHANCEMENT = auto()  # Enhance/rewrite content
    STRUCTURE_FIXING = auto()     # Fix HTML structure issues
    DIAGRAM_GENERATION = auto()   # Generate Mermaid diagrams
    CODE_EXECUTION = auto()       # Execute code via Kilo
    SCAFFOLD_GENERATION = auto()  # Generate directory structures
    FILE_PLACEMENT = auto()       # Place/copy files into scaffold
    SCREEN_GENERATION = auto()    # Generate screen designs
    SCREEN_REVIEW = auto()        # Review screen quality


class ImprovementType(Enum):
    """Types of improvements that can be applied."""
    ADD_SECTION = "add_section"
    ENHANCE_CONTENT = "enhance_content"
    FIX_STRUCTURE = "fix_structure"
    ADD_STYLING = "add_styling"
    GENERATE_DIAGRAM = "generate_diagram"
    MERGE_CONTENT = "merge_content"
    ADD_NAVIGATION = "add_navigation"
    FIX_ACCESSIBILITY = "fix_accessibility"


@dataclass
class PresentationContext(DataClassJsonMixin):
    """
    Context provided to a presentation agent for task execution.

    Contains all necessary information from the ledger system, artifacts,
    and configuration for the agent to perform its task.
    """

    # Ledger context (Magentic-One pattern)
    task_ledger_summary: str = ""
    progress_ledger_summary: str = ""

    # Artifact information
    artifact_stats: Dict[str, int] = field(default_factory=dict)
    artifact_paths: Dict[str, Path] = field(default_factory=dict)

    # Current HTML state
    current_pages: List[str] = field(default_factory=list)
    current_quality_score: float = 0.0
    quality_issues: List[Dict[str, Any]] = field(default_factory=list)

    # Task description
    task_description: str = ""
    target_page: Optional[str] = None  # Specific page to work on

    # Configuration
    config: Dict[str, Any] = field(default_factory=dict)

    # Project info
    project_id: str = ""
    output_dir: str = ""

    # Previous agent feedback
    previous_agent_feedback: List[str] = field(default_factory=list)

    # Quality targets
    quality_threshold: float = 0.8

    def get_llm_context(self) -> str:
        """Generate context string suitable for LLM prompts."""
        parts = []

        if self.task_description:
            parts.append(f"## Task\n{self.task_description}")

        if self.project_id:
            parts.append(f"## Project\n{self.project_id}")

        if self.artifact_stats:
            stats_str = ", ".join(f"{k}: {v}" for k, v in self.artifact_stats.items())
            parts.append(f"## Artifacts\n{stats_str}")

        if self.task_ledger_summary:
            parts.append(f"## Knowledge Context\n{self.task_ledger_summary}")

        if self.progress_ledger_summary:
            parts.append(f"## Progress\n{self.progress_ledger_summary}")

        if self.quality_issues:
            issues_str = "\n".join(
                f"- [{i['severity']}] {i['description']}"
                for i in self.quality_issues[:10]
            )
            parts.append(f"## Quality Issues\n{issues_str}")

        if self.previous_agent_feedback:
            feedback_str = "\n".join(f"- {f}" for f in self.previous_agent_feedback[-5:])
            parts.append(f"## Previous Feedback\n{feedback_str}")

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
    generated_files: List[str] = field(default_factory=list)
    modified_files: List[str] = field(default_factory=list)
    generated_content: Optional[str] = None

    # Quality metrics
    quality_score: float = 0.0
    quality_issues: List[Dict[str, Any]] = field(default_factory=list)

    # Improvement items
    improvements_applied: List[Dict[str, Any]] = field(default_factory=list)
    improvements_pending: List[Dict[str, Any]] = field(default_factory=list)

    # Action record for ledger
    action_type: str = ""
    duration_seconds: float = 0.0
    notes: str = ""

    # Recommendations for orchestrator
    recommendations: List[str] = field(default_factory=list)
    suggested_next_agent: Optional[str] = None
    confidence: float = 0.5  # 0-1, agent's confidence in result

    # Flags for orchestrator decisions
    needs_improvement: bool = False
    needs_review: bool = False
    stage_complete: bool = False
    should_replan: bool = False


@dataclass
class ImprovementItem(DataClassJsonMixin):
    """A single improvement to be applied to HTML content."""

    type: ImprovementType = ImprovementType.ENHANCE_CONTENT
    severity: str = "minor"  # critical, major, minor
    target_file: str = ""
    target_selector: str = ""  # CSS selector or section ID
    description: str = ""
    suggested_fix: str = ""
    position: str = ""  # before, after, replace
    content: str = ""  # New content to add/replace


@dataclass
class QualityEvaluation(DataClassJsonMixin):
    """Structured quality evaluation result."""

    overall_score: float = 0.0
    criteria_scores: Dict[str, float] = field(default_factory=dict)
    # structure, readability, completeness, navigation, accessibility, styling

    issues: List[ImprovementItem] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    passed: bool = False
    threshold: float = 0.8


class BasePresentationAgent(ABC):
    """
    Abstract base class for Presentation Stage agents.

    Each specialized agent inherits from this class and implements
    the abstract methods for its specific role in HTML generation.

    Attributes:
        name: Unique identifier for the agent
        role: The agent's role in the presentation pipeline
        description: Human-readable description of agent's purpose
        capabilities: Set of capabilities this agent provides
    """

    def __init__(
        self,
        name: str,
        role: AgentRole,
        description: str,
        capabilities: List[AgentCapability],
        config: Optional[Dict[str, Any]] = None
    ):
        self.name = name
        self.role = role
        self.description = description
        self.capabilities = set(capabilities)
        self.config = config or {}

        # LLM configuration - reads from merged config (agent-specific overrides defaults)
        self.model = self.config.get("model", "anthropic/claude-3.5-sonnet")
        self.temperature = self.config.get("temperature", 0.5)
        self.max_tokens = self.config.get("max_tokens", 8000)

        # Internal state
        self._is_running = False
        self._current_context: Optional[PresentationContext] = None

        logger.info(f"Initialized presentation agent: {self.name} ({self.role.name})")

    @property
    def is_running(self) -> bool:
        """Check if agent is currently executing a task."""
        return self._is_running

    def has_capability(self, capability: AgentCapability) -> bool:
        """Check if agent has a specific capability."""
        return capability in self.capabilities

    @abstractmethod
    async def execute(self, context: PresentationContext) -> AgentResult:
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

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Call the LLM with the given prompts.

        Uses the configured model via OpenRouter/Claude.

        Args:
            system_prompt: System message for the LLM
            user_prompt: User message with the actual request
            json_schema: Optional JSON schema for structured output

        Returns:
            LLM response string
        """
        # Import LLM logger
        try:
            from requirements_engineer.core.llm_logger import log_llm_call
        except ImportError:
            log_llm_call = None

        start_time = time.time()
        success = True
        error_msg = None

        try:
            # Import the backend query function
            from ai_scientist.treesearch.backend import query

            response = query(
                system_message=system_prompt,
                user_message=user_prompt,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                func_spec=json_schema
            )

            return response

        except Exception as e:
            success = False
            error_msg = str(e)
            logger.error(f"LLM call failed: {e}")
            raise

        finally:
            latency_ms = int((time.time() - start_time) * 1000)
            if log_llm_call:
                log_llm_call(
                    component=f"presentation_agent_{self.name}",
                    model=self.model,
                    latency_ms=latency_ms,
                    success=success,
                    error=error_msg
                )

    def _log_progress(self, message: str) -> None:
        """Log progress message."""
        logger.info(f"[{self.name}] {message}")

    def _log_error(self, message: str) -> None:
        """Log error message."""
        logger.error(f"[{self.name}] {message}")

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name}, role={self.role.name})"
