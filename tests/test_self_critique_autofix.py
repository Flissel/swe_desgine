"""
Tests for Self-Critique Auto-Fix System.

Tests cover:
- Fix classification (4 tests)
- Programmatic fixers: orphan reqs + stub test cases (5 tests)
- Score & integration (4 tests)
- LLM integration (1 test, skip_no_key)
"""

import json
import os
import pytest
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional
from unittest.mock import AsyncMock, patch, MagicMock

from requirements_engineer.critique.self_critique import (
    SelfCritiqueEngine,
    CritiqueIssue,
    CritiqueResult,
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
# Helpers: create test data
# ================================================================

def _make_issue(
    issue_id: str,
    category: IssueCategory,
    severity: IssueSeverity,
    title: str,
    affected: Optional[List[str]] = None,
) -> CritiqueIssue:
    return CritiqueIssue(
        id=issue_id,
        category=category,
        severity=severity,
        title=title,
        description=f"Test issue {issue_id}",
        affected_artifacts=affected or [],
        suggestion="Fix it",
    )


def _make_requirement(req_id: str, title: str):
    """Create a simple requirement-like object."""
    @dataclass
    class SimpleReq:
        requirement_id: str = ""
        title: str = ""
        description: str = ""
    return SimpleReq(requirement_id=req_id, title=title)


@pytest.fixture
def engine():
    """Create a SelfCritiqueEngine without OpenAI client."""
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


# ================================================================
# Fix Classification (4 tests)
# ================================================================

class TestClassifyFixability:
    def test_classify_orphan_as_fixable(self, engine):
        issues = [_make_issue(
            "CI-018", IssueCategory.TRACEABILITY, IssueSeverity.HIGH,
            "Orphan Requirements Without User Stories"
        )]
        engine._classify_fixability(issues)
        assert issues[0].auto_fixable is True
        assert issues[0].fix_strategy == "programmatic"

    def test_classify_missing_tests_as_fixable(self, engine):
        issues = [_make_issue(
            "CI-019", IssueCategory.TRACEABILITY, IssueSeverity.HIGH,
            "User Stories Without Test Coverage"
        )]
        engine._classify_fixability(issues)
        assert issues[0].auto_fixable is True
        assert issues[0].fix_strategy == "programmatic"

    def test_classify_missing_ac_as_llm_fixable(self, engine):
        issues = [_make_issue(
            "CI-011", IssueCategory.TESTABILITY, IssueSeverity.HIGH,
            "Missing Acceptance Criteria"
        )]
        engine._classify_fixability(issues)
        assert issues[0].auto_fixable is True
        assert issues[0].fix_strategy == "llm_assisted"

    def test_classify_completeness_as_not_fixable(self, engine):
        issues = [_make_issue(
            "CI-001", IssueCategory.COMPLETENESS, IssueSeverity.HIGH,
            "Missing Non-Functional Requirements"
        )]
        engine._classify_fixability(issues)
        assert issues[0].auto_fixable is False
        assert issues[0].fix_strategy == "manual"

    def test_classify_subjective_terms_as_llm_fixable(self, engine):
        issues = [_make_issue(
            "CI-012", IssueCategory.TESTABILITY, IssueSeverity.MEDIUM,
            "Subjective Terms in User Stories"
        )]
        engine._classify_fixability(issues)
        assert issues[0].auto_fixable is True
        assert issues[0].fix_strategy == "llm_assisted"


# ================================================================
# Programmatic Fixers (5 tests)
# ================================================================

@pytest.mark.skipif(not HAS_GENERATORS, reason="Generator classes not available")
class TestProgrammaticFixers:
    def test_fix_orphan_reqs_links_to_matching_story(self, engine):
        """Orphan REQ with keyword overlap should link to best matching story."""
        reqs = [_make_requirement("REQ-010", "User Authentication and Login")]
        stories = [
            UserStory(
                id="US-001", title="Login Feature",
                persona="user", action="login to the system",
                benefit="access features",
            ),
            UserStory(
                id="US-002", title="Report Dashboard",
                persona="admin", action="view reports",
                benefit="track metrics",
            ),
        ]
        issue = _make_issue(
            "CI-018", IssueCategory.TRACEABILITY, IssueSeverity.HIGH,
            "Orphan Requirements", affected=["REQ-010"]
        )
        fixes = engine._fix_orphan_requirements(issue, reqs, stories)
        assert len(fixes) == 1
        assert "REQ-010" in fixes[0]
        assert "US-001" in fixes[0]
        # Verify the link was created
        assert "REQ-010" in stories[0].linked_requirement_ids

    def test_fix_orphan_reqs_no_match_fallback(self, engine):
        """If no keywords overlap, no link is created (graceful)."""
        reqs = [_make_requirement("REQ-099", "Quantum Entanglement Protocol")]
        stories = [
            UserStory(
                id="US-001", title="Login Feature",
                persona="user", action="login",
                benefit="access",
            ),
        ]
        issue = _make_issue(
            "CI-018", IssueCategory.TRACEABILITY, IssueSeverity.HIGH,
            "Orphan Requirements", affected=["REQ-099"]
        )
        fixes = engine._fix_orphan_requirements(issue, reqs, stories)
        # "quantum", "entanglement", "protocol" vs "login", "feature" = no overlap
        assert len(fixes) == 0

    def test_fix_stories_without_tests_creates_stubs(self, engine):
        """Stub TestCase objects should be created for uncovered stories."""
        stories = [
            UserStory(
                id="US-005", title="Password Reset",
                persona="user", action="reset my password",
                benefit="regain access to my account",
            ),
        ]
        test_cases = []
        issue = _make_issue(
            "CI-019", IssueCategory.TRACEABILITY, IssueSeverity.HIGH,
            "User Stories Without Test Coverage", affected=["US-005"]
        )
        fixes = engine._fix_stories_without_tests(issue, stories, test_cases)
        assert len(fixes) == 1
        assert len(test_cases) == 1
        tc = test_cases[0]
        assert tc.id.startswith("TC-")
        assert "Password Reset" in tc.title

    def test_fix_stubs_have_correct_parent_links(self, engine):
        """Stub test cases should have parent_user_story_id set."""
        stories = [
            UserStory(
                id="US-010", title="Search Products",
                persona="customer", action="search for products",
                benefit="find what I need",
                parent_requirement_id="REQ-020",
            ),
        ]
        test_cases = []
        issue = _make_issue(
            "CI-019", IssueCategory.TRACEABILITY, IssueSeverity.HIGH,
            "User Stories Without Test Coverage", affected=["US-010"]
        )
        engine._fix_stories_without_tests(issue, stories, test_cases)
        tc = test_cases[0]
        assert tc.parent_user_story_id == "US-010"
        assert tc.parent_requirement_id == "REQ-020"

    def test_fix_stubs_have_given_when_then(self, engine):
        """Stub test cases should have Given/When/Then steps."""
        stories = [
            UserStory(
                id="US-020", title="View Profile",
                persona="registered user", action="view my profile",
                benefit="see my information",
            ),
        ]
        test_cases = []
        issue = _make_issue(
            "CI-019", IssueCategory.TRACEABILITY, IssueSeverity.HIGH,
            "User Stories Without Test Coverage", affected=["US-020"]
        )
        engine._fix_stories_without_tests(issue, stories, test_cases)
        tc = test_cases[0]
        assert len(tc.steps) == 3
        step_types = [s.step_type for s in tc.steps]
        assert step_types == ["Given", "When", "Then"]
        # Steps should reference persona and action
        assert "registered user" in tc.steps[0].description
        assert "view my profile" in tc.steps[1].description


# ================================================================
# Score & Integration (4 tests)
# ================================================================

class TestScoreAndIntegration:
    def test_quality_score_improves_after_fix(self, engine):
        """Fixed issues should be excluded from quality score calculation."""
        issues = [
            _make_issue("CI-001", IssueCategory.TRACEABILITY, IssueSeverity.HIGH, "Orphan Reqs"),
            _make_issue("CI-002", IssueCategory.COMPLETENESS, IssueSeverity.MEDIUM, "Missing NFRs"),
        ]
        # Score with both issues: 10 - 1.0 - 0.5 = 8.5
        score_before = engine._calculate_quality_score(issues)
        assert abs(score_before - 8.5) < 0.01

        # Mark one as fixed, recalculate with unfixed only
        issues[0].fixed = True
        unfixed = [i for i in issues if not i.fixed]
        score_after = engine._calculate_quality_score(unfixed)
        assert abs(score_after - 9.5) < 0.01
        assert score_after > score_before

    def test_quality_score_unchanged_no_fixes(self, engine):
        """If nothing is fixable, score stays the same."""
        issues = [
            _make_issue("CI-001", IssueCategory.COMPLETENESS, IssueSeverity.HIGH, "Missing NFRs"),
            _make_issue("CI-002", IssueCategory.COMPLETENESS, IssueSeverity.MEDIUM, "No Security Reqs"),
        ]
        score = engine._calculate_quality_score(issues)
        # No fixes applied, same issues
        unfixed = [i for i in issues if not i.fixed]
        score_after = engine._calculate_quality_score(unfixed)
        assert abs(score - score_after) < 0.001

    @pytest.mark.asyncio
    async def test_critique_with_auto_fix_false(self, engine):
        """When auto_fix=False, no classification or fixes should run."""
        engine._call_llm = AsyncMock(return_value='{"issues": []}')
        engine.initialized = True
        result = await engine.critique_and_improve(
            requirements=[], user_stories=[], test_cases=[],
            domain="test", auto_fix=False
        )
        assert isinstance(result, CritiqueResult)
        assert "auto_fixed" not in result.summary

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_GENERATORS, reason="Generator classes not available")
    async def test_full_auto_fix_flow_with_mock_llm(self, engine):
        """End-to-end: detect issues, classify, fix programmatic ones, recalculate."""
        # Mock LLM to return traceability issues with orphan reqs
        traceability_response = json.dumps({
            "issues": [
                {
                    "title": "Orphan Requirements Without User Stories",
                    "description": "10 requirements lack user story links",
                    "severity": "high",
                    "affected": ["REQ-001"],
                    "suggestion": "Link them",
                },
                {
                    "title": "User Stories Without Test Coverage",
                    "description": "Stories lack tests",
                    "severity": "high",
                    "affected": ["US-001"],
                    "suggestion": "Create tests",
                },
            ],
            "orphan_requirements": ["REQ-001"],
            "orphan_stories": ["US-001"],
        })
        empty_response = json.dumps({"issues": []})

        # LLM returns empty for consistency/completeness/testability, issues for traceability
        engine._call_llm = AsyncMock(side_effect=[
            empty_response,   # consistency
            empty_response,   # completeness
            empty_response,   # testability
            traceability_response,  # traceability
        ])
        engine.initialized = True

        reqs = [_make_requirement("REQ-001", "User Login Authentication")]
        stories = [
            UserStory(
                id="US-001", title="Login Feature",
                persona="user", action="login to authenticate",
                benefit="access the system",
            ),
        ]
        test_cases = []

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create required subdirectories
            os.makedirs(os.path.join(tmpdir, "user_stories"), exist_ok=True)
            os.makedirs(os.path.join(tmpdir, "testing"), exist_ok=True)
            # Create placeholder files
            with open(os.path.join(tmpdir, "testing", "test_documentation.md"), "w") as f:
                f.write("# Test Docs\n")

            result = await engine.critique_and_improve(
                requirements=reqs, user_stories=stories, test_cases=test_cases,
                domain="test", auto_fix=True, output_dir=tmpdir
            )

        assert isinstance(result, CritiqueResult)
        assert result.summary.get("auto_fixed", 0) >= 1
        # Orphan req should now be linked
        assert "REQ-001" in stories[0].linked_requirement_ids
        # Stub test case should be created
        assert len(test_cases) >= 1
        assert test_cases[0].parent_user_story_id == "US-001"
        # Score should be better than 0
        assert result.quality_score > 0


