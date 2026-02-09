"""
Presentation Orchestrator for Multi-Agent HTML Generation.

This package contains the orchestrator and ledger system for the
Presentation Stage (Stage 5) following the Magentic-One pattern.

Components:
- PresentationOrchestrator: Coordinates all agents using Two-Loop pattern
- PresentationTaskLedger: Tracks what we know about the task
- PresentationProgressLedger: Tracks progress and stagnation
- ImprovementTypes: Types of improvements that can be applied
"""

from .presentation_ledger import (
    PresentationTaskLedger,
    PresentationProgressLedger,
    PresentationLedgerManager,
    PresentationActionRecord,
    ActionType,
    FailedAttempt,
)

from .improvement_types import (
    ImprovementType,
    ImprovementPriority,
    ImprovementPlan,
    ImprovementItem,
    ImprovementResult,
    create_improvement_from_issue,
    create_improvement_plan,
)

from .presentation_orchestrator import (
    PresentationOrchestrator,
    OrchestratorState,
    OrchestratorConfig,
    IterationResult,
    run_presentation_orchestrator,
)

from .scaffold_orchestrator import ScaffoldOrchestrator
from .screen_design_orchestrator import ScreenDesignOrchestrator

__all__ = [
    # Ledger System
    "PresentationTaskLedger",
    "PresentationProgressLedger",
    "PresentationLedgerManager",
    "PresentationActionRecord",
    "ActionType",
    "FailedAttempt",
    # Improvement Types
    "ImprovementType",
    "ImprovementPriority",
    "ImprovementPlan",
    "ImprovementItem",
    "ImprovementResult",
    "create_improvement_from_issue",
    "create_improvement_plan",
    # Orchestrator
    "PresentationOrchestrator",
    "OrchestratorState",
    "OrchestratorConfig",
    "IterationResult",
    "run_presentation_orchestrator",
    # Scaffold Orchestrator
    "ScaffoldOrchestrator",
    # Screen Design Orchestrator
    "ScreenDesignOrchestrator",
]
