"""
Requirements Iterative Improver - Debug and improve requirement nodes.

Based on ai_scientist/treesearch/parallel_agent.py debug/improve patterns.
Implements the debug/improve loop for iterative requirement refinement.
"""

from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
import logging
import json
import copy

from .re_journal import RequirementNode, RequirementJournal
from ..utils.metrics import max_severity

logger = logging.getLogger("re-improver")


@dataclass
class DiagnosisResult:
    """Result of diagnosing a requirement node."""
    is_buggy: bool
    quality_issues: List[str]
    improvement_hints: List[str]
    severity: str = "low"  # low, medium, high, critical

    @property
    def needs_debug(self) -> bool:
        """Check if node needs debugging (has critical/high issues)."""
        return self.is_buggy and self.severity in ["high", "critical"]

    @property
    def can_improve(self) -> bool:
        """Check if node can be improved (has hints and is not critical)."""
        return len(self.improvement_hints) > 0 and not self.needs_debug


class IterativeImprover:
    """
    Implements the debug/improve loop for requirements.

    Debug: Fix quality issues (is_buggy = True)
    Improve: Enhance already-good requirements
    """

    def __init__(
        self,
        config: Dict[str, Any],
        journal: RequirementJournal,
        query_func: Any = None
    ):
        """
        Initialize the improver.

        Args:
            config: Configuration dict
            journal: RequirementJournal instance
            query_func: LLM query function
        """
        self.config = config
        self.journal = journal
        self.query_func = query_func

        # Search config
        search_config = config.get("agent", {}).get("search", {})
        self.max_debug_depth = search_config.get("max_debug_depth", 2)
        self.debug_prob = search_config.get("debug_prob", 0.5)

        # Validation thresholds
        self.thresholds = config.get("validation", {})

    def diagnose(self, node: RequirementNode) -> DiagnosisResult:
        """
        Diagnose a requirement node for quality issues.

        Args:
            node: RequirementNode to diagnose

        Returns:
            DiagnosisResult with issues and hints
        """
        issues = []
        hints = []
        severity = "low"

        # Check each quality metric
        if node.completeness_score < self.thresholds.get("min_completeness", 0.8):
            issues.append(f"Incomplete: missing details (score: {node.completeness_score:.2f})")
            hints.append("Add more specific details about scope, constraints, and context")
            severity = max_severity(severity, "medium")

        if node.consistency_score < self.thresholds.get("min_consistency", 0.9):
            issues.append(f"Inconsistent: potential contradictions (score: {node.consistency_score:.2f})")
            hints.append("Review for conflicting statements and clarify ambiguities")
            severity = max_severity(severity, "high")

        if node.testability_score < self.thresholds.get("min_testability", 0.75):
            issues.append(f"Not testable: unclear acceptance criteria (score: {node.testability_score:.2f})")
            hints.append("Add measurable acceptance criteria with specific conditions")
            severity = max_severity(severity, "medium")

        if node.clarity_score < self.thresholds.get("min_clarity", 0.8):
            issues.append(f"Unclear: ambiguous language (score: {node.clarity_score:.2f})")
            hints.append("Use precise, unambiguous language; avoid jargon")
            severity = max_severity(severity, "medium")

        if node.feasibility_score < self.thresholds.get("min_feasibility", 0.75):
            issues.append(f"Infeasible: may be too difficult (score: {node.feasibility_score:.2f})")
            hints.append("Review technical constraints and consider alternatives")
            severity = max_severity(severity, "high")

        if node.traceability_score < self.thresholds.get("min_traceability", 0.8):
            issues.append(f"Poor traceability: unclear linkage (score: {node.traceability_score:.2f})")
            hints.append("Add explicit links to business goals and related requirements")
            severity = max_severity(severity, "low")

        # Additional structural checks
        if not node.title:
            issues.append("Missing title")
            severity = "critical"

        if not node.description or len(node.description) < 20:
            issues.append("Description too short or missing")
            hints.append("Provide a detailed description of the requirement")
            severity = max_severity(severity, "high")

        if not node.acceptance_criteria:
            issues.append("No acceptance criteria defined")
            hints.append("Add at least one measurable acceptance criterion")
            severity = max_severity(severity, "medium")

        # Add improvement hints even if not buggy
        if len(hints) == 0 and node.aggregate_score() < 0.9:
            hints.append("Consider adding more acceptance criteria")
            hints.append("Review for edge cases and error scenarios")
            hints.append("Ensure dependencies are clearly documented")

        return DiagnosisResult(
            is_buggy=len(issues) > 0,
            quality_issues=issues,
            improvement_hints=hints,
            severity=severity
        )

    def debug_node(
        self,
        node: RequirementNode,
        diagnosis: DiagnosisResult
    ) -> RequirementNode:
        """
        Create a fixed version of a buggy node.

        Args:
            node: The buggy RequirementNode
            diagnosis: DiagnosisResult with issues

        Returns:
            New RequirementNode with fixes applied
        """
        # Check debug depth
        current_depth = self.journal.get_debug_depth(node)
        if current_depth >= self.max_debug_depth:
            logger.warning(f"Max debug depth ({self.max_debug_depth}) reached for {node.requirement_id}")
            # Return node as-is but mark as having reached limit
            return node

        # Create child node
        fixed_node = self._create_child_node(node, "debug")

        if self.query_func:
            # Use LLM to fix issues
            fixed_node = self._fix_with_llm(fixed_node, diagnosis)
        else:
            # Apply simple fixes without LLM
            fixed_node = self._apply_simple_fixes(fixed_node, diagnosis)

        # Re-check quality
        fixed_node.check_quality(self.thresholds)

        logger.info(f"Debug: {node.requirement_id} v{node.version} -> v{fixed_node.version} "
                   f"(issues: {len(diagnosis.quality_issues)} -> {len(fixed_node.quality_issues)})")

        return fixed_node

    def improve_node(
        self,
        node: RequirementNode,
        hints: List[str] = None
    ) -> RequirementNode:
        """
        Create an improved version of a good node.

        Args:
            node: The RequirementNode to improve
            hints: Optional improvement hints

        Returns:
            New RequirementNode with improvements
        """
        # Create child node
        improved_node = self._create_child_node(node, "improve")

        if self.query_func:
            # Use LLM to improve
            improved_node = self._improve_with_llm(improved_node, hints)
        else:
            # Apply simple improvements without LLM
            improved_node = self._apply_simple_improvements(improved_node, hints)

        # Re-check quality
        improved_node.check_quality(self.thresholds)

        logger.info(f"Improve: {node.requirement_id} v{node.version} -> v{improved_node.version} "
                   f"(score: {node.aggregate_score():.2f} -> {improved_node.aggregate_score():.2f})")

        return improved_node

    def _create_child_node(
        self,
        parent: RequirementNode,
        stage_name: str
    ) -> RequirementNode:
        """Create a child node from a parent using deep copy."""
        child = copy.deepcopy(parent)

        # Reset identity and tree structure for the new version
        child.id = __import__("uuid").uuid4().hex
        child.version = parent.version + 1
        child.parent_version_id = parent.id
        child.children_version_ids = set()
        child.stage_name = stage_name
        child.created_at = __import__("datetime").datetime.now().isoformat()
        child.updated_at = child.created_at

        return child

    def _fix_with_llm(
        self,
        node: RequirementNode,
        diagnosis: DiagnosisResult
    ) -> RequirementNode:
        """Use LLM to fix quality issues."""
        fix_prompt = f"""Fix the following requirement based on the identified issues:

## Current Requirement
Title: {node.title}
Description: {node.description}
Type: {node.type}
Priority: {node.priority}
Acceptance Criteria: {json.dumps(node.acceptance_criteria)}

## Issues to Fix
{chr(10).join(f"- {issue}" for issue in diagnosis.quality_issues)}

## Hints
{chr(10).join(f"- {hint}" for hint in diagnosis.improvement_hints)}

Return the fixed requirement in JSON format:
```json
{{
    "title": "...",
    "description": "...",
    "acceptance_criteria": ["..."],
    "rationale": "..."
}}
```"""

        # Get model from config - check core.improver first, then agent.code
        core_config = self.config.get("core", {}).get("improver", {})
        code_config = self.config.get("agent", {}).get("code", {})
        model = core_config.get("model") or code_config.get("model", "google/gemini-2.0-flash-exp:free")
        response, _, _, _, _ = self.query_func(
            system_message="You are a requirements engineering expert. Fix the requirement issues.",
            user_message=fix_prompt,
            model=model,
            temperature=core_config.get("temperature", 0.5),
            max_tokens=core_config.get("max_tokens", 2000)
        )

        return self._parse_llm_response(node, response)

    def _improve_with_llm(
        self,
        node: RequirementNode,
        hints: List[str] = None
    ) -> RequirementNode:
        """Use LLM to improve a requirement."""
        improve_prompt = f"""Improve the following requirement to make it more complete and precise:

## Current Requirement
Title: {node.title}
Description: {node.description}
Type: {node.type}
Priority: {node.priority}
Acceptance Criteria: {json.dumps(node.acceptance_criteria)}
Current Score: {node.aggregate_score():.2f}

## Improvement Suggestions
{chr(10).join(f"- {hint}" for hint in (hints or [])) or "- Enhance detail and precision"}

Return the improved requirement in JSON format:
```json
{{
    "title": "...",
    "description": "...",
    "acceptance_criteria": ["..."],
    "rationale": "..."
}}
```"""

        # Get model from config - check core.improver first, then agent.code
        core_config = self.config.get("core", {}).get("improver", {})
        code_config = self.config.get("agent", {}).get("code", {})
        model = core_config.get("model") or code_config.get("model", "google/gemini-2.0-flash-exp:free")
        response, _, _, _, _ = self.query_func(
            system_message="You are a requirements engineering expert. Improve the requirement.",
            user_message=improve_prompt,
            model=model,
            temperature=core_config.get("temperature", 0.7),
            max_tokens=core_config.get("max_tokens", 2000)
        )

        return self._parse_llm_response(node, response)

    def _parse_llm_response(
        self,
        node: RequirementNode,
        response: str
    ) -> RequirementNode:
        """Parse LLM response and update node."""
        try:
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
                data = json.loads(json_str)

                if "title" in data:
                    node.title = data["title"]
                if "description" in data:
                    node.description = data["description"]
                if "acceptance_criteria" in data:
                    node.acceptance_criteria = data["acceptance_criteria"]
                if "rationale" in data:
                    node.rationale = data["rationale"]

        except (json.JSONDecodeError, IndexError) as e:
            logger.error(f"Failed to parse LLM response: {e}")

        return node

    def _apply_simple_fixes(
        self,
        node: RequirementNode,
        diagnosis: DiagnosisResult
    ) -> RequirementNode:
        """Apply simple fixes without LLM."""
        # Add placeholder acceptance criterion if missing
        if not node.acceptance_criteria:
            node.acceptance_criteria = [
                "Given the system is running, when this feature is used, then the expected outcome occurs"
            ]
            node.testability_score = 0.6

        # Add placeholder description if too short
        if len(node.description) < 20:
            node.description = f"{node.description} [Additional details needed: scope, constraints, expected behavior]"
            node.completeness_score = 0.6

        # Mark fixes applied
        node.analysis = f"Applied {len(diagnosis.quality_issues)} fixes"
        node.improvement_suggestions = diagnosis.improvement_hints

        return node

    def _apply_simple_improvements(
        self,
        node: RequirementNode,
        hints: List[str] = None
    ) -> RequirementNode:
        """Apply simple improvements without LLM."""
        # Boost scores slightly (simulating improvement)
        node.completeness_score = min(1.0, node.completeness_score + 0.05)
        node.clarity_score = min(1.0, node.clarity_score + 0.05)
        node.testability_score = min(1.0, node.testability_score + 0.05)

        # Add note about improvements
        node.analysis = f"Applied improvements based on: {hints or ['general enhancement']}"

        return node

    def iterate(
        self,
        node: RequirementNode,
        max_iterations: int = 3
    ) -> RequirementNode:
        """
        Run the debug/improve loop until quality thresholds are met.

        Args:
            node: Starting RequirementNode
            max_iterations: Maximum iterations

        Returns:
            Best node after iterations
        """
        current = node

        for i in range(max_iterations):
            diagnosis = self.diagnose(current)

            if not diagnosis.is_buggy and not diagnosis.can_improve:
                logger.info(f"Iteration {i+1}: Node meets all thresholds")
                break

            if diagnosis.needs_debug:
                current = self.debug_node(current, diagnosis)
                self.journal.add_node(current)
            elif diagnosis.can_improve:
                current = self.improve_node(current, diagnosis.improvement_hints)
                self.journal.add_node(current)
            else:
                break

        return current
