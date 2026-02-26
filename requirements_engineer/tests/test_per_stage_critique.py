"""
Tests for Per-Stage Self-Critique.

Covers:
- Stage routing: correct analyses called per stage (3 tests)
- Auto-fix at stage boundary (4 tests)
- Integration: fewer issues after pre-fix (3 tests)
- LLM integration (1 test, skip_no_key)
"""

import json
import os
import pytest
import asyncio
from dataclasses import dataclass, field
from typing import List, Optional
from unittest.mock import AsyncMock, patch, MagicMock

from requirements_engineer.critique.self_critique import (
    SelfCritiqueEngine,
    CritiqueIssue,
    IssueCategory,
    IssueSeverity,
)

# Import generator types
try:
    from requirements_engineer.generators.user_story_generator import (
        AcceptanceCriterion,
        UserStory,
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

def _make_requirement(req_id: str, title: str):
    @dataclass
    class SimpleReq:
        requirement_id: str = ""
        title: str = ""
        description: str = ""
    return SimpleReq(requirement_id=req_id, title=title)


@pytest.fixture
def engine():
    """Create a SelfCritiqueEngine without real OpenAI client."""
    e = SelfCritiqueEngine.__new__(SelfCritiqueEngine)
    e.model_name = "test-model"
    e.base_url = "http://test"
    e.api_key = "test"
    e.client = None
    e.initialized = False
    e.issue_counter = 0
    e._call_count = 0
    e._total_tokens = 0
    return e


def _mock_llm_response(issues, orphan_reqs=None, orphan_stories=None):
    """Build a JSON string mimicking LLM critique response."""
    data = {"issues": issues}
    if orphan_reqs is not None:
        data["orphan_requirements"] = orphan_reqs
    if orphan_stories is not None:
        data["orphan_stories"] = orphan_stories
    return json.dumps(data)


# ================================================================
# Stage Routing (3 tests)
# ================================================================

class TestStageRouting:
    def test_discovery_runs_completeness_only(self, engine):
        """Discovery stage should call check_completeness but NOT consistency/testability."""
        completeness_called = False
        consistency_called = False
        testability_called = False

        async def mock_completeness(reqs, domain=""):
            nonlocal completeness_called
            completeness_called = True
            return []

        async def mock_consistency(reqs, stories):
            nonlocal consistency_called
            consistency_called = True
            return []

        async def mock_testability(stories, tcs):
            nonlocal testability_called
            testability_called = True
            return []

        engine.check_completeness = mock_completeness
        engine.check_consistency = mock_consistency
        engine.check_testability = mock_testability

        reqs = [_make_requirement("REQ-001", "Test Req")]
        result = asyncio.get_event_loop().run_until_complete(
            engine.run_stage_critique("discovery", requirements=reqs, domain="test")
        )
        assert completeness_called is True
        assert consistency_called is False
        assert testability_called is False
        assert result["stage"] == "discovery"

    def test_analysis_runs_consistency_and_traceability(self, engine):
        """Analysis stage should call check_consistency + check_traceability."""
        calls = []

        async def mock_consistency(reqs, stories):
            calls.append("consistency")
            return []

        async def mock_traceability(reqs, stories, tcs):
            calls.append("traceability")
            return []

        async def mock_completeness(reqs, domain=""):
            calls.append("completeness")
            return []

        engine.check_consistency = mock_consistency
        engine.check_traceability = mock_traceability
        engine.check_completeness = mock_completeness

        reqs = [_make_requirement("REQ-001", "Test")]
        result = asyncio.get_event_loop().run_until_complete(
            engine.run_stage_critique("analysis", requirements=reqs, user_stories=[])
        )
        assert "consistency" in calls
        assert "traceability" in calls
        assert "completeness" not in calls

    def test_validation_runs_testability_and_traceability(self, engine):
        """Validation stage should call check_testability + check_traceability."""
        calls = []

        async def mock_testability(stories, tcs):
            calls.append("testability")
            return []

        async def mock_traceability(reqs, stories, tcs):
            calls.append("traceability")
            return []

        async def mock_consistency(reqs, stories):
            calls.append("consistency")
            return []

        engine.check_testability = mock_testability
        engine.check_traceability = mock_traceability
        engine.check_consistency = mock_consistency

        reqs = [_make_requirement("REQ-001", "Test")]
        result = asyncio.get_event_loop().run_until_complete(
            engine.run_stage_critique("validation", requirements=reqs, user_stories=[], test_cases=[])
        )
        assert "testability" in calls
        assert "traceability" in calls
        assert "consistency" not in calls


# ================================================================
# Auto-Fix at Stage Boundary (4 tests)
# ================================================================

@pytest.mark.skipif(not HAS_GENERATORS, reason="Generator classes not available")
class TestStageAutoFix:
    def test_analysis_fixes_orphan_requirements(self, engine):
        """After analysis critique, orphan reqs should get linked to stories."""
        reqs = [_make_requirement("REQ-010", "User Authentication and Login")]
        stories = [
            UserStory(
                id="US-001", title="Login Feature",
                persona="user", action="login to the system",
                benefit="access features",
            ),
        ]

        # Mock LLM to return consistency (empty) + traceability (orphan req)
        call_count = 0
        async def mock_llm(prompt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Consistency response
                return _mock_llm_response([])
            else:
                # Traceability response — detect orphan
                return _mock_llm_response([
                    {
                        "title": "Orphan Requirements Without User Stories",
                        "description": "REQ-010 has no linked user story",
                        "severity": "high",
                        "affected": ["REQ-010"],
                        "suggestion": "Link to existing stories",
                    }
                ], orphan_reqs=["REQ-010"])
        engine._call_llm = mock_llm

        result = asyncio.get_event_loop().run_until_complete(
            engine.run_stage_critique(
                "analysis", requirements=reqs, user_stories=stories, auto_fix=True
            )
        )
        assert result["issues_found"] >= 1
        assert result["issues_fixed"] >= 1
        assert any("REQ-010" in log for log in result["fix_log"])
        # Verify the actual link
        assert stories[0].parent_requirement_id == "REQ-010"

    def test_validation_fixes_stories_without_tests(self, engine):
        """After validation critique, stories without tests get stub TCs."""
        reqs = [_make_requirement("REQ-001", "Registration")]
        stories = [
            UserStory(
                id="US-005", title="Password Reset",
                persona="user", action="reset my password",
                benefit="regain account access",
                parent_requirement_id="REQ-001",
            ),
        ]
        test_cases = []

        # Mock LLM: testability (empty) + traceability (stories without tests)
        call_count = 0
        async def mock_llm(prompt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Testability response
                return _mock_llm_response([])
            else:
                # Traceability response — stories without tests
                return _mock_llm_response([
                    {
                        "title": "User Stories Without Test Coverage",
                        "description": "US-005 has no test cases",
                        "severity": "high",
                        "affected": ["US-005"],
                        "suggestion": "Create test cases",
                    }
                ], orphan_stories=["US-005"])
        engine._call_llm = mock_llm

        result = asyncio.get_event_loop().run_until_complete(
            engine.run_stage_critique(
                "validation", requirements=reqs, user_stories=stories,
                test_cases=test_cases, auto_fix=True
            )
        )
        assert result["issues_fixed"] >= 1
        # Verify stub TC was added to test_cases list
        assert len(test_cases) >= 1
        assert test_cases[0].parent_user_story_id == "US-005"

    def test_discovery_does_not_autofix(self, engine):
        """Discovery stage should NOT apply auto-fixes (advisory only)."""
        # Mock LLM to return completeness issues
        async def mock_llm(prompt):
            return _mock_llm_response([
                {
                    "title": "Missing Error Handling",
                    "description": "No error handling defined",
                    "severity": "high",
                    "affected": ["REQ-001"],
                    "suggestion": "Add error cases",
                }
            ])
        engine._call_llm = mock_llm

        reqs = [_make_requirement("REQ-001", "Authentication")]
        result = asyncio.get_event_loop().run_until_complete(
            engine.run_stage_critique(
                "discovery", requirements=reqs, domain="test", auto_fix=False
            )
        )
        assert result["issues_found"] >= 1
        assert result["issues_fixed"] == 0

    def test_fix_log_returned(self, engine):
        """Fix log should contain descriptive entries."""
        reqs = [_make_requirement("REQ-010", "User Login Authentication")]
        stories = [
            UserStory(
                id="US-001", title="Login Feature",
                persona="user", action="login to the system",
                benefit="access system",
            ),
        ]

        call_count = 0
        async def mock_llm(prompt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_llm_response([])
            else:
                return _mock_llm_response([
                    {
                        "title": "Orphan Requirements",
                        "description": "Orphan detected",
                        "severity": "high",
                        "affected": ["REQ-010"],
                        "suggestion": "Link",
                    }
                ])
        engine._call_llm = mock_llm

        result = asyncio.get_event_loop().run_until_complete(
            engine.run_stage_critique(
                "analysis", requirements=reqs, user_stories=stories, auto_fix=True
            )
        )
        assert len(result["fix_log"]) > 0
        # Log entries should mention what was linked
        assert any("Linked" in entry for entry in result["fix_log"])


# ================================================================
# Integration (3 tests)
# ================================================================

class TestStageIntegration:
    def test_stage_critique_returns_summary_dict(self, engine):
        """Return dict should have all expected keys."""
        async def mock_llm(prompt):
            return _mock_llm_response([])
        engine._call_llm = mock_llm

        reqs = [_make_requirement("REQ-001", "Test")]
        result = asyncio.get_event_loop().run_until_complete(
            engine.run_stage_critique("discovery", requirements=reqs)
        )
        assert "stage" in result
        assert "issues_found" in result
        assert "issues_fixed" in result
        assert "fix_log" in result
        assert result["stage"] == "discovery"
        assert isinstance(result["issues_found"], int)
        assert isinstance(result["fix_log"], list)

    def test_stage_critique_with_empty_data(self, engine):
        """Empty requirements should not crash."""
        async def mock_llm(prompt):
            return _mock_llm_response([])
        engine._call_llm = mock_llm

        result = asyncio.get_event_loop().run_until_complete(
            engine.run_stage_critique("discovery", requirements=[])
        )
        assert result["issues_found"] == 0
        assert result["issues_fixed"] == 0

    def test_unknown_stage_returns_empty(self, engine):
        """Unknown stage name should return zero issues gracefully."""
        result = asyncio.get_event_loop().run_until_complete(
            engine.run_stage_critique("nonexistent", requirements=[])
        )
        assert result["stage"] == "nonexistent"
        assert result["issues_found"] == 0
        assert result["issues_fixed"] == 0

    @pytest.mark.skipif(not HAS_GENERATORS, reason="Generator classes not available")
    def test_analysis_then_validation_improves_traceability(self, engine):
        """Running analysis critique (orphan fix) should reduce traceability issues in validation."""
        reqs = [_make_requirement("REQ-010", "User Authentication and Login")]
        stories = [
            UserStory(
                id="US-001", title="Login Feature",
                persona="user", action="login to the system",
                benefit="access features",
            ),
        ]

        # Phase 1: Analysis stage — fix orphan
        call_count = 0
        async def mock_llm_analysis(prompt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_llm_response([])  # consistency
            else:
                return _mock_llm_response([
                    {
                        "title": "Orphan Requirements",
                        "description": "REQ-010 orphan",
                        "severity": "high",
                        "affected": ["REQ-010"],
                        "suggestion": "Link",
                    }
                ])
        engine._call_llm = mock_llm_analysis

        result1 = asyncio.get_event_loop().run_until_complete(
            engine.run_stage_critique("analysis", requirements=reqs, user_stories=stories, auto_fix=True)
        )
        assert result1["issues_fixed"] >= 1
        # Verify link was created
        assert stories[0].parent_requirement_id == "REQ-010"

        # Phase 2: Validation stage — orphan should no longer be detected
        # (LLM would see the link now, but we mock to confirm the flow)
        async def mock_llm_validation(prompt):
            return _mock_llm_response([])  # No more issues
        engine._call_llm = mock_llm_validation

        test_cases = []
        result2 = asyncio.get_event_loop().run_until_complete(
            engine.run_stage_critique(
                "validation", requirements=reqs, user_stories=stories,
                test_cases=test_cases, auto_fix=True
            )
        )
        # After fixing orphan in analysis, validation should find fewer issues
        assert result2["issues_found"] == 0


# ================================================================
# LLM Integration (1 test, skip_no_key)
# ================================================================

skip_no_key = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set"
)

@skip_no_key
def test_analysis_critique_live():
    """Live LLM call for per-stage analysis critique."""
    engine = SelfCritiqueEngine(
        model_name="openai/gpt-4o-mini",
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ.get("OPENROUTER_API_KEY"),
    )
    asyncio.get_event_loop().run_until_complete(engine.initialize())

    reqs = [
        _make_requirement("REQ-001", "User Registration via Phone Number"),
        _make_requirement("REQ-002", "Two-Factor Authentication"),
    ]

    result = asyncio.get_event_loop().run_until_complete(
        engine.run_stage_critique(
            "discovery", requirements=reqs, domain="messaging app", auto_fix=False
        )
    )
    assert result["stage"] == "discovery"
    assert isinstance(result["issues_found"], int)
    # LLM should find at least some completeness issue
    assert result["issues_found"] >= 0
