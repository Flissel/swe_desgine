"""
Trace Evaluator - Parent-relative quality evaluation for trace nodes.

Unlike SelfCritiqueEngine (which evaluates artifacts in isolation), this evaluator
scores each artifact **relative to its trace parent**:
- Requirement vs Epic: Does it cover the epic's scope?
- UserStory vs Requirement: Does it capture all acceptance criteria?
- TestCase vs UserStory: Does it verify all acceptance criteria?

Uses programmatic checks first (fast, no LLM cost), with LLM fallback
when programmatic scoring is insufficient.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from .trace_node import TraceNode

log = logging.getLogger(__name__)

# Default evaluation weights per node type
DEFAULT_WEIGHTS = {
    "requirement": {
        "scope_coverage": 0.30,
        "clarity": 0.20,
        "feasibility": 0.20,
        "acceptance_quality": 0.30,
    },
    "user_story": {
        "criteria_coverage": 0.35,
        "persona_fit": 0.15,
        "action_completeness": 0.20,
        "testability": 0.30,
    },
    "test_case": {
        "criteria_verification": 0.35,
        "step_completeness": 0.25,
        "boundary_coverage": 0.20,
        "negative_paths": 0.20,
    },
}

# LLM prompt templates
REQUIREMENT_EVAL_PROMPT = """You are a Requirements Engineering expert.
Evaluate this REQUIREMENT against its parent EPIC for quality.

EPIC:
  Title: {epic_title}
  Description: {epic_description}

REQUIREMENT:
  ID: {req_id}
  Title: {req_title}
  Description: {req_description}
  Type: {req_type}
  Acceptance Criteria: {req_criteria}

Score each dimension 0.0-1.0:
- scope_coverage: Does this requirement fully address the relevant aspect of the epic?
- clarity: Is the requirement unambiguous and well-defined?
- feasibility: Is the requirement technically achievable?
- acceptance_quality: Are the acceptance criteria measurable and complete?

Also list any quality issues found.

Return JSON:
{{
    "scores": {{
        "scope_coverage": 0.0,
        "clarity": 0.0,
        "feasibility": 0.0,
        "acceptance_quality": 0.0
    }},
    "issues": ["issue 1", "issue 2"]
}}
Return ONLY valid JSON."""

USER_STORY_EVAL_PROMPT = """You are a Requirements Engineering expert.
Evaluate this USER STORY against its parent REQUIREMENT.

REQUIREMENT:
  ID: {req_id}
  Title: {req_title}
  Description: {req_description}
  Acceptance Criteria: {req_criteria}

USER STORY:
  ID: {story_id}
  Title: {story_title}
  As a {persona}, I want to {action}, so that {benefit}
  Acceptance Criteria: {story_criteria}

Score each dimension 0.0-1.0:
- criteria_coverage: Does the user story capture all requirement acceptance criteria?
- persona_fit: Is the persona appropriate for this requirement?
- action_completeness: Does the action fully describe what the user needs?
- testability: Are the story's acceptance criteria measurable (Given/When/Then)?

Also list any quality issues found.

Return JSON:
{{
    "scores": {{
        "criteria_coverage": 0.0,
        "persona_fit": 0.0,
        "action_completeness": 0.0,
        "testability": 0.0
    }},
    "issues": ["issue 1", "issue 2"]
}}
Return ONLY valid JSON."""

TEST_CASE_EVAL_PROMPT = """You are a QA Engineering expert.
Evaluate this TEST CASE against its parent USER STORY.

USER STORY:
  ID: {story_id}
  Title: {story_title}
  As a {persona}, I want to {action}, so that {benefit}
  Acceptance Criteria: {story_criteria}

TEST CASE:
  ID: {tc_id}
  Title: {tc_title}
  Description: {tc_description}
  Steps: {tc_steps}
  Expected Result: {tc_expected}

Score each dimension 0.0-1.0:
- criteria_verification: Does the test verify each acceptance criterion of the story?
- step_completeness: Are the test steps detailed enough to execute?
- boundary_coverage: Does the test include boundary/edge case checks?
- negative_paths: Does the test cover error cases and invalid inputs?

Also list any quality issues found.

