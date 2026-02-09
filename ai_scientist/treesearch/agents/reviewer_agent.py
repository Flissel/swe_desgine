"""
Reviewer Agent for Magentic-One inspired AI-Scientist architecture.

This agent specializes in stage completion evaluation:
- Quality assessment of experiments
- Stage completion criteria checking
- Recommendations for next steps

Extracted from the AgentManager's _check_stage_completion method.
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
    from ..journal import Journal

logger = logging.getLogger(__name__)


class ReviewerAgent(BaseResearchAgent):
    """
    Specialized agent for stage completion review.

    This agent handles:
    - Review: Assess experiment quality and completeness
    - Criteria: Check if stage goals are met
    - Decision: Recommend stage transition or continuation

    It evaluates whether the current stage is complete and
    provides guidance for the orchestrator.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(
            name="reviewer",
            description="Evaluates stage completion and recommends next steps",
            capabilities=[
                AgentCapability.STAGE_REVIEW,
            ],
            config=config or {}
        )

        self._review_intro = (
            "You are a senior AI researcher reviewing experimental progress. "
            "Your task is to evaluate whether the current stage is complete "
            "and the experiment is ready to progress to the next stage."
        )

        # Stage-specific completion criteria
        self._stage_criteria = {
            1: {  # Initial Implementation
                "name": "Initial Implementation",
                "required": ["Working baseline", "Basic metrics reported"],
                "optional": ["Simple visualization", "Single dataset tested"],
            },
            2: {  # Baseline Tuning
                "name": "Baseline Tuning",
                "required": ["Hyperparameters optimized", "Multiple datasets tested"],
                "optional": ["Stable training curves", "Documented improvements"],
            },
            3: {  # Creative Research
                "name": "Creative Research",
                "required": ["Novel improvements explored", "Insights documented"],
                "optional": ["Multiple approaches compared", "Best approach identified"],
            },
            4: {  # Ablation Studies
                "name": "Ablation Studies",
                "required": ["Key components ablated", "Contributions documented"],
                "optional": ["Statistical significance", "Comprehensive analysis"],
            },
        }

    def can_handle(self, task_type: TaskType) -> bool:
        """Check if this agent can handle the task."""
        return task_type == TaskType.REVIEW

    def execute(self, context: AgentContext) -> AgentResult:
        """
        Execute stage completion review.

        Evaluates whether the current stage is complete.
        """
        start_time = time.time()
        self.prepare(context)

        try:
            errors = self.validate_context(context)
            if errors:
                return AgentResult(
                    success=False,
                    error_message=f"Context validation failed: {', '.join(errors)}",
                    action_type="review",
                    duration_seconds=time.time() - start_time
                )

            result = self._review_stage(context)
            result.duration_seconds = time.time() - start_time

            return result

        except Exception as e:
            logger.error(f"ReviewerAgent execution failed: {e}")
            return AgentResult(
                success=False,
                error_message=str(e),
                action_type="review",
                duration_seconds=time.time() - start_time
            )
        finally:
            self.cleanup()

    def _review_stage(self, context: AgentContext) -> AgentResult:
        """
        Review the current stage for completion.
        """
        logger.info(f"ReviewerAgent reviewing stage {context.stage_number}")

        # Get criteria for this stage
        criteria = self._stage_criteria.get(context.stage_number, self._stage_criteria[1])

        # Evaluate criteria
        evaluation = self._evaluate_criteria(context, criteria)

        # Determine completion status
        required_met = evaluation.get("required_met", 0)
        required_total = evaluation.get("required_total", 1)
        completion_ratio = required_met / required_total if required_total > 0 else 0

        stage_complete = completion_ratio >= 1.0

        # Generate analysis
        analysis_parts = [
            f"Stage: {criteria['name']} (Stage {context.stage_number})",
            f"Required criteria met: {required_met}/{required_total}",
            f"Optional criteria met: {evaluation.get('optional_met', 0)}/{evaluation.get('optional_total', 0)}",
            "",
            "Detailed Assessment:",
        ]

        for criterion, status in evaluation.get("details", {}).items():
            status_str = "MET" if status else "NOT MET"
            analysis_parts.append(f"  - {criterion}: {status_str}")

        # Generate recommendations
        recommendations = []
        if stage_complete:
            recommendations.append(f"Stage {context.stage_number} complete - ready for next stage")
            recommendations.append("Run multi-seed evaluation for robustness")
        else:
            missing = evaluation.get("missing_criteria", [])
            recommendations.append(f"Stage not complete - missing: {', '.join(missing)}")
            recommendations.append("Continue current stage to meet criteria")

        # Check for stagnation via ledger
        if context.progress_ledger_summary and "stagnation" in context.progress_ledger_summary.lower():
            recommendations.append("Stagnation detected - consider alternative approaches")

        return AgentResult(
            success=True,
            analysis="\n".join(analysis_parts),
            action_type="review",
            notes=f"Stage {context.stage_number} review: {'COMPLETE' if stage_complete else 'INCOMPLETE'}",
            recommendations=recommendations,
            confidence=0.8 if stage_complete else 0.6,
            stage_complete=stage_complete,
            needs_improvement=not stage_complete
        )

    def _evaluate_criteria(self, context: AgentContext, criteria: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate completion criteria.
        """
        evaluation = {
            "required_met": 0,
            "required_total": len(criteria.get("required", [])),
            "optional_met": 0,
            "optional_total": len(criteria.get("optional", [])),
            "details": {},
            "missing_criteria": [],
        }

        # Check required criteria
        for req in criteria.get("required", []):
            met = self._check_criterion(context, req)
            evaluation["details"][f"[Required] {req}"] = met
            if met:
                evaluation["required_met"] += 1
            else:
                evaluation["missing_criteria"].append(req)

        # Check optional criteria
        for opt in criteria.get("optional", []):
            met = self._check_criterion(context, opt)
            evaluation["details"][f"[Optional] {opt}"] = met
            if met:
                evaluation["optional_met"] += 1

        return evaluation

    def _check_criterion(self, context: AgentContext, criterion: str) -> bool:
        """
        Check if a specific criterion is met.

        This is a simplified check - actual implementation would use
        more sophisticated analysis.
        """
        criterion_lower = criterion.lower()

        # Check against current node
        if context.current_node:
            node = context.current_node

            # Basic working implementation
            if "working" in criterion_lower:
                return not node.get("is_buggy", True)

            # Metrics reported
            if "metrics" in criterion_lower:
                return node.get("metric") is not None

            # Visualization
            if "visualization" in criterion_lower or "plots" in criterion_lower:
                plots = node.get("plots", [])
                return len(plots) > 0

            # Multiple datasets
            if "datasets" in criterion_lower:
                datasets = node.get("datasets_successfully_tested", [])
                return len(datasets) >= 2

        # Check against journal summary
        if context.journal_summary:
            summary_lower = context.journal_summary.lower()

            if "optimized" in criterion_lower:
                return "tuned" in summary_lower or "optimized" in summary_lower

            if "improvements" in criterion_lower:
                return "improvement" in summary_lower or "better" in summary_lower

            if "documented" in criterion_lower:
                return "analysis" in summary_lower

        # Default to not met for unknown criteria
        return False

    def validate_context(self, context: AgentContext) -> List[str]:
        """Validate context for review."""
        errors = super().validate_context(context)

        if context.stage_number < 1 or context.stage_number > 4:
            errors.append(f"Invalid stage number: {context.stage_number}")

        return errors
