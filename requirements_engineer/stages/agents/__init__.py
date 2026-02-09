"""
Presentation Stage Agents for Multi-Agent HTML Generation.

This package contains specialized agents for the Presentation Stage (Stage 5)
following the Magentic-One pattern with an Orchestrator + specialized agents.

Agents:
- BasePresentationAgent: Base class for all presentation agents
- ContentAnalyzerAgent: Analyzes artifacts from Stages 1-4
- HTMLGeneratorAgent: Generates HTML pages
- HTMLReviewerAgent: Evaluates quality and provides structured feedback
- HTMLImproverAgent: Applies improvements to HTML content
- KiloIntegrationAgent: Interfaces with Kilo CLI for complex generation
"""

from .base_presentation_agent import (
    BasePresentationAgent,
    AgentRole,
    AgentCapability,
    PresentationContext,
    AgentResult,
    ImprovementItem,
    ImprovementType,
    QualityEvaluation,
)
from .content_analyzer_agent import ContentAnalyzerAgent, ContentAnalysis
from .html_generator_agent import HTMLGeneratorAgent, HTMLPage
from .html_reviewer_agent import HTMLReviewerAgent, PageReview
from .html_improver_agent import HTMLImproverAgent, AppliedImprovement
from .kilo_integration_agent import KiloIntegrationAgent, KiloTaskResult
from .project_scaffold_agent import ProjectScaffoldAgent
from .scaffold_reviewer_agent import ScaffoldReviewerAgent
from .scaffold_improver_agent import ScaffoldImproverAgent
from .screen_generator_agent import ScreenGeneratorAgent
from .screen_reviewer_agent import ScreenReviewerAgent
from .screen_improver_agent import ScreenImproverAgent

__all__ = [
    # Base classes and types
    "BasePresentationAgent",
    "AgentRole",
    "AgentCapability",
    "PresentationContext",
    "AgentResult",
    "ImprovementItem",
    "ImprovementType",
    "QualityEvaluation",
    # HTML Agents
    "ContentAnalyzerAgent",
    "ContentAnalysis",
    "HTMLGeneratorAgent",
    "HTMLPage",
    "HTMLReviewerAgent",
    "PageReview",
    "HTMLImproverAgent",
    "AppliedImprovement",
    "KiloIntegrationAgent",
    "KiloTaskResult",
    # Scaffold Agents
    "ProjectScaffoldAgent",
    "ScaffoldReviewerAgent",
    "ScaffoldImproverAgent",
    # Screen Design Agents
    "ScreenGeneratorAgent",
    "ScreenReviewerAgent",
    "ScreenImproverAgent",
]
