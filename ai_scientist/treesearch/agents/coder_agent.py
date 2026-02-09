"""
Coder Agent for Magentic-One inspired AI-Scientist architecture.

This agent specializes in code generation, including:
- Initial draft implementation
- Code improvement based on feedback
- Code modification for experiments

Extracted from the ParallelAgent's _draft and _improve methods.
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
    from ..backend import FunctionSpec

logger = logging.getLogger(__name__)


class CoderAgent(BaseResearchAgent):
    """
    Specialized agent for code generation and improvement.

    This agent handles:
    - Draft: Initial implementation of research ideas
    - Improve: Enhancement of existing implementations

    It uses the LLM to generate plans and code based on the research
    context and feedback from previous experiments.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(
            name="coder",
            description="Generates and improves experiment code based on research ideas",
            capabilities=[
                AgentCapability.CODE_GENERATION,
                AgentCapability.CODE_IMPROVEMENT,
            ],
            config=config or {}
        )

        # Prompt templates (can be customized via config)
        self._draft_intro = (
            "You are an AI researcher who is looking to publish a paper that will "
            "contribute significantly to the field. Your first task is to write a "
            "python code to implement a solid baseline based on your research idea "
            "provided below, from data preparation to model training, as well as "
            "evaluation and visualization. Focus on getting a simple but working "
            "implementation first, before any sophisticated improvements. "
            "We will explore more advanced variations in later stages."
        )

        self._improve_intro = (
            "You are an experienced AI researcher. You are provided with a previously "
            "developed implementation. Your task is to improve it based on the current "
            "experimental stage."
        )

    def can_handle(self, task_type: TaskType) -> bool:
        """Check if this agent can handle the task."""
        return task_type in [TaskType.DRAFT, TaskType.IMPROVE]

    def execute(self, context: AgentContext) -> AgentResult:
        """
        Execute code generation based on context.

        Determines whether to draft new code or improve existing code
        based on the context.
        """
        start_time = time.time()
        self.prepare(context)

        try:
            # Validate context
            errors = self.validate_context(context)
            if errors:
                return AgentResult(
                    success=False,
                    error_message=f"Context validation failed: {', '.join(errors)}",
                    action_type="draft",
                    duration_seconds=time.time() - start_time
                )

            # Determine operation type
            has_parent = context.parent_node is not None
            task_type = TaskType.IMPROVE if has_parent else TaskType.DRAFT

            # Generate code
            if task_type == TaskType.DRAFT:
                result = self._generate_draft(context)
            else:
                result = self._generate_improvement(context)

            result.duration_seconds = time.time() - start_time
            return result

        except Exception as e:
            logger.error(f"CoderAgent execution failed: {e}")
            return AgentResult(
                success=False,
                error_message=str(e),
                action_type="draft" if not context.parent_node else "improve",
                duration_seconds=time.time() - start_time,
                needs_debugging=True
            )
        finally:
            self.cleanup()

    def _generate_draft(self, context: AgentContext) -> AgentResult:
        """
        Generate initial draft implementation.

        Creates a baseline implementation based on the research idea.
        """
        logger.info("CoderAgent generating draft implementation")

        # Build prompt
        prompt = self._build_draft_prompt(context)

        # This is a placeholder - actual implementation would call the LLM
        # In the refactored architecture, this would use the backend query
        plan = f"Draft plan for: {context.task_description[:100]}"
        code = "# Placeholder - LLM integration pending"

        return AgentResult(
            success=True,
            plan=plan,
            code=code,
            action_type="draft",
            notes="Generated initial draft implementation",
            recommendations=["Execute code to test baseline", "Review for obvious issues"],
            confidence=0.7,
            needs_debugging=False,
            needs_improvement=True
        )

    def _generate_improvement(self, context: AgentContext) -> AgentResult:
        """
        Generate improved implementation based on parent node.

        Enhances the existing implementation with feedback.
        """
        logger.info("CoderAgent generating improvement")

        if not context.parent_node:
            return AgentResult(
                success=False,
                error_message="No parent node provided for improvement",
                action_type="improve"
            )

        # Build prompt
        prompt = self._build_improve_prompt(context)

        # Placeholder for LLM call
        plan = f"Improvement plan based on feedback"
        code = context.parent_node.get("code", "") + "\n# Improved"

        return AgentResult(
            success=True,
            plan=plan,
            code=code,
            action_type="improve",
            notes="Generated improved implementation",
            recommendations=["Execute to verify improvement", "Check metrics"],
            confidence=0.6,
            needs_debugging=False
        )

    def _build_draft_prompt(self, context: AgentContext) -> Dict[str, Any]:
        """Build the prompt for draft generation."""
        prompt = {
            "Introduction": self._draft_intro,
            "Research idea": context.task_description,
        }

        # Add ledger context if available (Magentic-One pattern)
        if context.task_ledger_summary:
            prompt["Knowledge Context"] = context.task_ledger_summary

        # Add memory/history
        if context.previous_agent_feedback:
            prompt["Memory"] = "\n".join(context.previous_agent_feedback)

        # Add stage-specific instructions
        prompt["Stage Goals"] = context.stage_goals

        return prompt

    def _build_improve_prompt(self, context: AgentContext) -> Dict[str, Any]:
        """Build the prompt for improvement generation."""
        prompt = {
            "Introduction": self._improve_intro,
            "Research idea": context.task_description,
        }

        if context.parent_node:
            prompt["Previous solution"] = {
                "Code": context.parent_node.get("code", ""),
                "Analysis": context.parent_node.get("analysis", ""),
            }

        # Add feedback
        if context.previous_agent_feedback:
            prompt["Feedback"] = "\n".join(context.previous_agent_feedback)

        # Add ledger context
        if context.progress_ledger_summary:
            prompt["Progress Context"] = context.progress_ledger_summary

        prompt["Stage Goals"] = context.stage_goals

        return prompt

    def validate_context(self, context: AgentContext) -> List[str]:
        """Validate context for code generation."""
        errors = super().validate_context(context)

        if not context.task_description:
            errors.append("Task description is required for code generation")

        return errors

    def get_recommendations(self, result: AgentResult) -> List[str]:
        """Generate recommendations based on code generation result."""
        recommendations = super().get_recommendations(result)

        if result.success:
            recommendations.append("Run analyst agent to evaluate results")

            if result.action_type == "draft":
                recommendations.append("Consider tuning hyperparameters after baseline verification")

        return recommendations