Return JSON:
{{
    "scores": {{
        "criteria_verification": 0.0,
        "step_completeness": 0.0,
        "boundary_coverage": 0.0,
        "negative_paths": 0.0
    }},
    "issues": ["issue 1", "issue 2"]
}}
Return ONLY valid JSON."""


def _parse_json_response(text: str) -> Dict:
    """Parse JSON from LLM response, handling markdown fences."""
    text = text.strip()
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try markdown fence
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Try finding first { ... }
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start >= 0 and brace_end > brace_start:
        try:
            return json.loads(text[brace_start:brace_end + 1])
        except json.JSONDecodeError:
            pass
    return {"scores": {}, "issues": ["Failed to parse LLM response"]}


def _word_set(text: str) -> set:
    """Extract lowercase word set from text for overlap comparison."""
    return set(re.findall(r"[a-z]{3,}", text.lower()))


class TraceEvaluator:
    """Evaluates artifact quality relative to its trace parent.

    Uses programmatic checks for fast scoring, with optional LLM
    fallback for deeper semantic evaluation.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, llm_call=None):
        """Initialize evaluator.

        Args:
            config: Optional config with eval_weights overrides.
            llm_call: Async callable(prompt: str) -> str for LLM evaluation.
                      If None, only programmatic checks are used.
        """
        cfg = config or {}
        self.weights = cfg.get("eval_weights", DEFAULT_WEIGHTS)
        self._call_llm = llm_call
        self.llm_threshold = cfg.get("llm_threshold", 0.60)
        self._llm_calls = 0

    @property
    def llm_calls_used(self) -> int:
        return self._llm_calls

    async def evaluate(self, node: TraceNode) -> Dict[str, float]:
        """Score node quality relative to its trace parent.

        Returns dict of dimension_name -> score (0.0-1.0).
        """
        if node.node_type == "requirement":
            scores = await self._evaluate_requirement(node)
        elif node.node_type == "user_story":
            scores = await self._evaluate_user_story(node)
        elif node.node_type == "test_case":
            scores = await self._evaluate_test_case(node)
        elif node.node_type == "epic":
            # Epics are roots — no parent-relative evaluation
            scores = {"scope_coverage": 1.0}
        else:
            scores = {}

        node.dimension_scores = scores
        return scores

    async def evaluate_with_children(self, node: TraceNode) -> Dict[str, float]:
        """Re-evaluate a node considering its children's coverage.

        Checks whether children collectively cover the parent's scope.
        Returns updated scores dict with 'overall' key.
        """
        base_scores = dict(node.dimension_scores)

        if not node.children_trace:
            base_scores["children_coverage"] = 0.0
        else:
            complete_children = sum(1 for c in node.children_trace if c.is_complete)
            base_scores["children_coverage"] = complete_children / len(node.children_trace)

        # Overall = average of all dimensions
        all_vals = [v for v in base_scores.values() if isinstance(v, (int, float))]
        base_scores["overall"] = sum(all_vals) / max(len(all_vals), 1)

        return base_scores

    # ── Programmatic Evaluators ──────────────────────────────

    async def _evaluate_requirement(self, node: TraceNode) -> Dict[str, float]:
        """Evaluate requirement against its epic parent."""
        art = node.artifact
        parent_ctx = node.get_parent_context()
        issues = []

        # scope_coverage: keyword overlap between req description and epic description
        epic_desc = parent_ctx.get("epic_description", "")
        req_desc = getattr(art, "description", "") or ""
        req_title = getattr(art, "title", "") or ""

        if epic_desc and req_desc:
            epic_words = _word_set(epic_desc)
            req_words = _word_set(req_desc + " " + req_title)
            overlap = len(epic_words & req_words)
            scope_coverage = min(overlap / max(len(epic_words) * 0.3, 1), 1.0)
        else:
            scope_coverage = 0.5  # No parent context → neutral
            if not epic_desc:
                issues.append("No epic description for scope evaluation")

        # clarity: description length and acceptance criteria presence
        desc_len = len(req_desc.split())
        has_criteria = bool(getattr(art, "acceptance_criteria", []))
        clarity = 0.0
        if desc_len >= 20:
            clarity += 0.5
        elif desc_len >= 10:
            clarity += 0.3
        elif desc_len > 0:
            clarity += 0.1
        if has_criteria:
            clarity += 0.5
        else:
            issues.append("No acceptance criteria defined")

        # feasibility: check for concrete terms (not subjective)
        subjective_terms = {"fast", "easy", "simple", "user-friendly", "intuitive", "nice", "good", "best"}
        words_lower = set(req_desc.lower().split())
        subjective_count = len(subjective_terms & words_lower)
        feasibility = max(1.0 - subjective_count * 0.2, 0.0)
        if subjective_count > 0:
            issues.append(f"Subjective terms found: {subjective_terms & words_lower}")

        # acceptance_quality: count and quality of acceptance criteria
        criteria = getattr(art, "acceptance_criteria", []) or []
        if len(criteria) >= 3:
            acceptance_quality = 1.0
        elif len(criteria) >= 1:
            acceptance_quality = 0.5 + len(criteria) * 0.15
        else:
            acceptance_quality = 0.0
            issues.append("No acceptance criteria — untestable requirement")

        scores = {
            "scope_coverage": scope_coverage,
            "clarity": clarity,
            "feasibility": feasibility,
            "acceptance_quality": acceptance_quality,
        }

        # LLM fallback for low overall score
        overall = self._weighted_score(scores, "requirement")
        if overall < self.llm_threshold and self._call_llm is not None:
            llm_scores, llm_issues = await self._llm_evaluate_requirement(node, parent_ctx)
            if llm_scores:
                scores = llm_scores
                issues.extend(llm_issues)

        node.quality_issues = issues
        return scores

    async def _evaluate_user_story(self, node: TraceNode) -> Dict[str, float]:
        """Evaluate user story against its requirement parent."""
        art = node.artifact
        parent_ctx = node.get_parent_context()
        issues = []

        # criteria_coverage: how many req acceptance criteria are reflected in story
        req_criteria = parent_ctx.get("req_acceptance_criteria", [])
        story_criteria = getattr(art, "acceptance_criteria", []) or []

        if req_criteria and story_criteria:
            req_criteria_text = " ".join(str(c) for c in req_criteria).lower()
            story_criteria_text = " ".join(
                f"{getattr(ac, 'given', '')} {getattr(ac, 'when', '')} {getattr(ac, 'then', '')}"
                for ac in story_criteria
            ).lower()
            req_words = _word_set(req_criteria_text)
            story_words = _word_set(story_criteria_text)
            if req_words:
                overlap = len(req_words & story_words)
                criteria_coverage = min(overlap / max(len(req_words) * 0.4, 1), 1.0)
            else:
                criteria_coverage = 0.5
        elif not req_criteria:
            criteria_coverage = 0.5  # Parent has no criteria to check against
        else:
            criteria_coverage = 0.0
            issues.append("Story has no acceptance criteria")

        # persona_fit: persona should be non-empty and meaningful
        persona = getattr(art, "persona", "") or ""
        if len(persona) >= 3:
            persona_fit = 1.0
        elif persona:
            persona_fit = 0.5
            issues.append("Persona too vague")
        else:
            persona_fit = 0.0
            issues.append("No persona defined")

        # action_completeness: action + benefit should be non-trivial
        action = getattr(art, "action", "") or ""
        benefit = getattr(art, "benefit", "") or ""
        action_score = 0.0
        if len(action.split()) >= 5:
            action_score += 0.5
        elif action:
            action_score += 0.25
        else:
            issues.append("No action defined")
        if len(benefit.split()) >= 3:
            action_score += 0.5
        elif benefit:
            action_score += 0.25
        else:
            issues.append("No benefit defined")

        # testability: count GWT criteria (Given/When/Then format)
        gwt_count = 0
        for ac in story_criteria:
            given = getattr(ac, "given", "")
            when = getattr(ac, "when", "")
            then = getattr(ac, "then", "")
            if given and when and then:
                gwt_count += 1
        if story_criteria:
            testability = gwt_count / len(story_criteria)
        else:
            testability = 0.0
            issues.append("No acceptance criteria for testability check")

        scores = {
            "criteria_coverage": criteria_coverage,
            "persona_fit": persona_fit,
            "action_completeness": action_score,
            "testability": testability,
        }

        # LLM fallback
        overall = self._weighted_score(scores, "user_story")
        if overall < self.llm_threshold and self._call_llm is not None:
            llm_scores, llm_issues = await self._llm_evaluate_user_story(node, parent_ctx)
            if llm_scores:
                scores = llm_scores
                issues.extend(llm_issues)

        node.quality_issues = issues
        return scores

    async def _evaluate_test_case(self, node: TraceNode) -> Dict[str, float]:
        """Evaluate test case against its user story parent."""
        art = node.artifact
        parent_ctx = node.get_parent_context()
        issues = []

        # criteria_verification: TC steps reference story criteria keywords
        story_criteria = parent_ctx.get("story_acceptance_criteria", [])
        tc_steps = getattr(art, "steps", []) or []

        if story_criteria and tc_steps:
            criteria_words = set()
            for ac in story_criteria:
                for val in ac.values():
                    criteria_words |= _word_set(str(val))

            step_text = " ".join(
                f"{getattr(s, 'description', getattr(s, 'action', ''))} {getattr(s, 'expected_result', '')}"
                for s in tc_steps
            )
            step_words = _word_set(step_text)
            overlap = len(criteria_words & step_words)
            criteria_verification = min(overlap / max(len(criteria_words) * 0.3, 1), 1.0)
        elif not story_criteria:
            criteria_verification = 0.5  # Parent has no criteria
        else:
            criteria_verification = 0.0
            issues.append("Test case has no steps")

        # step_completeness: enough steps with actions + expected results
        complete_steps = 0
        for s in tc_steps:
            has_action = bool(getattr(s, "description", "") or getattr(s, "action", ""))
            has_expected = bool(getattr(s, "expected_result", ""))
            if has_action and has_expected:
                complete_steps += 1
        if tc_steps:
            step_completeness = complete_steps / len(tc_steps)
        else:
            step_completeness = 0.0
            issues.append("No test steps defined")

        # boundary_coverage: look for boundary-related keywords in steps
        boundary_keywords = {"boundary", "limit", "max", "min", "edge", "zero", "empty", "null", "overflow", "negative"}
        all_step_text = " ".join(
            str(getattr(s, "action", "")) + " " + str(getattr(s, "expected_result", ""))
            for s in tc_steps
        ).lower()
        boundary_hits = sum(1 for kw in boundary_keywords if kw in all_step_text)
        boundary_coverage = min(boundary_hits / 3.0, 1.0)  # 3+ boundary keywords = 1.0
        if boundary_hits == 0:
            issues.append("No boundary/edge case testing")

        # negative_paths: look for error/negative test keywords
        negative_keywords = {"error", "invalid", "fail", "reject", "unauthorized", "forbidden", "wrong", "incorrect", "missing"}
        tc_title = (getattr(art, "title", "") or "").lower()
        tc_desc = (getattr(art, "description", "") or "").lower()
        tc_type = (getattr(art, "test_type", "") or "").lower()
        full_text = f"{tc_title} {tc_desc} {tc_type} {all_step_text}"
        neg_hits = sum(1 for kw in negative_keywords if kw in full_text)
        negative_paths = min(neg_hits / 2.0, 1.0)  # 2+ negative keywords = 1.0

        scores = {
            "criteria_verification": criteria_verification,
            "step_completeness": step_completeness,
            "boundary_coverage": boundary_coverage,
            "negative_paths": negative_paths,
        }

        # LLM fallback
        overall = self._weighted_score(scores, "test_case")
        if overall < self.llm_threshold and self._call_llm is not None:
            llm_scores, llm_issues = await self._llm_evaluate_test_case(node, parent_ctx)
            if llm_scores:
                scores = llm_scores
                issues.extend(llm_issues)

        node.quality_issues = issues
        return scores

    # ── LLM Evaluation (fallback) ────────────────────────────

    async def _llm_evaluate_requirement(self, node: TraceNode, parent_ctx: Dict) -> tuple:
        """LLM-based evaluation for requirements."""
        art = node.artifact
        prompt = REQUIREMENT_EVAL_PROMPT.format(
            epic_title=parent_ctx.get("epic_title", "N/A"),
            epic_description=parent_ctx.get("epic_description", "N/A"),
            req_id=getattr(art, "requirement_id", node.node_id),
            req_title=getattr(art, "title", ""),
            req_description=getattr(art, "description", ""),
            req_type=getattr(art, "type", "functional"),
            req_criteria=str(getattr(art, "acceptance_criteria", [])),
        )
        return await self._run_llm_eval(prompt, "requirement")

    async def _llm_evaluate_user_story(self, node: TraceNode, parent_ctx: Dict) -> tuple:
        """LLM-based evaluation for user stories."""
        art = node.artifact
        story_criteria = getattr(art, "acceptance_criteria", [])
        criteria_str = "; ".join(
            f"Given {getattr(ac, 'given', '')}, When {getattr(ac, 'when', '')}, Then {getattr(ac, 'then', '')}"
            for ac in story_criteria
        ) if story_criteria else "None"

        prompt = USER_STORY_EVAL_PROMPT.format(
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
        )
        return await self._run_llm_eval(prompt, "user_story")

    async def _llm_evaluate_test_case(self, node: TraceNode, parent_ctx: Dict) -> tuple:
        """LLM-based evaluation for test cases."""
        art = node.artifact
        steps = getattr(art, "steps", [])
        steps_str = "; ".join(
            f"Step {i+1}: {getattr(s, 'description', getattr(s, 'action', ''))} → {getattr(s, 'expected_result', '')}"
            for i, s in enumerate(steps)
        ) if steps else "None"

        story_criteria = parent_ctx.get("story_acceptance_criteria", [])
        criteria_str = "; ".join(
            f"Given {ac.get('given', '')}, When {ac.get('when', '')}, Then {ac.get('then', '')}"
            for ac in story_criteria
        ) if story_criteria else "None"

        prompt = TEST_CASE_EVAL_PROMPT.format(
            story_id=parent_ctx.get("story_id", "N/A"),
            story_title=parent_ctx.get("story_title", ""),
            persona=parent_ctx.get("story_persona", ""),
            action=parent_ctx.get("story_action", ""),
            benefit=parent_ctx.get("story_benefit", ""),
            story_criteria=criteria_str,
            tc_id=getattr(art, "id", node.node_id),
            tc_title=getattr(art, "title", ""),
            tc_description=getattr(art, "description", ""),
            tc_steps=steps_str,
            tc_expected=getattr(art, "expected_result", ""),
        )
        return await self._run_llm_eval(prompt, "test_case")

    async def _run_llm_eval(self, prompt: str, node_type: str) -> tuple:
        """Execute LLM evaluation and parse response."""
        try:
            response = await self._call_llm(prompt)
            self._llm_calls += 1
            data = _parse_json_response(response)
            scores = data.get("scores", {})
            issues = data.get("issues", [])

            # Validate scores are in expected dimensions
            expected_dims = set(self.weights.get(node_type, {}).keys())
            valid_scores = {k: max(0.0, min(float(v), 1.0)) for k, v in scores.items() if k in expected_dims}

            if len(valid_scores) == len(expected_dims):
                return valid_scores, issues
            else:
                log.warning(f"LLM returned incomplete scores for {node_type}: {scores}")
                return None, issues
        except Exception as e:
            log.warning(f"LLM evaluation failed for {node_type}: {e}")
            return None, [f"LLM evaluation error: {e}"]

    # ── Scoring Helpers ──────────────────────────────────────

    def _weighted_score(self, scores: Dict[str, float], node_type: str) -> float:
        """Calculate weighted average from dimension scores."""
        weights = self.weights.get(node_type, {})
        if not weights or not scores:
            return sum(scores.values()) / max(len(scores), 1) if scores else 0.0

        total = 0.0
        weight_sum = 0.0
        for dim, weight in weights.items():
            if dim in scores:
                total += scores[dim] * weight
                weight_sum += weight

        return total / max(weight_sum, 0.001)

    def aggregate_score(self, scores: Dict[str, float], node_type: str) -> float:
        """Public method to aggregate dimension scores into overall score."""
        return self._weighted_score(scores, node_type)