# ================================================================
# _save_fixed_artifacts (2 tests)
# ================================================================

@pytest.mark.skipif(not HAS_GENERATORS, reason="Generator classes not available")
class TestSaveFixedArtifacts:
    def test_save_rewrites_user_stories_md(self, engine):
        """After fixes, user_stories.md should be regenerated."""
        stories = [
            UserStory(
                id="US-001", title="Login",
                persona="user", action="login",
                benefit="access",
                acceptance_criteria=[
                    AcceptanceCriterion(given="valid credentials", when="I submit login", then="I see dashboard"),
                ],
            ),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            us_dir = os.path.join(tmpdir, "user_stories")
            os.makedirs(us_dir)
            saved = engine._save_fixed_artifacts(tmpdir, stories, [])
            assert len(saved) >= 1
            md_path = os.path.join(us_dir, "user_stories.md")
            assert os.path.exists(md_path)
            content = open(md_path, encoding="utf-8").read()
            assert "US-001" in content
            assert "Login" in content

    def test_save_appends_stub_test_cases(self, engine):
        """Stub test cases should be appended to test_documentation.md."""
        stub_tc = TestCase(
            id="TC-999", title="Verify Login",
            description="Stub test case for US-001",
            steps=[
                TestStep(step_type="Given", description="user is on the page"),
                TestStep(step_type="When", description="user logs in"),
                TestStep(step_type="Then", description="access is verified"),
            ],
            parent_user_story_id="US-001",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = os.path.join(tmpdir, "testing")
            os.makedirs(test_dir)
            doc_path = os.path.join(test_dir, "test_documentation.md")
            with open(doc_path, "w") as f:
                f.write("# Existing Tests\n")
            saved = engine._save_fixed_artifacts(tmpdir, [], [stub_tc])
            assert len(saved) >= 1
            content = open(doc_path, encoding="utf-8").read()
            assert "Auto-Generated Stub Test Cases" in content
            assert "TC-999" in content


# ================================================================
# CritiqueIssue dataclass (2 tests)
# ================================================================

class TestCritiqueIssueDataclass:
    def test_to_dict_includes_fix_fields(self):
        issue = CritiqueIssue(
            id="CI-001",
            category=IssueCategory.TRACEABILITY,
            severity=IssueSeverity.HIGH,
            title="Test",
            description="Test desc",
            fix_strategy="programmatic",
            fix_details="Linked REQ-001 to US-001",
            auto_fixable=True,
            fixed=True,
        )
        d = issue.to_dict()
        assert d["fix_strategy"] == "programmatic"
        assert d["fix_details"] == "Linked REQ-001 to US-001"
        assert d["auto_fixable"] is True
        assert d["fixed"] is True

    def test_to_markdown_shows_fixed_status(self):
        issue = CritiqueIssue(
            id="CI-001",
            category=IssueCategory.TRACEABILITY,
            severity=IssueSeverity.HIGH,
            title="Test Issue",
            description="Desc",
            fixed=True,
        )
        md = issue.to_markdown()
        assert "Auto-fixed" in md


# ================================================================
# LLM Integration Test (skip without API key)
# ================================================================

@pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set"
)
@pytest.mark.skipif(not HAS_GENERATORS, reason="Generator classes not available")
@pytest.mark.asyncio
async def test_llm_acceptance_criteria_generation():
    """Integration: real LLM call to generate acceptance criteria."""
    engine = SelfCritiqueEngine(
        model_name="openai/gpt-4o-mini",
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ.get("OPENROUTER_API_KEY"),
    )
    await engine.initialize()

    stories = [
        UserStory(
            id="US-INT-001", title="Password Reset",
            persona="user", action="reset my password via email",
            benefit="regain access to my account",
        ),
    ]
    issue = _make_issue(
        "CI-011", IssueCategory.TESTABILITY, IssueSeverity.HIGH,
        "Missing Acceptance Criteria", affected=["US-INT-001"]
    )
    fixes = await engine._fix_missing_acceptance_criteria(issue, stories)
    assert len(fixes) >= 1
    assert len(stories[0].acceptance_criteria) >= 1
    ac = stories[0].acceptance_criteria[0]
    assert ac.given
    assert ac.when
    assert ac.then
