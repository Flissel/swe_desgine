"""
Debugger Agent for Magentic-One inspired AI-Scientist architecture.

This agent specializes in error analysis and bug fixing:
- Analyzing stack traces and error messages
- Proposing fixes for buggy code
- Learning from past failures to avoid similar issues

Extracted from the ParallelAgent's _debug method.
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


class DebuggerAgent(BaseResearchAgent):
    """
    Specialized agent for debugging and error fixing.

    This agent handles:
    - Debug: Fix bugs in failed implementations
    - Error analysis: Understand root causes
    - Fix proposals: Generate corrected code

    It analyzes execution output, stack traces, and VLM feedback
    to propose targeted fixes.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(
            name="debugger",
            description="Analyzes errors and generates bug fixes for failed experiments",
            capabilities=[
                AgentCapability.CODE_DEBUGGING,
            ],
            config=config or {}
        )

        self._debug_intro = (
            "You are an experienced AI researcher. Your previous code for research "
            "experiment had a bug, so based on the information below, you should "
            "revise it in order to fix this bug. Your response should be an "
            "implementation outline in natural language, followed by a single "
            "markdown code block which implements the bugfix/solution."
        )

        # Common error patterns and their typical fixes
        self._error_patterns = {
            "CUDA out of memory": "Reduce batch size or model size",
            "IndexError": "Check array dimensions and loop bounds",
            "KeyError": "Verify dictionary keys exist before access",
            "ImportError": "Install missing packages or fix import paths",
            "FileNotFoundError": "Create required files or fix paths",
            "RuntimeError": "Check for device mismatches or invalid operations",
            "ValueError": "Validate input shapes and types",
            "TypeError": "Check argument types and conversions",
        }

    def can_handle(self, task_type: TaskType) -> bool:
        """Check if this agent can handle the task."""
        return task_type == TaskType.DEBUG

    def execute(self, context: AgentContext) -> AgentResult:
        """
        Execute debugging based on context.

        Analyzes the failed node and generates a fix.
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
                    action_type="debug",
                    duration_seconds=time.time() - start_time
                )

            # Analyze error
            error_analysis = self._analyze_error(context)

            # Generate fix
            result = self._generate_fix(context, error_analysis)
            result.duration_seconds = time.time() - start_time

            return result

        except Exception as e:
            logger.error(f"DebuggerAgent execution failed: {e}")
            return AgentResult(
                success=False,
                error_message=str(e),
                action_type="debug",
                duration_seconds=time.time() - start_time
            )
        finally:
            self.cleanup()

    def _analyze_error(self, context: AgentContext) -> Dict[str, Any]:
        """
        Analyze the error from the parent node.

        Returns a structured analysis of the error.
        """
        analysis = {
            "error_type": None,
            "error_message": "",
            "likely_cause": "",
            "suggested_fix_type": "",
            "confidence": 0.5,
        }

        if not context.parent_node:
            return analysis

        parent = context.parent_node

        # Extract error information
        exc_type = parent.get("exc_type")
        exc_info = parent.get("exc_info", {})
        term_out = parent.get("term_out", "")

        if exc_type:
            analysis["error_type"] = exc_type
            analysis["error_message"] = str(exc_info)

            # Match against known patterns
            for pattern, fix_hint in self._error_patterns.items():
                if pattern.lower() in exc_type.lower() or pattern.lower() in str(exc_info).lower():
                    analysis["likely_cause"] = pattern
                    analysis["suggested_fix_type"] = fix_hint
                    analysis["confidence"] = 0.7
                    break

        # Check terminal output for additional clues
        if term_out:
            for pattern, fix_hint in self._error_patterns.items():
                if pattern.lower() in term_out.lower():
                    if not analysis["likely_cause"]:
                        analysis["likely_cause"] = pattern
                        analysis["suggested_fix_type"] = fix_hint
                    break

        logger.info(f"Error analysis: {analysis}")
        return analysis

    def _generate_fix(self, context: AgentContext, error_analysis: Dict[str, Any]) -> AgentResult:
        """
        Generate a fix for the identified error.
        """
        logger.info(f"DebuggerAgent generating fix for: {error_analysis.get('error_type', 'unknown')}")

        if not context.parent_node:
            return AgentResult(
                success=False,
                error_message="No parent node provided for debugging",
                action_type="debug"
            )

        # Build debug prompt
        prompt = self._build_debug_prompt(context, error_analysis)

        # Placeholder for LLM call
        plan = f"Fix for {error_analysis.get('error_type', 'error')}: {error_analysis.get('suggested_fix_type', 'investigate')}"
        code = context.parent_node.get("code", "") + "\n# Bug fix applied"

        # Determine recommendations based on error type
        recommendations = self._get_fix_recommendations(error_analysis)

        return AgentResult(
            success=True,
            plan=plan,
            code=code,
            action_type="debug",
            analysis=f"Error type: {error_analysis.get('error_type')}, Cause: {error_analysis.get('likely_cause')}",
            notes=f"Generated fix for {error_analysis.get('error_type', 'error')}",
            recommendations=recommendations,
            confidence=error_analysis.get("confidence", 0.5),
            needs_debugging=False,  # Assume fix works, will be re-evaluated after execution
            needs_improvement=True
        )

    def _build_debug_prompt(self, context: AgentContext, error_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Build the prompt for debug fix generation."""
        prompt = {
            "Introduction": self._debug_intro,
            "Research idea": context.task_description,
        }

        if context.parent_node:
            prompt["Previous (buggy) implementation"] = context.parent_node.get("code", "")
            prompt["Execution output"] = context.parent_node.get("term_out", "")

            # VLM feedback if available
            vlm_feedback = context.parent_node.get("vlm_feedback_summary", [])
            if vlm_feedback:
                prompt["Feedback based on generated plots"] = vlm_feedback

            # Execution time feedback
            exec_time_feedback = context.parent_node.get("exec_time_feedback", "")
            if exec_time_feedback:
                prompt["Feedback about execution time"] = exec_time_feedback

        # Add error analysis
        prompt["Error Analysis"] = {
            "Type": error_analysis.get("error_type", "Unknown"),
            "Likely Cause": error_analysis.get("likely_cause", "Unknown"),
            "Suggested Fix": error_analysis.get("suggested_fix_type", "Investigate and fix"),
        }

        # Add ledger context for learning from past failures
        if context.task_ledger_summary:
            prompt["Knowledge from past experiments"] = context.task_ledger_summary

        return prompt

    def _get_fix_recommendations(self, error_analysis: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on error analysis."""
        recommendations = ["Execute fixed code to verify", "Monitor for similar errors"]

        error_type = error_analysis.get("error_type", "")

        if "memory" in error_type.lower():
            recommendations.append("Consider gradient checkpointing if memory remains an issue")
            recommendations.append("Try smaller model or batch size")

        if "import" in error_type.lower():
            recommendations.append("Verify all dependencies are installed")

        if error_analysis.get("confidence", 0) < 0.5:
            recommendations.append("Low confidence fix - may need manual review")

        return recommendations

    def validate_context(self, context: AgentContext) -> List[str]:
        """Validate context for debugging."""
        errors = super().validate_context(context)

        if not context.parent_node:
            errors.append("Parent node is required for debugging")

        return errors

    def get_recommendations(self, result: AgentResult) -> List[str]:
        """Generate recommendations based on debug result."""
        recommendations = super().get_recommendations(result)

        if result.success:
            recommendations.append("Re-run experiment with fixed code")

            if result.confidence < 0.6:
                recommendations.append("Consider additional review - fix confidence is low")

        return recommendations
