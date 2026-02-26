"""
Tests for Epic-Rooted Iterative Tree Search (Trace Walker).

Covers:
- TraceNode: creation, tree building, version tracking (3 tests)
- TraceEvaluator: parent-relative scoring (5 tests)
- TraceExpander: draft/improve/debug (4 tests)
- TraceWalker: DFS walk, refinement, termination (6 tests)
- Integration: traceability improvement, LLM live (2 tests)
"""

import asyncio
import json
import os
import pytest
from dataclasses import dataclass, field
from typing import List, Optional
from unittest.mock import AsyncMock

from requirements_engineer.treesearch.trace_node import (
    TraceNode,
    TraceWalkResult,
    NODE_TYPES,
)
from requirements_engineer.treesearch.trace_evaluator import TraceEvaluator
from requirements_engineer.treesearch.trace_expander import TraceExpander
from requirements_engineer.treesearch.trace_walker import TraceWalker

# Import generator types
try:
    from requirements_engineer.generators.user_story_generator import (
        AcceptanceCriterion,
        UserStory,
        Epic,
    )
    from requirements_engineer.generators.test_case_generator import (
        TestCase,
        TestStep,
    )
    HAS_GENERATORS = True
except ImportError:
    HAS_GENERATORS = False


# ================================================================
# Helpers
# ================================================================

@dataclass
class SimpleReq:
    requirement_id: str = ""
    title: str = ""
    description: str = ""
    type: str = "functional"
    priority: str = "should"
    acceptance_criteria: List[str] = field(default_factory=list)
    version: int = 1
    parent_version_id: Optional[str] = None
    children_version_ids: object = field(default_factory=set)
    stage_name: str = "draft"
    quality_issues: List[str] = field(default_factory=list)
    is_buggy: bool = False


@dataclass
class SimpleEpic:
    id: str = ""
    title: str = ""
    description: str = ""
    parent_requirements: List[str] = field(default_factory=list)
    user_stories: List[str] = field(default_factory=list)
    status: str = "draft"


@dataclass
class SimpleStory:
    id: str = ""
    title: str = ""
    persona: str = ""
    action: str = ""
    benefit: str = ""
    acceptance_criteria: list = field(default_factory=list)
    parent_requirement_id: str = ""
    parent_epic_id: str = ""


@dataclass
class SimpleCriterion:
    given: str = ""
    when: str = ""
    then: str = ""


@dataclass
class SimpleTC:
    id: str = ""
    title: str = ""
    description: str = ""
    steps: list = field(default_factory=list)
    expected_result: str = ""
    test_type: str = "functional"
    parent_user_story_id: str = ""
    parent_requirement_id: str = ""


@dataclass
class SimpleStep:
    step_type: str = "When"
    description: str = ""
    expected_result: str = ""


