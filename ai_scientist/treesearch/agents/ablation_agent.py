"""
Ablation Agent for Magentic-One inspired AI-Scientist architecture.

This agent specializes in ablation studies:
- Component isolation and removal
- Contribution analysis
- Systematic experimentation

Extracted from the ParallelAgent's _generate_ablation_node method.
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


class AblationAgent(BaseResearchAgent):
    """
    Specialized agent for ablation studies.

    This agent handles:
    - Ablate: Remove or modify specific components
    - Analyze: Understand contribution of each part
    - Compare: Systematic comparison of variants

    It creates experiments that isolate the contribution of
    individual components to understand their importance.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(
            name="ablation",
            description="Conducts ablation studies to analyze component contributions",
            capabilities=[
                AgentCapability.ABLATION_ANALYSIS,
            ],
            config=config or {}
        )

        self._ablation_intro = (
            "You are an expert AI researcher conducting ablation studies. "
            "Your task is to systematically remove or modify components of the "
            "implementation to understand their individual contributions to the "
            "overall performance."
        )

        # Common ablation strategies
        self._ablation_strategies = [
            "Remove component entirely",
            "Replace with simpler baseline",
            "Modify key hyperparameter",
            "Change architectural element",
            "Remove regularization technique",
        ]

    def can_handle(self, task_type: TaskType) -> bool:
        """Check if this agent can handle the task."""
        return task_type == TaskType.ABLATE

    def execute(self, context: AgentContext) -> AgentResult:
        """
        Execute ablation study.

        Generates an ablation variant of the parent implementation.
        """
        start_time = time.time()
        self.prepare(context)

        try:
            errors = self.validate_context(context)
            if errors:
                return AgentResult(
                    success=False,
                    error_message=f"Context validation failed: {', '.join(errors)}",
                    action_type="ablate",
                    duration_seconds=time.time() - start_time
                )

            result = self._generate_ablation(context)
            result.duration_seconds = time.time() - start_time

            return result

        except Exception as e:
            logger.error(f"AblationAgent execution failed: {e}")
            return AgentResult(
                success=False,
                error_message=str(e),
                action_type="ablate",
                duration_seconds=time.time() - start_time
            )
        finally:
            self.cleanup()

    def _generate_ablation(self, context: AgentContext) -> AgentResult:
        """
        Generate ablation study experiment.
        """
        logger.info("AblationAgent generating ablation study")

        if not context.parent_node:
            return AgentResult(
                success=False,
                error_message="No parent node for ablation",
                action_type="ablate"
            )

        # Identify components to ablate
        ablation_target = self._identify_ablation_target(context)

        # Build ablation prompt
        prompt = self._build_ablation_prompt(context, ablation_target)

        # Placeholder for LLM call
        component = ablation_target.get("component", "component")
        strategy = ablation_target.get("strategy", "remove")
        plan = f"Ablation: {strategy} {component}"
        code = context.parent_node.get("code", "") + f"\n# Ablation: {component} - {strategy}"

        return AgentResult(
            success=True,
            plan=plan,
            code=code,
            action_type="ablate",
            notes=f"Generated ablation for {component}",
            recommendations=[
                "Execute ablation experiment",
                "Compare metrics with full model",
                "Document component contribution"
            ],
            confidence=0.7
        )

    def _identify_ablation_target(self, context: AgentContext) -> Dict[str, Any]:
        """
        Identify the best component to ablate.
        """
        target = {
            "component": "key_component",
            "strategy": "remove",
            "reason": "investigate contribution",
        }

        if context.parent_node:
            # Analyze code to find ablation targets
            code = context.parent_node.get("code", "")

            # Simple heuristics for common ablation targets
            if "dropout" in code.lower():
                target["component"] = "dropout"
                target["strategy"] = "remove dropout"
                target["reason"] = "test if regularization is necessary"

            elif "attention" in code.lower():
                target["component"] = "attention mechanism"
                target["strategy"] = "replace with simple averaging"
                target["reason"] = "measure attention contribution"

            elif "batch_norm" in code.lower() or "BatchNorm" in code:
                target["component"] = "batch normalization"
                target["strategy"] = "remove batch norm"
                target["reason"] = "test normalization importance"

            elif "residual" in code.lower() or "skip" in code.lower():
                target["component"] = "residual connections"
                target["strategy"] = "remove skip connections"
                target["reason"] = "measure residual contribution"

        # Use progress ledger to avoid redundant ablations
        if context.task_ledger_summary:
            if target["component"] in context.task_ledger_summary:
                target["component"] = "alternative_component"
                target["reason"] = "previous ablation already done"

        return target

    def _build_ablation_prompt(self, context: AgentContext, target: Dict[str, Any]) -> Dict[str, Any]:
        """Build prompt for ablation generation."""
        prompt = {
            "Introduction": self._ablation_intro,
            "Research idea": context.task_description,
            "Stage Goals": context.stage_goals,
        }

        if context.parent_node:
            prompt["Full implementation"] = context.parent_node.get("code", "")
            prompt["Full model performance"] = context.parent_node.get("analysis", "")

        prompt["Ablation Target"] = {
            "Component": target.get("component"),
            "Strategy": target.get("strategy"),
            "Reason": target.get("reason"),
        }

        prompt["Ablation Strategies"] = self._ablation_strategies

        # Add ledger context to track which ablations have been done
        if context.task_ledger_summary:
            prompt["Previous ablations"] = context.task_ledger_summary

        return prompt

    def validate_context(self, context: AgentContext) -> List[str]:
        """Validate context for ablation."""
        errors = super().validate_context(context)

        if not context.parent_node:
            errors.append("Parent node required for ablation study")

        return errors
