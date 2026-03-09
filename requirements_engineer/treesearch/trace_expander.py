"""
Trace Expander - Generates and refines artifacts in the trace tree.

Three operations mirroring the AI-Scientist's node expansion:
- draft: Generate initial children from parent (e.g., requirements from epic)
- improve: Create improved version of existing artifact
- debug: Fix structural issues (missing fields, broken links)
"""

import copy
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .trace_node import TraceNode

log = logging.getLogger(__name__)

# LLM prompt templates for improvement
IMPROVE_REQUIREMENT_PROMPT = """You are a Requirements Engineering expert.
Improve this requirement based on the quality issues found.

PARENT EPIC:
  Title: {epic_title}
  Description: {epic_description}

CURRENT REQUIREMENT:
  ID: {req_id}
  Title: {req_title}
  Description: {req_description}
  Acceptance Criteria: {req_criteria}

QUALITY ISSUES:
{issues}

Return an improved version as JSON:
{{
    "title": "Improved title",
    "description": "Improved description (at least 20 words, specific, measurable)",
    "acceptance_criteria": ["criterion 1", "criterion 2", "criterion 3"]
}}
Return ONLY valid JSON."""

IMPROVE_USER_STORY_PROMPT = """You are a Requirements Engineering expert.
Improve this user story based on the quality issues found.

PARENT REQUIREMENT:
  ID: {req_id}
  Title: {req_title}
  Description: {req_description}
  Acceptance Criteria: {req_criteria}

CURRENT USER STORY:
  ID: {story_id}
  Title: {story_title}
  As a {persona}, I want to {action}, so that {benefit}
  Acceptance Criteria: {story_criteria}

QUALITY ISSUES:
{issues}

Return an improved version as JSON:
{{
    "title": "Improved title",
    "persona": "specific persona",
    "action": "detailed action",
    "benefit": "clear benefit",
    "acceptance_criteria": [
        {{"given": "...", "when": "...", "then": "..."}},
        {{"given": "...", "when": "...", "then": "..."}}
    ]
}}
Return ONLY valid JSON."""

IMPROVE_TEST_CASE_PROMPT = """You are a QA Engineering expert.
Improve this test case based on the quality issues found.

PARENT USER STORY:
  ID: {story_id}
  Title: {story_title}
  As a {persona}, I want to {action}, so that {benefit}
  Acceptance Criteria: {story_criteria}

CURRENT TEST CASE:
  ID: {tc_id}
  Title: {tc_title}
  Steps: {tc_steps}
  Expected: {tc_expected}

QUALITY ISSUES:
{issues}

Return an improved version as JSON:
{{
    "title": "Improved title",
    "description": "What this test verifies",
    "steps": [
        {{"action": "Step action", "expected_result": "What should happen"}}
    ],
    "expected_result": "Overall expected outcome",
    "test_type": "functional|integration|e2e|performance"
}}
Return ONLY valid JSON."""


def _parse_json_response(text: str) -> Optional[Dict]:
    """Parse JSON from LLM response, handling markdown fences."""
    text = text.strip()
    for attempt in [
        lambda: json.loads(text),
        lambda: json.loads(re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL).group(1)),
        lambda: json.loads(text[text.find("{"):text.rfind("}") + 1]),
    ]:
        try:
            return attempt()
        except (json.JSONDecodeError, AttributeError, ValueError):
            continue
    return None