def _run(coro):
    """Run async coroutine in sync context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ================================================================
# TraceNode Tests (3 tests)
# ================================================================

class TestTraceNode:
    def test_trace_node_creation(self):
        """Wrapping a requirement in TraceNode should work."""
        req = SimpleReq(requirement_id="REQ-001", title="Login")
        node = TraceNode(node_id="REQ-001", node_type="requirement", artifact=req)
        assert node.node_id == "REQ-001"
        assert node.node_type == "requirement"
        assert node.artifact is req
        assert node.depth == 0
        assert node.is_leaf is True
        assert len(node.versions) == 1  # Initial artifact stored as v0
        assert node.trace_path == ["REQ-001"]

    def test_trace_tree_building(self):
        """Build Epic → REQ → US → TC tree and verify structure."""
        epic = SimpleEpic(id="EPIC-001", title="Auth", parent_requirements=["REQ-001"])
        epic_node = TraceNode(node_id="EPIC-001", node_type="epic", artifact=epic)

        req = SimpleReq(requirement_id="REQ-001", title="Login")
        req_node = TraceNode(node_id="REQ-001", node_type="requirement",
                             artifact=req, parent_trace=epic_node)
        epic_node.children_trace.append(req_node)

        story = SimpleStory(id="US-001", parent_requirement_id="REQ-001")
        story_node = TraceNode(node_id="US-001", node_type="user_story",
                               artifact=story, parent_trace=req_node)
        req_node.children_trace.append(story_node)

        tc = SimpleTC(id="TC-001", parent_user_story_id="US-001")
        tc_node = TraceNode(node_id="TC-001", node_type="test_case",
                            artifact=tc, parent_trace=story_node)
        story_node.children_trace.append(tc_node)

        assert epic_node.depth == 0
        assert req_node.depth == 1
        assert story_node.depth == 2
        assert tc_node.depth == 3
        assert tc_node.trace_path == ["EPIC-001", "REQ-001", "US-001", "TC-001"]
        assert tc_node.is_leaf is True
        assert req_node.is_leaf is False

    def test_version_tracking(self):
        """Recording refinements should grow the versions list."""
        req = SimpleReq(requirement_id="REQ-001", title="Login")
        node = TraceNode(node_id="REQ-001", node_type="requirement", artifact=req)
        assert len(node.versions) == 1

        # Simulate a refinement
        improved_req = SimpleReq(requirement_id="REQ-001", title="Improved Login")
        node.record_refinement(improved_req, "improve", 0.5, 0.75)
        assert len(node.versions) == 2
        assert node.current_version == 1
        assert node.artifact is improved_req
        assert node.iteration_count == 1
        assert len(node.refinement_log) == 1
        assert "improve" in node.refinement_log[0]


# ================================================================
# TraceEvaluator Tests (5 tests)
# ================================================================

class TestTraceEvaluator:
    def test_requirement_vs_epic_scoring(self):
        """Requirement evaluation against epic should produce dimension scores."""
        evaluator = TraceEvaluator()

        epic = SimpleEpic(
            id="EPIC-001", title="User Authentication",
            description="The system must support secure user authentication including login, registration, and password recovery."
        )
        epic_node = TraceNode(node_id="EPIC-001", node_type="epic", artifact=epic)

        req = SimpleReq(
            requirement_id="REQ-001",
            title="User Login Authentication",
            description="The system shall provide secure login authentication with username and password for registered users.",
            acceptance_criteria=[
                "Users can login with valid credentials",
                "Invalid credentials show error message",
                "Account locks after 5 failed attempts",
            ],
        )
        req_node = TraceNode(node_id="REQ-001", node_type="requirement",
                             artifact=req, parent_trace=epic_node)

        scores = _run(evaluator.evaluate(req_node))
        assert "scope_coverage" in scores
        assert "clarity" in scores
        assert "feasibility" in scores
        assert "acceptance_quality" in scores
        # 3 acceptance criteria → acceptance_quality should be 1.0
        assert scores["acceptance_quality"] == 1.0
        # Description has 15+ words → clarity should be decent
        assert scores["clarity"] >= 0.5

    def test_story_vs_requirement_criteria_coverage(self):
        """User story evaluation should check criteria coverage against requirement."""
        evaluator = TraceEvaluator()

        req = SimpleReq(
            requirement_id="REQ-001",
            title="User Login",
            description="The system shall support user login.",
            acceptance_criteria=["Users can login with valid credentials"],
        )
        req_node = TraceNode(node_id="REQ-001", node_type="requirement", artifact=req)

        story = SimpleStory(
            id="US-001", title="Login Feature",
            persona="registered user",
            action="login to the system with my username and password",
            benefit="access my personalized dashboard",
            acceptance_criteria=[
                SimpleCriterion(
                    given="a registered user with valid credentials",
                    when="the user submits login form",
                    then="the user is authenticated and redirected",
                ),
            ],
            parent_requirement_id="REQ-001",
        )
        story_node = TraceNode(node_id="US-001", node_type="user_story",
                               artifact=story, parent_trace=req_node)

        scores = _run(evaluator.evaluate(story_node))
        assert "criteria_coverage" in scores
        assert "persona_fit" in scores
        assert "testability" in scores
        # Has persona → persona_fit should be 1.0
        assert scores["persona_fit"] == 1.0
        # Has 1 complete GWT → testability = 1.0
        assert scores["testability"] == 1.0

    def test_test_vs_story_criteria_verification(self):
        """Test case evaluation should check step coverage against story criteria."""
        evaluator = TraceEvaluator()

        story = SimpleStory(
            id="US-001", title="Login Feature",
            persona="user", action="login", benefit="access system",
            acceptance_criteria=[
                SimpleCriterion(given="valid credentials", when="submit login", then="authenticated"),
            ],
        )
        story_node = TraceNode(node_id="US-001", node_type="user_story", artifact=story)

        tc = SimpleTC(
            id="TC-001", title="Test Login with Valid Credentials",
            description="Verify login with valid credentials works",
            steps=[
                SimpleStep(step_type="Given", description="a user with valid credentials exists", expected_result="user in database"),
                SimpleStep(step_type="When", description="user submits login form with credentials", expected_result="form submitted"),
                SimpleStep(step_type="Then", description="user is authenticated and redirected", expected_result="redirect to dashboard"),
            ],
            expected_result="User successfully authenticated",
            parent_user_story_id="US-001",
        )
        tc_node = TraceNode(node_id="TC-001", node_type="test_case",
                            artifact=tc, parent_trace=story_node)

        scores = _run(evaluator.evaluate(tc_node))
        assert "criteria_verification" in scores
        assert "step_completeness" in scores
        # 3 steps all have action + expected → step_completeness = 1.0
        assert scores["step_completeness"] == 1.0

    def test_llm_fallback_for_low_scores(self):
        """LLM should be called when programmatic scores are below threshold."""
        call_count = 0

        async def mock_llm(prompt):
            nonlocal call_count
            call_count += 1
            return json.dumps({
                "scores": {
                    "scope_coverage": 0.90,
                    "clarity": 0.85,
                    "feasibility": 0.80,
                    "acceptance_quality": 0.75,
                },
                "issues": ["LLM found issue"],
            })

        evaluator = TraceEvaluator(
            config={"llm_threshold": 0.99},  # Force LLM fallback
            llm_call=mock_llm,
        )

        epic = SimpleEpic(id="EPIC-001", title="Auth", description="Authentication system")
        epic_node = TraceNode(node_id="EPIC-001", node_type="epic", artifact=epic)

        req = SimpleReq(requirement_id="REQ-001", title="Login", description="Short desc")
        req_node = TraceNode(node_id="REQ-001", node_type="requirement",
                             artifact=req, parent_trace=epic_node)

        scores = _run(evaluator.evaluate(req_node))
        assert call_count == 1  # LLM was called
        assert scores["scope_coverage"] == 0.90
        assert "LLM found issue" in req_node.quality_issues

    def test_evaluation_returns_all_dimensions(self):
        """Evaluation should return all expected dimension keys."""
        evaluator = TraceEvaluator()

        epic = SimpleEpic(id="EPIC-001", description="System")
        epic_node = TraceNode(node_id="EPIC-001", node_type="epic", artifact=epic)
        req = SimpleReq(requirement_id="REQ-001", title="Test")
        req_node = TraceNode(node_id="REQ-001", node_type="requirement",
                             artifact=req, parent_trace=epic_node)

        scores = _run(evaluator.evaluate(req_node))
        expected_dims = {"scope_coverage", "clarity", "feasibility", "acceptance_quality"}
        assert set(scores.keys()) == expected_dims


# ================================================================
# TraceExpander Tests (4 tests)
# ================================================================

class TestTraceExpander:
    @pytest.mark.skipif(not HAS_GENERATORS, reason="Generator classes not available")
    def test_draft_stories_from_requirement(self):
        """Drafting children from requirement should produce UserStory stubs."""
        expander = TraceExpander()
        req = SimpleReq(
            requirement_id="REQ-005",
            title="User Registration",
            description="The system must allow new users to register with email and password.",
        )
        req_node = TraceNode(node_id="REQ-005", node_type="requirement", artifact=req)

        children = _run(expander.draft(req_node))
        assert len(children) >= 1
        assert hasattr(children[0], "parent_requirement_id")
        assert children[0].parent_requirement_id == "REQ-005"

    def test_improve_requirement_with_issues(self):
        """Improving a requirement should create a new version with fixes."""
        async def mock_llm(prompt):
            return json.dumps({
                "title": "Secure User Login Authentication",
                "description": "The system shall provide secure user login with encrypted password storage and multi-factor authentication support for all registered users.",
                "acceptance_criteria": [
                    "Users can login with valid username and password",
                    "Passwords are encrypted with bcrypt",
                    "Account locks after 5 consecutive failed login attempts",
                ],
            })

        expander = TraceExpander(llm_call=mock_llm)
        req = SimpleReq(
            requirement_id="REQ-001",
            title="Login",
            description="Login feature",
        )
        epic = SimpleEpic(id="EPIC-001", title="Auth", description="Authentication")
        epic_node = TraceNode(node_id="EPIC-001", node_type="epic", artifact=epic)
        req_node = TraceNode(node_id="REQ-001", node_type="requirement",
                             artifact=req, parent_trace=epic_node)

        improved = _run(expander.improve(req_node, ["Description too short", "No acceptance criteria"]))
        assert improved.title == "Secure User Login Authentication"
        assert len(improved.acceptance_criteria) == 3
        assert "bcrypt" in improved.acceptance_criteria[1]

    def test_debug_fixes_structural_issues(self):
        """Debug should fix missing fields without LLM."""
        expander = TraceExpander()
        req = SimpleReq(requirement_id="REQ-001", title="Registration")
        req_node = TraceNode(node_id="REQ-001", node_type="requirement", artifact=req)

        fixed = _run(expander.debug(req_node, ["Empty description", "No acceptance criteria"]))
        # Description should be populated
        assert len(fixed.description) > 0
        # Acceptance criteria should have at least one entry
        assert len(fixed.acceptance_criteria) >= 1

    def test_improve_preserves_existing_fields(self):
        """Improvement should not lose existing data."""
        async def mock_llm(prompt):
            return json.dumps({
                "title": "Better Title",
                "description": "Better description for the login feature with detailed requirements.",
                "acceptance_criteria": ["New criterion 1", "New criterion 2"],
            })

        expander = TraceExpander(llm_call=mock_llm)
        req = SimpleReq(
            requirement_id="REQ-001",
            title="Login",
            description="Old description",
            type="functional",
            priority="must",
        )
        epic = SimpleEpic(id="EPIC-001", description="Auth")
        epic_node = TraceNode(node_id="EPIC-001", node_type="epic", artifact=epic)
        req_node = TraceNode(node_id="REQ-001", node_type="requirement",
                             artifact=req, parent_trace=epic_node)

        improved = _run(expander.improve(req_node, ["Short description"]))
        # Updated fields
        assert improved.title == "Better Title"
        # Preserved fields
        assert improved.requirement_id == "REQ-001"
        assert improved.type == "functional"
        assert improved.priority == "must"


# ================================================================
# TraceWalker Tests (6 tests)
# ================================================================

class TestTraceWalker:
    def test_walk_single_epic_all_levels(self):
        """Walking an epic with full trace should visit all nodes."""
        walker = TraceWalker(config={"quality_threshold": 0.01})  # Low threshold → all pass

        epic = SimpleEpic(
            id="EPIC-001", title="Auth",
            description="User authentication system with login and registration",
            parent_requirements=["REQ-001"],
        )
        req = SimpleReq(
            requirement_id="REQ-001",
            title="User Login",
            description="The system shall provide secure user login authentication for registered users.",
            acceptance_criteria=["Users can login", "Invalid creds show error", "Account locks after 5 fails"],
        )
        story = SimpleStory(
            id="US-001", title="Login Feature",
            persona="registered user",
            action="login to the system",
            benefit="access my account",
            acceptance_criteria=[
                SimpleCriterion(given="valid creds", when="submit login", then="authenticated"),
            ],
            parent_requirement_id="REQ-001",
        )
        tc = SimpleTC(
            id="TC-001", title="Test Login",
            description="Verify login",
            steps=[
                SimpleStep(step_type="When", description="login with valid creds", expected_result="success"),
            ],
            expected_result="Authenticated",
            parent_user_story_id="US-001",
        )

        result = _run(walker.walk_epic(epic, {
            "requirements": [req],
            "user_stories": [story],
            "test_cases": [tc],
        }))
        assert result.epic_id == "EPIC-001"
        assert result.nodes_total == 3  # REQ + US + TC (epic excluded)
        assert result.avg_quality > 0
        assert len(result.node_summaries) == 3

    def test_refinement_loop_stops_at_threshold(self):
        """Once quality meets threshold, refinement should stop."""
        walker = TraceWalker(config={
            "quality_threshold": 0.50,  # Easy to reach
            "max_iterations_per_node": 5,
        })

        epic = SimpleEpic(
            id="EPIC-001", title="Auth",
            description="Authentication system with login features",
            parent_requirements=["REQ-001"],
        )
        req = SimpleReq(
            requirement_id="REQ-001",
            title="Login Authentication System",
            description="The system shall provide secure login authentication with username and password validation for all registered users.",
            acceptance_criteria=["Users can login", "Error on invalid creds", "Lockout after failures"],
        )

        result = _run(walker.walk_epic(epic, {
            "requirements": [req],
            "user_stories": [],
            "test_cases": [],
        }))
        # With good data and low threshold, should be complete without refinement
        req_summary = result.node_summaries[0]
        assert req_summary["quality_score"] >= 0.50

    def test_refinement_loop_stops_at_max_iterations(self):
        """Refinement should not exceed max_iterations."""
        walker = TraceWalker(config={
            "quality_threshold": 0.99,  # Almost unreachable
            "max_iterations_per_node": 2,
            "requirement": {"quality_threshold": 0.99, "max_iterations": 2},
        })

        epic = SimpleEpic(
            id="EPIC-001", title="Auth",
            description="Authentication",
            parent_requirements=["REQ-001"],
        )
        req = SimpleReq(requirement_id="REQ-001", title="Login")

        result = _run(walker.walk_epic(epic, {
            "requirements": [req],
            "user_stories": [],
            "test_cases": [],
        }))
        req_summary = result.node_summaries[0]
        assert req_summary["iterations"] <= 2

    def test_parent_reevaluated_after_children(self):
        """Parent should be re-evaluated after children are processed."""
        walker = TraceWalker(config={"quality_threshold": 0.01})

        epic = SimpleEpic(
            id="EPIC-001", title="Auth",
            description="Authentication system with comprehensive login and security features",
            parent_requirements=["REQ-001"],
        )
        req = SimpleReq(
            requirement_id="REQ-001",
            title="Login Authentication",
            description="The system shall provide login authentication with secure validation for all users.",
            acceptance_criteria=["Users can login", "Error handling"],
        )
        story = SimpleStory(
            id="US-001", title="Login Feature",
            persona="user", action="login", benefit="access",
            acceptance_criteria=[SimpleCriterion(given="creds", when="login", then="auth")],
            parent_requirement_id="REQ-001",
        )

        result = _run(walker.walk_epic(epic, {
            "requirements": [req],
            "user_stories": [story],
            "test_cases": [],
        }))
        # Should have visited requirement and story
        assert result.nodes_total >= 2

    def test_walk_with_existing_artifacts(self):
        """Walk should handle existing linked artifacts without crashing."""
        walker = TraceWalker(config={"quality_threshold": 0.01})

        epic = SimpleEpic(
            id="EPIC-001", title="E-Commerce",
            description="E-commerce platform with shopping cart and checkout and payment processing",
            parent_requirements=["REQ-001", "REQ-002"],
        )
        reqs = [
            SimpleReq(requirement_id="REQ-001", title="Shopping Cart",
                      description="The system shall allow users to add items to a shopping cart.",
                      acceptance_criteria=["Add item to cart"]),
            SimpleReq(requirement_id="REQ-002", title="Checkout",
                      description="The system shall process checkout with payment validation.",
                      acceptance_criteria=["Process payment"]),
        ]
        stories = [
            SimpleStory(id="US-001", title="Add to Cart",
                        persona="shopper", action="add item to cart", benefit="purchase later",
                        acceptance_criteria=[SimpleCriterion(given="item", when="add", then="in cart")],
                        parent_requirement_id="REQ-001"),
            SimpleStory(id="US-002", title="Checkout Flow",
                        persona="shopper", action="checkout my cart", benefit="receive items",
                        acceptance_criteria=[SimpleCriterion(given="cart items", when="checkout", then="order placed")],
                        parent_requirement_id="REQ-002"),
        ]
        tcs = [
            SimpleTC(id="TC-001", title="Test Add to Cart",
                     steps=[SimpleStep(description="add item", expected_result="item added")],
                     parent_user_story_id="US-001"),
        ]

        result = _run(walker.walk_epic(epic, {
            "requirements": reqs,
            "user_stories": stories,
            "test_cases": tcs,
        }))
        # 2 reqs + 2 stories + 1 existing tc + 1 drafted stub tc = 6 nodes
        assert result.nodes_total == 6
        assert result.avg_quality > 0

    def test_walk_result_audit_trail(self):
        """Walk result should contain per-node summary with expected keys."""
        walker = TraceWalker(config={"quality_threshold": 0.01})

        epic = SimpleEpic(
            id="EPIC-001", title="Auth",
            description="Authentication features for user login",
            parent_requirements=["REQ-001"],
        )
        req = SimpleReq(
            requirement_id="REQ-001", title="Login",
            description="The system shall support user login with credentials validation.",
            acceptance_criteria=["Login works"],
        )

        result = _run(walker.walk_epic(epic, {
            "requirements": [req],
            "user_stories": [],
            "test_cases": [],
        }))
        assert len(result.node_summaries) >= 1
        summary = result.node_summaries[0]
        assert "node_id" in summary
        assert "node_type" in summary
        assert "quality_score" in summary
        assert "iterations" in summary
        assert "is_complete" in summary
        assert "dimension_scores" in summary


# ================================================================
# Integration Tests (2 tests)
# ================================================================

class TestIntegration:
    def test_walk_produces_quality_scores(self):
        """After walk, all nodes should have quality scores > 0."""
        walker = TraceWalker(config={"quality_threshold": 0.01})

        epic = SimpleEpic(
            id="EPIC-001", title="User Management",
            description="Complete user management with registration, login, profile editing, and password recovery",
            parent_requirements=["REQ-001"],
        )
        req = SimpleReq(
            requirement_id="REQ-001",
            title="User Registration",
            description="The system shall allow new users to register with email address and password.",
            acceptance_criteria=[
                "Users can register with email and password",
                "Email must be unique",
                "Password must meet complexity requirements",
            ],
        )
        story = SimpleStory(
            id="US-001", title="User Registration Flow",
            persona="new user",
            action="register for an account with my email and a secure password",
            benefit="access the platform features",
            acceptance_criteria=[
                SimpleCriterion(
                    given="a new user on the registration page",
                    when="the user fills in email and password and submits",
                    then="the account is created and confirmation email sent",
                ),
            ],
            parent_requirement_id="REQ-001",
        )
        tc = SimpleTC(
            id="TC-001",
            title="Test User Registration with Valid Data",
            description="Verify new user can register",
            steps=[
                SimpleStep(step_type="Given", description="user is on registration page", expected_result="page loaded"),
                SimpleStep(step_type="When", description="user enters valid email and password", expected_result="form filled"),
                SimpleStep(step_type="Then", description="account is created successfully", expected_result="redirect to dashboard"),
            ],
            expected_result="User registered successfully",
            parent_user_story_id="US-001",
        )

        result = _run(walker.walk_epic(epic, {
            "requirements": [req],
            "user_stories": [story],
            "test_cases": [tc],
        }))
        assert result.nodes_total == 3
        assert result.avg_quality > 0
        assert all(ns["quality_score"] > 0 for ns in result.node_summaries)

    def test_walk_result_markdown(self):
        """Walk result should produce valid markdown."""
        result = TraceWalkResult(
            epic_id="EPIC-001",
            epic_title="Authentication",
            nodes_total=5,
            nodes_refined=2,
            nodes_complete=4,
            avg_quality=0.82,
            llm_calls_used=3,
            duration_seconds=1.5,
            node_summaries=[
                {"node_id": "REQ-001", "node_type": "requirement",
                 "quality_score": 0.85, "iterations": 1, "is_complete": True},
                {"node_id": "US-001", "node_type": "user_story",
                 "quality_score": 0.78, "iterations": 0, "is_complete": True},
            ],
        )
        md = result.to_markdown()
        assert "EPIC-001" in md
        assert "Authentication" in md
        assert "5" in md  # nodes_total
        assert "REQ-001" in md
        assert "US-001" in md


# ================================================================
# LLM Integration (1 test, skip_no_key)
# ================================================================

skip_no_key = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set"
)

@skip_no_key
def test_trace_walk_live():
    """Live LLM call for trace walk evaluation and improvement."""
    import openai

    client = openai.AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ.get("OPENROUTER_API_KEY"),
    )

    async def llm_call(prompt: str) -> str:
        resp = await client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a Requirements Engineering expert. Return valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=2000,
        )
        return resp.choices[0].message.content or ""

    walker = TraceWalker(
        config={
            "quality_threshold": 0.70,
            "max_iterations_per_node": 1,
            "max_total_llm_calls": 5,
        },
        llm_call=llm_call,
    )

    epic = SimpleEpic(
        id="EPIC-001", title="User Authentication",
        description="Secure authentication system with login, registration, and password recovery.",
        parent_requirements=["REQ-001"],
    )
    req = SimpleReq(
        requirement_id="REQ-001",
        title="User Login",
        description="Allow users to log in.",  # Intentionally short
    )

    result = _run(walker.walk_epic(epic, {
        "requirements": [req],
        "user_stories": [],
        "test_cases": [],
    }))
    assert result.epic_id == "EPIC-001"
    assert result.nodes_total >= 1
    assert result.avg_quality > 0
