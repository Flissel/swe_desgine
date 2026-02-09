"""
Tuner Agent for Magentic-One inspired AI-Scientist architecture.

This agent specializes in hyperparameter tuning:
- Hyperparameter selection and ranges
- Tuning strategy (grid, random, Bayesian)
- Performance optimization

Extracted from the ParallelAgent's _generate_hyperparam_tuning_node method.
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


class TunerAgent(BaseResearchAgent):
    """
    Specialized agent for hyperparameter tuning.

    This agent handles:
    - Tune: Generate hyperparameter variations
    - Strategy: Select appropriate tuning approach
    - Optimization: Guide search towards better configurations

    It creates experiment variations with different hyperparameter
    configurations to optimize model performance.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(
            name="tuner",
            description="Generates hyperparameter tuning experiments",
            capabilities=[
                AgentCapability.HYPERPARAMETER_TUNING,
            ],
            config=config or {}
        )

        self._tuning_intro = (
            "You are an expert AI researcher specializing in hyperparameter optimization. "
            "Your task is to propose effective hyperparameter modifications to improve "
            "the baseline implementation's performance."
        )

        # Common hyperparameters to tune
        self._common_hyperparams = [
            ("learning_rate", "float", "1e-5 to 1e-2"),
            ("batch_size", "int", "8 to 128"),
            ("num_epochs", "int", "5 to 100"),
            ("hidden_dim", "int", "64 to 1024"),
            ("dropout", "float", "0.0 to 0.5"),
            ("weight_decay", "float", "0 to 0.1"),
            ("optimizer", "choice", "adam, sgd, adamw"),
        ]

    def can_handle(self, task_type: TaskType) -> bool:
        """Check if this agent can handle the task."""
        return task_type == TaskType.TUNE

    def execute(self, context: AgentContext) -> AgentResult:
        """
        Execute hyperparameter tuning.

        Generates a tuned version of the parent implementation.
        """
        start_time = time.time()
        self.prepare(context)

        try:
            errors = self.validate_context(context)
            if errors:
                return AgentResult(
                    success=False,
                    error_message=f"Context validation failed: {', '.join(errors)}",
                    action_type="tune",
                    duration_seconds=time.time() - start_time
                )

            result = self._generate_tuning(context)
            result.duration_seconds = time.time() - start_time

            return result

        except Exception as e:
            logger.error(f"TunerAgent execution failed: {e}")
            return AgentResult(
                success=False,
                error_message=str(e),
                action_type="tune",
                duration_seconds=time.time() - start_time
            )
        finally:
            self.cleanup()

    def _generate_tuning(self, context: AgentContext) -> AgentResult:
        """
        Generate hyperparameter tuning experiment.
        """
        logger.info("TunerAgent generating hyperparameter tuning")

        if not context.parent_node:
            return AgentResult(
                success=False,
                error_message="No parent node for tuning",
                action_type="tune"
            )

        # Analyze current performance to guide tuning
        tuning_suggestions = self._analyze_for_tuning(context)

        # Build tuning prompt
        prompt = self._build_tuning_prompt(context, tuning_suggestions)

        # Placeholder for LLM call
        hyperparam_name = tuning_suggestions.get("primary_param", "learning_rate")
        plan = f"Tune {hyperparam_name}: {tuning_suggestions.get('suggestion', 'adjust')}"
        code = context.parent_node.get("code", "") + f"\n# Tuned: {hyperparam_name}"

        return AgentResult(
            success=True,
            plan=plan,
            code=code,
            action_type="tune",
            notes=f"Generated tuning experiment for {hyperparam_name}",
            recommendations=[
                "Execute tuned experiment",
                "Compare metrics with baseline",
                "Consider further tuning if improvement seen"
            ],
            confidence=0.6
        )

    def _analyze_for_tuning(self, context: AgentContext) -> Dict[str, Any]:
        """
        Analyze context to determine best tuning strategy.
        """
        suggestions = {
            "primary_param": "learning_rate",
            "suggestion": "try lower learning rate",
            "reason": "default suggestion",
        }

        if context.parent_node:
            # Check execution time - if too fast, might need more epochs
            exec_time = context.parent_node.get("exec_time", 0)
            if exec_time < 60:  # Less than a minute
                suggestions["primary_param"] = "num_epochs"
                suggestions["suggestion"] = "increase epochs for better convergence"
                suggestions["reason"] = "training completed quickly"

            # Check for convergence issues in analysis
            analysis = context.parent_node.get("analysis", "")
            if "overfit" in analysis.lower():
                suggestions["primary_param"] = "dropout"
                suggestions["suggestion"] = "increase dropout for regularization"
                suggestions["reason"] = "overfitting detected"
            elif "underfit" in analysis.lower():
                suggestions["primary_param"] = "hidden_dim"
                suggestions["suggestion"] = "increase model capacity"
                suggestions["reason"] = "underfitting detected"

        return suggestions

    def _build_tuning_prompt(self, context: AgentContext, suggestions: Dict[str, Any]) -> Dict[str, Any]:
        """Build prompt for tuning generation."""
        prompt = {
            "Introduction": self._tuning_intro,
            "Research idea": context.task_description,
            "Stage Goals": context.stage_goals,
        }

        if context.parent_node:
            prompt["Baseline implementation"] = context.parent_node.get("code", "")
            prompt["Baseline performance"] = context.parent_node.get("analysis", "")

        prompt["Tuning Suggestions"] = {
            "Primary parameter": suggestions.get("primary_param"),
            "Suggestion": suggestions.get("suggestion"),
            "Reason": suggestions.get("reason"),
        }

        prompt["Common hyperparameters"] = [
            f"{name} ({typ}): typical range {range_}"
            for name, typ, range_ in self._common_hyperparams
        ]

        return prompt

    def validate_context(self, context: AgentContext) -> List[str]:
        """Validate context for tuning."""
        errors = super().validate_context(context)

        if not context.parent_node:
            errors.append("Parent node required for hyperparameter tuning")

        return errors
