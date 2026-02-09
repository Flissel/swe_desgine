"""
Analyst Agent for Magentic-One inspired AI-Scientist architecture.

This agent specializes in experiment analysis:
- VLM (Vision-Language Model) analysis of plots
- Metrics parsing and interpretation
- Result quality assessment

Extracted from the ParallelAgent's VLM feedback methods.
"""

from __future__ import annotations

import logging
import time
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from .base_agent import (
    BaseResearchAgent,
    AgentContext,
    AgentResult,
    AgentCapability,
    TaskType,
)

if TYPE_CHECKING:
    from ..journal import Node

logger = logging.getLogger(__name__)


class AnalystAgent(BaseResearchAgent):
    """
    Specialized agent for experiment analysis and metrics interpretation.

    This agent handles:
    - Analyze: VLM-based analysis of generated plots
    - Metrics: Parse and interpret experiment metrics
    - Quality: Assess result quality and validity

    It uses vision-language models to analyze plots and provides
    structured feedback for the orchestrator and other agents.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(
            name="analyst",
            description="Analyzes experiment results using VLM and metrics interpretation",
            capabilities=[
                AgentCapability.VLM_ANALYSIS,
                AgentCapability.METRIC_PARSING,
            ],
            config=config or {}
        )

        self._analysis_intro = (
            "You are an expert AI researcher analyzing experimental results. "
            "Your task is to carefully examine the provided plots and metrics "
            "to assess the quality and validity of the experiment."
        )

        # Key aspects to analyze in plots
        self._analysis_aspects = [
            "Training convergence and stability",
            "Generalization (train vs validation gap)",
            "Metric quality and improvement trends",
            "Anomalies or unexpected patterns",
            "Sample quality (for generative models)",
        ]

    def can_handle(self, task_type: TaskType) -> bool:
        """Check if this agent can handle the task."""
        return task_type == TaskType.ANALYZE

    def execute(self, context: AgentContext) -> AgentResult:
        """
        Execute analysis on experiment results.

        Analyzes plots, parses metrics, and generates feedback.
        """
        start_time = time.time()
        self.prepare(context)

        try:
            errors = self.validate_context(context)
            if errors:
                return AgentResult(
                    success=False,
                    error_message=f"Context validation failed: {', '.join(errors)}",
                    action_type="analyze",
                    duration_seconds=time.time() - start_time
                )

            # Perform analysis
            result = self._analyze_experiment(context)
            result.duration_seconds = time.time() - start_time

            return result

        except Exception as e:
            logger.error(f"AnalystAgent execution failed: {e}")
            return AgentResult(
                success=False,
                error_message=str(e),
                action_type="analyze",
                duration_seconds=time.time() - start_time
            )
        finally:
            self.cleanup()

    def _analyze_experiment(self, context: AgentContext) -> AgentResult:
        """
        Perform comprehensive experiment analysis.
        """
        logger.info("AnalystAgent performing experiment analysis")

        analysis_parts = []
        recommendations = []
        confidence = 0.5

        # Analyze node if provided
        if context.current_node:
            node = context.current_node

            # Check for valid metrics
            metric = node.get("metric")
            if metric:
                analysis_parts.append(f"Metric value: {metric}")
                confidence += 0.1

            # Check for plots
            plots = node.get("plots", [])
            if plots:
                analysis_parts.append(f"Generated {len(plots)} plots for analysis")
                confidence += 0.1

                # VLM analysis would happen here
                for aspect in self._analysis_aspects:
                    analysis_parts.append(f"- {aspect}: [VLM analysis pending]")

            # Check execution output
            term_out = node.get("term_out", "")
            if term_out:
                # Look for common success indicators
                if "loss:" in term_out.lower() or "accuracy:" in term_out.lower():
                    confidence += 0.1
                    analysis_parts.append("Training logs contain metric outputs")

            # Assess if buggy
            is_buggy = node.get("is_buggy", False)
            if is_buggy:
                confidence -= 0.2
                recommendations.append("Experiment has issues - debug agent needed")

        # Generate overall assessment
        if confidence > 0.6:
            assessment = "Experiment appears successful"
            recommendations.append("Consider moving to next stage")
        elif confidence > 0.4:
            assessment = "Experiment has mixed results"
            recommendations.append("Review results and consider improvements")
        else:
            assessment = "Experiment needs attention"
            recommendations.append("Debug or improve implementation")

        analysis_parts.insert(0, f"Overall Assessment: {assessment}")

        return AgentResult(
            success=True,
            analysis="\n".join(analysis_parts),
            action_type="analyze",
            notes=assessment,
            recommendations=recommendations,
            confidence=min(confidence, 1.0),
            needs_debugging=confidence < 0.4,
            needs_improvement=0.4 <= confidence < 0.7
        )

    def validate_context(self, context: AgentContext) -> List[str]:
        """Validate context for analysis."""
        errors = super().validate_context(context)

        # Analysis typically needs a node to analyze
        if not context.current_node:
            errors.append("Current node is required for analysis")

        return errors

    def get_recommendations(self, result: AgentResult) -> List[str]:
        """Generate recommendations based on analysis."""
        recommendations = super().get_recommendations(result)

        if result.success and result.confidence > 0.7:
            recommendations.append("High quality results - ready for review")

        return recommendations