class TraceExpander:
    """Generates or improves artifacts based on parent context and quality feedback.

    Mirrors AI-Scientist's draft/improve/debug expansion:
    - draft: Generate initial children from parent node
    - improve: Create better version using quality issues as guidance
    - debug: Fix structural problems (missing fields, broken links)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, llm_call=None):
        """Initialize expander.

        Args:
            config: Optional configuration.
            llm_call: Async callable(prompt: str) -> str for LLM generation.
        """
        self._call_llm = llm_call
        self._llm_calls = 0
        cfg = config or {}
        self.max_draft_children = cfg.get("max_draft_children", 5)

    @property
    def llm_calls_used(self) -> int:
        return self._llm_calls

    # ── Draft: Generate children from parent ─────────────────

    async def draft(self, parent_node: TraceNode) -> List[Any]:
        """Generate initial child artifacts from parent context.

        This creates new artifacts, NOT refinements of existing ones.
        E.g., generate requirements from epic, stories from requirement.
        """
        if parent_node.node_type == "epic":
            return self._draft_requirements_from_epic(parent_node)
        elif parent_node.node_type == "requirement":
            return self._draft_stories_from_requirement(parent_node)
        elif parent_node.node_type == "user_story":
            return self._draft_tests_from_story(parent_node)
        return []

    def _draft_requirements_from_epic(self, epic_node: TraceNode) -> List[Any]:
        """Create placeholder requirements from epic context.

        Real requirement extraction happens in the pipeline generators.
        This creates lightweight stubs for requirements that exist in
        the epic's parent_requirements but aren't linked yet.
        """
        # In the trace walker, existing artifacts are already linked.
        # This method handles the case where the epic references requirements
        # that don't exist yet — returns empty (they should already exist).
        return []

    def _draft_stories_from_requirement(self, req_node: TraceNode) -> List[Any]:
        """Create stub user stories from requirement context.

        Returns lightweight stubs that can be improved via LLM.
        """
        art = req_node.artifact
        req_title = getattr(art, "title", "") or ""
        req_desc = getattr(art, "description", "") or ""
        req_id = getattr(art, "requirement_id", "") or req_node.node_id

        # Try to import UserStory dataclass
        try:
            from requirements_engineer.generators.user_story_generator import (
                UserStory, AcceptanceCriterion
            )
        except ImportError:
            return []

        # Create one stub story per requirement
        story = UserStory(
            id=f"US-{req_id.split('-')[-1] if '-' in req_id else '001'}",
            title=f"User story for: {req_title}",
            persona="user",
            action=req_desc[:100] if req_desc else req_title,
            benefit="achieve the requirement goals",
            parent_requirement_id=req_id,
        )
        return [story]

    def _draft_tests_from_story(self, story_node: TraceNode) -> List[Any]:
        """Create stub test cases from user story context."""
        art = story_node.artifact
        story_id = getattr(art, "id", "") or story_node.node_id
        story_title = getattr(art, "title", "") or ""

        try:
            from requirements_engineer.generators.test_case_generator import (
                TestCase, TestStep
            )
        except ImportError:
            return []

        # Create one stub test per story
        tc = TestCase(
            id=f"TC-{story_id.split('-')[-1] if '-' in story_id else '001'}",
            title=f"Test: {story_title}",
            description=f"Verify that {story_title}",
            parent_user_story_id=story_id,
            steps=[
                TestStep(
                    step_type="When",
                    description=f"Execute the scenario: {story_title}",
                    expected_result="Expected behavior is observed",
                ),
            ],
        )
        return [tc]

    # ── Improve: Create better version via LLM ───────────────

    async def improve(self, node: TraceNode, issues: List[str]) -> Any:
        """Create an improved version of the artifact using LLM.

        Args:
            node: The trace node to improve.
            issues: Quality issues to address.

        Returns:
            Improved artifact (same type as node.artifact), or original if LLM unavailable.
        """
        if self._call_llm is None:
            return self._improve_programmatic(node, issues)

        parent_ctx = node.get_parent_context()
        issues_text = "\n".join(f"- {issue}" for issue in issues) if issues else "- General quality improvement needed"

        if node.node_type == "requirement":
            return await self._improve_requirement(node, parent_ctx, issues_text)
        elif node.node_type == "user_story":
            return await self._improve_user_story(node, parent_ctx, issues_text)
        elif node.node_type == "test_case":
            return await self._improve_test_case(node, parent_ctx, issues_text)

        return node.artifact

    async def _improve_requirement(self, node: TraceNode, parent_ctx: Dict, issues_text: str) -> Any:
        """Improve requirement via LLM."""
        art = node.artifact
        prompt = IMPROVE_REQUIREMENT_PROMPT.format(
            epic_title=parent_ctx.get("epic_title", "N/A"),
            epic_description=parent_ctx.get("epic_description", "N/A"),
            req_id=getattr(art, "requirement_id", node.node_id),
            req_title=getattr(art, "title", ""),
            req_description=getattr(art, "description", ""),
            req_criteria=str(getattr(art, "acceptance_criteria", [])),
            issues=issues_text,
        )

        response = await self._call_llm(prompt)
        self._llm_calls += 1
        data = _parse_json_response(response)
        if not data:
            return self._improve_programmatic(node, node.quality_issues)

        # Apply improvements to a copy
        improved = copy.deepcopy(art)
        if "title" in data:
            improved.title = data["title"]
        if "description" in data:
            improved.description = data["description"]
        if "acceptance_criteria" in data:
            improved.acceptance_criteria = data["acceptance_criteria"]
        improved.version = getattr(improved, "version", 0) + 1
        improved.stage_name = "improve"

        return improved

    async def _improve_user_story(self, node: TraceNode, parent_ctx: Dict, issues_text: str) -> Any:
        """Improve user story via LLM."""
        art = node.artifact
        story_criteria = getattr(art, "acceptance_criteria", [])
        criteria_str = "; ".join(
            f"Given {getattr(ac, 'given', '')}, When {getattr(ac, 'when', '')}, Then {getattr(ac, 'then', '')}"
            for ac in story_criteria
        ) if story_criteria else "None"

        prompt = IMPROVE_USER_STORY_PROMPT.format(
            req_id=parent_ctx.get("req_id", "N/A"),
            req_title=parent_ctx.get("req_title", ""),
            req_description=parent_ctx.get("req_description", ""),
            req_criteria=str(parent_ctx.get("req_acceptance_criteria", [])),
            story_id=getattr(art, "id", node.node_id),
            story_title=getattr(art, "title", ""),
            persona=getattr(art, "persona", ""),
            action=getattr(art, "action", ""),
            benefit=getattr(art, "benefit", ""),
            story_criteria=criteria_str,
            issues=issues_text,
        )

        response = await self._call_llm(prompt)
        self._llm_calls += 1
        data = _parse_json_response(response)
        if not data:
            return self._improve_programmatic(node, node.quality_issues)

        # Apply improvements to a copy
        improved = copy.deepcopy(art)
        if "title" in data:
            improved.title = data["title"]
        if "persona" in data:
            improved.persona = data["persona"]
        if "action" in data:
            improved.action = data["action"]
        if "benefit" in data:
            improved.benefit = data["benefit"]
        if "acceptance_criteria" in data and isinstance(data["acceptance_criteria"], list):
            try:
                from requirements_engineer.generators.user_story_generator import AcceptanceCriterion
                improved.acceptance_criteria = [
                    AcceptanceCriterion(
                        given=ac.get("given", ""),
                        when=ac.get("when", ""),
                        then=ac.get("then", ""),
                    )
                    for ac in data["acceptance_criteria"]
                    if isinstance(ac, dict)
                ]
            except ImportError:
                pass

        return improved

    async def _improve_test_case(self, node: TraceNode, parent_ctx: Dict, issues_text: str) -> Any:
        """Improve test case via LLM."""
        art = node.artifact
        steps = getattr(art, "steps", [])
        steps_str = "; ".join(
            f"Step {i+1}: {getattr(s, 'action', '')} → {getattr(s, 'expected_result', '')}"
            for i, s in enumerate(steps)
        ) if steps else "None"

        story_criteria = parent_ctx.get("story_acceptance_criteria", [])
        criteria_str = "; ".join(
            f"Given {ac.get('given', '')}, When {ac.get('when', '')}, Then {ac.get('then', '')}"
            for ac in story_criteria
        ) if story_criteria else "None"

        prompt = IMPROVE_TEST_CASE_PROMPT.format(
            story_id=parent_ctx.get("story_id", "N/A"),
            story_title=parent_ctx.get("story_title", ""),
            persona=parent_ctx.get("story_persona", ""),
            action=parent_ctx.get("story_action", ""),
            benefit=parent_ctx.get("story_benefit", ""),
            story_criteria=criteria_str,
            tc_id=getattr(art, "id", node.node_id),
            tc_title=getattr(art, "title", ""),
            tc_steps=steps_str,
            tc_expected=getattr(art, "expected_result", ""),
            issues=issues_text,
        )

        response = await self._call_llm(prompt)
        self._llm_calls += 1
        data = _parse_json_response(response)
        if not data:
            return self._improve_programmatic(node, node.quality_issues)

        # Apply improvements to a copy
        improved = copy.deepcopy(art)
        if "title" in data:
            improved.title = data["title"]
        if "description" in data:
            improved.description = data["description"]
        if "expected_result" in data:
            improved.expected_result = data["expected_result"]
        if "test_type" in data:
            improved.test_type = data["test_type"]
        if "steps" in data and isinstance(data["steps"], list):
            try:
                from requirements_engineer.generators.test_case_generator import TestStep
                improved.steps = [
                    TestStep(
                        step_type=s.get("step_type", "When"),
                        description=s.get("action", s.get("description", "")),
                        expected_result=s.get("expected_result", ""),
                    )
                    for i, s in enumerate(data["steps"])
                    if isinstance(s, dict)
                ]
            except ImportError:
                pass

        return improved

    # ── Debug: Fix structural issues ─────────────────────────

    async def debug(self, node: TraceNode, issues: List[str]) -> Any:
        """Fix structural issues in the artifact.

        Unlike improve (which creates a better version), debug fixes
        fundamental problems like missing required fields or broken links.
        """
        return self._improve_programmatic(node, issues)

    # ── Programmatic Improvement (no LLM) ────────────────────

    def _improve_programmatic(self, node: TraceNode, issues: List[str]) -> Any:
        """Apply rule-based fixes without LLM.

        Handles common issues:
        - Missing acceptance criteria → add placeholder
        - Empty description → derive from title
        - Missing persona → set default
        """
        art = copy.deepcopy(node.artifact)

        if node.node_type == "requirement":
            self._fix_requirement(art, issues)
        elif node.node_type == "user_story":
            self._fix_user_story(art, node, issues)
        elif node.node_type == "test_case":
            self._fix_test_case(art, node, issues)

        return art

    def _fix_requirement(self, art: Any, issues: List[str]):
        """Fix common requirement issues."""
        # Add description if empty
        title = getattr(art, "title", "") or ""
        desc = getattr(art, "description", "") or ""
        if not desc and title:
            art.description = f"The system shall implement {title.lower()}."

        # Add at least one acceptance criterion if none
        criteria = getattr(art, "acceptance_criteria", None)
        if criteria is not None and len(criteria) == 0:
            art.acceptance_criteria = [
                f"The {title.lower()} feature is functional and verified by test cases."
            ]

        # Update version
        if hasattr(art, "version"):
            art.version = getattr(art, "version", 0) + 1
        if hasattr(art, "stage_name"):
            art.stage_name = "debug"

    def _fix_user_story(self, art: Any, node: TraceNode, issues: List[str]):
        """Fix common user story issues."""
        # Fix empty persona
        if not getattr(art, "persona", ""):
            art.persona = "user"

        # Fix empty action
        if not getattr(art, "action", ""):
            parent_ctx = node.get_parent_context()
            req_title = parent_ctx.get("req_title", "use the system")
            art.action = req_title.lower()

        # Fix empty benefit
        if not getattr(art, "benefit", ""):
            art.benefit = "achieve the intended outcome"

    def _fix_test_case(self, art: Any, node: TraceNode, issues: List[str]):
        """Fix common test case issues."""
        # Add at least one step if empty
        steps = getattr(art, "steps", None)
        if steps is not None and len(steps) == 0:
            try:
                from requirements_engineer.generators.test_case_generator import TestStep
                title = getattr(art, "title", "the feature")
                art.steps = [
                    TestStep(
                        step_type="When",
                        description=f"Execute the scenario: {title}",
                        expected_result="Expected behavior is observed",
                    )
                ]
            except ImportError:
                pass

        # Add expected result if empty
        if not getattr(art, "expected_result", ""):
            art.expected_result = "The system behaves as specified in the user story."
