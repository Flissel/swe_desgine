"""
Tests for the post-generation refinement loop.

Tests cover:
  - ArtifactLoader (mock output dirs)
  - CompletenessChecker (12 rules with mock bundles)
  - GapClassifier
  - RefinementReport generation
  - RefinementLoop (dry-run on real output)
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from requirements_engineer.refinement import (
    ArtifactBundle,
    CompletenessReport,
    DEFAULT_THRESHOLDS,
    DEFAULT_WEIGHTS,
    FileLoadResult,
    Gap,
    GapFixStrategy,
    GapSeverity,
    LoadStatus,
    RefinementResult,
    RuleResult,
)
from requirements_engineer.refinement.artifact_loader import ArtifactLoader
from requirements_engineer.refinement.completeness_checker import (
    CompletenessChecker,
    _extract_keywords,
)
from requirements_engineer.refinement.gap_classifier import (
    ClassifiedGaps,
    classify_gaps,
    _gap_priority,
)
from requirements_engineer.refinement.generator_invoker import (
    GeneratorInvoker,
    _estimate_cost,
)
from requirements_engineer.refinement.refinement_report import (
    generate_dry_run_report,
    generate_report,
)


# ============================================================================
# Fixtures
# ============================================================================

def _make_req(rid: str, title: str = "", desc: str = "", rtype: str = "functional"):
    """Create a mock requirement."""
    req = MagicMock()
    req.requirement_id = rid
    req.id = rid
    req.title = title or f"Requirement {rid}"
    req.description = desc or f"Description for {rid}"
    req.type = rtype
    return req


def _make_story(sid: str, parent_req: str = "", title: str = "", parent_epic: str = ""):
    """Create a mock user story."""
    story = MagicMock()
    story.id = sid
    story.title = title or f"Story {sid}"
    story.parent_requirement_id = parent_req
    story.parent_epic_id = parent_epic
    story.linked_requirement_ids = []
    story.persona = "User"
    story.action = "do something"
    story.benefit = "get value"
    return story


def _make_test_case(tcid: str, parent_story: str = ""):
    """Create a mock test case."""
    tc = MagicMock()
    tc.id = tcid
    tc.title = f"Test {tcid}"
    tc.description = f"Test description for {tcid}"
    tc.parent_user_story_id = parent_story
    tc.test_type = "acceptance"
    tc.status = "active"
    return tc


def _make_endpoint(method: str, path: str, parent_req: str = "", summary: str = ""):
    """Create a mock API endpoint."""
    ep = MagicMock()
    ep.method = method
    ep.path = path
    ep.summary = summary or f"{method} {path}"
    ep.parent_requirement_id = parent_req
    ep.tags = []
    return ep


def _make_task(tid: str, parent_req: str = "", parent_story: str = "", parent_feature: str = ""):
    """Create a mock task."""
    task = MagicMock()
    task.id = tid
    task.title = f"Task {tid}"
    task.description = f"Implement {tid}"
    task.parent_requirement_id = parent_req
    task.parent_user_story_id = parent_story
    task.parent_feature_id = parent_feature
    return task


def _make_epic(eid: str, title: str = "", desc: str = ""):
    """Create a mock epic."""
    epic = MagicMock()
    epic.id = eid
    epic.title = title or f"Epic {eid}"
    epic.description = desc or f"Description for {eid}"
    return epic


def _make_entity(name: str, fields=None):
    """Create a mock entity."""
    entity = MagicMock()
    entity.name = name
    entity.fields = fields or []
    return entity


def _make_state_machine(entity_name: str):
    """Create a mock state machine."""
    sm = MagicMock()
    sm.entity = entity_name
    return sm


def _make_screen(sid: str, parent_story: str = "", components=None):
    """Create a mock screen."""
    screen = MagicMock()
    screen.id = sid
    screen.parent_user_story = parent_story
    screen.linked_user_stories = []
    screen.components = components or []
    return screen


def _make_flow(name: str, desc: str = ""):
    """Create a mock user flow."""
    flow = MagicMock()
    flow.name = name
    flow.title = name
    flow.description = desc or f"Flow for {name}"
    return flow


def _make_bundle(**kwargs) -> ArtifactBundle:
    """Create an ArtifactBundle with optional overrides."""
    bundle = ArtifactBundle()
    for key, val in kwargs.items():
        setattr(bundle, key, val)
    # Build indices
    for req in bundle.requirements:
        rid = getattr(req, "requirement_id", "")
        if rid:
            bundle.req_by_id[rid] = req
    for story in bundle.user_stories:
        sid = getattr(story, "id", "")
        if sid:
            bundle.story_by_id[sid] = story
    for tc in bundle.test_cases:
        tid = getattr(tc, "id", "")
        if tid:
            bundle.test_by_id[tid] = tc
    for ep in bundle.api_endpoints:
        key = f"{getattr(ep, 'method', '')} {getattr(ep, 'path', '')}"
        bundle.endpoint_by_key[key] = ep
    for task in bundle.tasks:
        tid = getattr(task, "id", "")
        if tid:
            bundle.task_by_id[tid] = task
    return bundle


# ============================================================================
# ArtifactBundle Tests
# ============================================================================

class TestArtifactBundle:
    def test_empty_bundle(self):
        bundle = ArtifactBundle()
        assert bundle.loaded_count == 0
        assert bundle.missing_count == 0
        s = bundle.summary()
        assert s["requirements"] == 0

    def test_summary_counts(self):
        bundle = _make_bundle(
            requirements=[_make_req("REQ-001"), _make_req("REQ-002")],
            user_stories=[_make_story("US-001")],
        )
        s = bundle.summary()
        assert s["requirements"] == 2
        assert s["user_stories"] == 1

    def test_file_result_tracking(self):
        bundle = ArtifactBundle()
        bundle.file_results.append(FileLoadResult("a.json", LoadStatus.LOADED, 5))
        bundle.file_results.append(FileLoadResult("b.json", LoadStatus.MISSING))
        assert bundle.loaded_count == 1
        assert bundle.missing_count == 1


# ============================================================================
# ArtifactLoader Tests
# ============================================================================

class TestArtifactLoader:
    def test_missing_directory_raises(self):
        with pytest.raises(FileNotFoundError):
            ArtifactLoader("/nonexistent/path/12345")

    def test_empty_directory(self, tmp_path):
        loader = ArtifactLoader(tmp_path)
        bundle = loader.load_all()
        assert len(bundle.requirements) == 0
        assert len(bundle.user_stories) == 0
        assert bundle.missing_count > 0

    def test_loads_journal_json(self, tmp_path):
        """Test loading requirements from journal.json."""
        journal = {
            "nodes": {
                "abc123": {
                    "id": "abc123",
                    "requirement_id": "REQ-001",
                    "title": "Test Requirement",
                    "description": "A test requirement",
                    "type": "functional",
                    "priority": "must",
                    "acceptance_criteria": [],
                    "testable": True,
                    "dependencies": [],
                    "conflicts": [],
                    "related_requirements": [],
                    "mermaid_diagrams": {},
                    "validation_status": "draft",
                    "version": 1,
                    "children_version_ids": [],
                    "improvement_suggestions": [],
                }
            }
        }
        (tmp_path / "journal.json").write_text(json.dumps(journal), encoding="utf-8")

        loader = ArtifactLoader(tmp_path)
        bundle = loader.load_all()
        assert len(bundle.requirements) == 1
        assert bundle.req_by_id["REQ-001"].title == "Test Requirement"

    def test_loads_epics_json(self, tmp_path):
        """Test loading epics from dedicated file."""
        epics_dir = tmp_path / "user_stories" / "epics"
        epics_dir.mkdir(parents=True)
        epics = [
            {
                "id": "EPIC-001",
                "title": "Auth Epic",
                "description": "Authentication features",
                "stories": [],
                "parent_requirements": [],
                "status": "active",
                "created_at": "2026-01-01T00:00:00",
                "acceptance_criteria": [],
                "definition_of_done": [],
                "story_points": 0,
                "business_value": "",
                "priority": "must",
                "owner_role": "",
                "dependencies": [],
            }
        ]
        (epics_dir / "epics.json").write_text(json.dumps(epics), encoding="utf-8")

        loader = ArtifactLoader(tmp_path)
        bundle = loader.load_all()
        assert len(bundle.epics) == 1
        assert bundle.epic_by_id["EPIC-001"].title == "Auth Epic"

    def test_loads_diagrams(self, tmp_path):
        """Test loading .mmd files."""
        diag_dir = tmp_path / "diagrams"
        diag_dir.mkdir()
        (diag_dir / "er.mmd").write_text("erDiagram\n  User ||--o{ Order : places", encoding="utf-8")

        loader = ArtifactLoader(tmp_path)
        bundle = loader.load_all()
        assert "diagrams/er.mmd" in bundle.diagrams


# ============================================================================
# Keyword Extraction Tests
# ============================================================================

class TestKeywordExtraction:
    def test_basic_extraction(self):
        kw = _extract_keywords("The user should authenticate via OAuth2")
        assert "authenticate" in kw
        assert "oauth" in kw  # regex extracts alpha chars only, "2" stripped
        assert "the" not in kw
        assert "should" not in kw

    def test_stopwords_removed(self):
        kw = _extract_keywords("and the or not but if")
        assert len(kw) == 0

    def test_short_words_removed(self):
        kw = _extract_keywords("go to do it")
        assert len(kw) == 0

    def test_german_stopwords(self):
        kw = _extract_keywords("der die das ein eine und oder")
        assert len(kw) == 0


# ============================================================================
# CompletenessChecker Tests
# ============================================================================

class TestCompletenessChecker:
    def test_empty_bundle_all_pass(self):
        """Empty bundle should get 100% (nothing to check)."""
        bundle = _make_bundle()
        checker = CompletenessChecker()
        report = checker.check_all(bundle)
        assert report.overall_score == 1.0

    def test_req_to_story_pass(self):
        """Requirements with stories should pass."""
        bundle = _make_bundle(
            requirements=[_make_req("REQ-001"), _make_req("REQ-002")],
            user_stories=[
                _make_story("US-001", parent_req="REQ-001"),
                _make_story("US-002", parent_req="REQ-002"),
            ],
        )
        checker = CompletenessChecker()
        report = checker.check_all(bundle)
        rr = next(r for r in report.rule_results if r.rule_id == "req_to_story")
        assert rr.passed
        assert rr.score == 1.0

    def test_req_to_story_fail(self):
        """Requirements without stories should fail."""
        bundle = _make_bundle(
            requirements=[_make_req("REQ-001"), _make_req("REQ-002"), _make_req("REQ-003")],
            user_stories=[_make_story("US-001", parent_req="REQ-001")],
        )
        checker = CompletenessChecker()
        report = checker.check_all(bundle)
        rr = next(r for r in report.rule_results if r.rule_id == "req_to_story")
        assert not rr.passed
        assert len(rr.gaps) == 2

    def test_story_to_test_pass(self):
        """Stories with tests should pass."""
        bundle = _make_bundle(
            user_stories=[_make_story("US-001"), _make_story("US-002")],
            test_cases=[
                _make_test_case("TC-001", parent_story="US-001"),
                _make_test_case("TC-002", parent_story="US-002"),
            ],
        )
        checker = CompletenessChecker()
        report = checker.check_all(bundle)
        rr = next(r for r in report.rule_results if r.rule_id == "story_to_test")
        assert rr.passed

    def test_story_to_test_fail(self):
        """Stories without tests should fail."""
        bundle = _make_bundle(
            user_stories=[_make_story("US-001"), _make_story("US-002")],
            test_cases=[_make_test_case("TC-001", parent_story="US-001")],
        )
        checker = CompletenessChecker()
        report = checker.check_all(bundle)
        rr = next(r for r in report.rule_results if r.rule_id == "story_to_test")
        assert not rr.passed
        assert len(rr.gaps) == 1
        assert rr.gaps[0].affected_ids == ["US-002"]

    def test_api_to_req_pass(self):
        """Endpoints with parent_requirement_id should pass."""
        bundle = _make_bundle(
            api_endpoints=[
                _make_endpoint("GET", "/users", parent_req="REQ-001"),
                _make_endpoint("POST", "/users", parent_req="REQ-002"),
            ],
        )
        checker = CompletenessChecker()
        report = checker.check_all(bundle)
        rr = next(r for r in report.rule_results if r.rule_id == "api_to_req")
        assert rr.passed

    def test_api_to_req_fail(self):
        """Endpoints without parent_requirement_id should fail."""
        bundle = _make_bundle(
            api_endpoints=[
                _make_endpoint("GET", "/users", parent_req="REQ-001"),
                _make_endpoint("POST", "/orders", parent_req=""),
            ],
        )
        checker = CompletenessChecker()
        report = checker.check_all(bundle)
        rr = next(r for r in report.rule_results if r.rule_id == "api_to_req")
        assert not rr.passed
        assert len(rr.gaps) == 1

    def test_task_ratio_pass(self):
        """Sufficient tasks should pass."""
        bundle = _make_bundle(
            requirements=[_make_req("REQ-001")],
            tasks=[_make_task("T-001"), _make_task("T-002"), _make_task("T-003")],
        )
        checker = CompletenessChecker()
        report = checker.check_all(bundle)
        rr = next(r for r in report.rule_results if r.rule_id == "task_ratio")
        assert rr.passed  # 3 tasks / 1 req = 3.0 >= 2.0

    def test_task_ratio_fail(self):
        """Insufficient tasks should fail."""
        bundle = _make_bundle(
            requirements=[_make_req("REQ-001"), _make_req("REQ-002"), _make_req("REQ-003")],
            tasks=[_make_task("T-001")],
        )
        checker = CompletenessChecker()
        report = checker.check_all(bundle)
        rr = next(r for r in report.rule_results if r.rule_id == "task_ratio")
        assert not rr.passed  # 1/3 = 0.33 < 2.0

    def test_task_backlinks_pass(self):
        """Tasks with backlinks should pass."""
        bundle = _make_bundle(
            tasks=[
                _make_task("T-001", parent_req="REQ-001"),
                _make_task("T-002", parent_feature="FEAT-001"),
            ],
        )
        checker = CompletenessChecker()
        report = checker.check_all(bundle)
        rr = next(r for r in report.rule_results if r.rule_id == "task_backlinks")
        assert rr.passed

    def test_task_backlinks_fail(self):
        """Tasks without any backlinks should fail."""
        bundle = _make_bundle(
            tasks=[
                _make_task("T-001", parent_req="REQ-001"),
                _make_task("T-002"),  # no backlinks
                _make_task("T-003"),  # no backlinks
            ],
        )
        checker = CompletenessChecker()
        report = checker.check_all(bundle)
        rr = next(r for r in report.rule_results if r.rule_id == "task_backlinks")
        # 1/3 = 33% < 80%
        assert not rr.passed
        assert len(rr.gaps) == 2

    def test_quality_gates_pass(self):
        """All gates checked should pass."""
        bundle = _make_bundle(
            requirements=[_make_req("REQ-001")],
            user_stories=[_make_story("US-001")],
            test_cases=[_make_test_case("TC-001")],
        )
        checker = CompletenessChecker()
        report = checker.check_all(bundle)
        rr = next(r for r in report.rule_results if r.rule_id == "quality_gates")
        assert rr.passed

    def test_flow_coverage_pass(self):
        """Epics matched to flows should pass."""
        bundle = _make_bundle(
            epics=[_make_epic("EPIC-001", title="User Authentication Login System")],
            user_flows=[_make_flow("Authentication Login Flow", desc="User authentication login system")],
        )
        checker = CompletenessChecker()
        report = checker.check_all(bundle)
        rr = next(r for r in report.rule_results if r.rule_id == "flow_coverage")
        assert rr.passed

    def test_flow_coverage_fail(self):
        """Epics without matching flows should fail."""
        bundle = _make_bundle(
            epics=[
                _make_epic("EPIC-001", title="User Authentication"),
                _make_epic("EPIC-002", title="Payment Processing"),
            ],
            user_flows=[_make_flow("Unrelated Feature Flow")],
        )
        checker = CompletenessChecker()
        report = checker.check_all(bundle)
        rr = next(r for r in report.rule_results if r.rule_id == "flow_coverage")
        assert not rr.passed

    def test_disabled_rules(self):
        """Disabled rules should be excluded from results."""
        bundle = _make_bundle(
            requirements=[_make_req("REQ-001")],
            user_stories=[],  # Would fail req_to_story
        )
        checker = CompletenessChecker({"disabled_rules": ["req_to_story"]})
        report = checker.check_all(bundle)
        rule_ids = [r.rule_id for r in report.rule_results]
        assert "req_to_story" not in rule_ids

    def test_overall_score_weighted(self):
        """Overall score should be weighted average of rule scores."""
        bundle = _make_bundle(
            requirements=[_make_req("REQ-001")],
            user_stories=[_make_story("US-001", parent_req="REQ-001")],
            test_cases=[_make_test_case("TC-001", parent_story="US-001")],
        )
        checker = CompletenessChecker()
        report = checker.check_all(bundle)
        # Most rules should pass (empty artifacts = 1.0)
        assert report.overall_score > 0.5


# ============================================================================
# GapClassifier Tests
# ============================================================================

class TestGapClassifier:
    def test_classify_by_strategy(self):
        gaps = [
            Gap(gap_id="GAP-001", rule_id="story_to_test",
                fix_strategy=GapFixStrategy.AUTO_LINK),
            Gap(gap_id="GAP-002", rule_id="entity_to_req",
                fix_strategy=GapFixStrategy.LLM_EXTEND),
            Gap(gap_id="GAP-003", rule_id="story_to_screen",
                fix_strategy=GapFixStrategy.GENERATOR),
            Gap(gap_id="GAP-004", rule_id="quality_gates",
                fix_strategy=GapFixStrategy.MANUAL),
        ]
        classified = classify_gaps(gaps)
        assert len(classified.auto_link) == 1
        assert len(classified.llm_extend) == 1
        assert len(classified.generator) == 1
        assert len(classified.manual) == 1
        assert classified.fixable_count == 3
        assert classified.total_count == 4

    def test_priority_sorting(self):
        """Higher severity gaps should be first."""
        gaps = [
            Gap(gap_id="GAP-001", rule_id="story_to_test",
                severity=GapSeverity.LOW,
                fix_strategy=GapFixStrategy.AUTO_LINK,
                target_value=1.0, current_value=0.0),
            Gap(gap_id="GAP-002", rule_id="story_to_test",
                severity=GapSeverity.CRITICAL,
                fix_strategy=GapFixStrategy.AUTO_LINK,
                target_value=1.0, current_value=0.0),
        ]
        classified = classify_gaps(gaps)
        assert classified.auto_link[0].gap_id == "GAP-002"  # Critical first

    def test_gap_priority_calculation(self):
        gap_high = Gap(
            gap_id="G1", rule_id="req_to_story",
            severity=GapSeverity.HIGH,
            target_value=1.0, current_value=0.0,
        )
        gap_low = Gap(
            gap_id="G2", rule_id="req_to_story",
            severity=GapSeverity.LOW,
            target_value=1.0, current_value=0.0,
        )
        assert _gap_priority(gap_high) > _gap_priority(gap_low)


# ============================================================================
# GeneratorInvoker Tests
# ============================================================================

class TestGeneratorInvoker:
    def test_fix_api_to_req_link(self):
        """API endpoint should be linked to requirement via keyword overlap."""
        reqs = [
            _make_req("REQ-001", title="Register Auth Endpoint",
                      desc="Handle register and auth for users"),
        ]
        ep = _make_endpoint("POST", "/auth/register", parent_req="",
                            summary="Register auth endpoint")
        bundle = _make_bundle(
            requirements=reqs,
            api_endpoints=[ep],
        )

        gap = Gap(
            gap_id="GAP-001", rule_id="api_to_req",
            affected_ids=["POST /auth/register"],
            fix_strategy=GapFixStrategy.AUTO_LINK,
        )

        invoker = GeneratorInvoker()
        result = asyncio.run(invoker._fix_api_to_req_link(gap, bundle))
        assert result is True
        assert ep.parent_requirement_id == "REQ-001"

    def test_fix_task_backlink(self):
        """Task should be linked to requirement via keyword overlap."""
        reqs = [
            _make_req("REQ-001", title="Message Encryption Security",
                      desc="End-to-end encryption for messages security"),
        ]
        task = _make_task("T-001")
        task.title = "Implement Message Encryption Security"
        task.description = "Add message encryption security to chat module"
        bundle = _make_bundle(requirements=reqs, tasks=[task])

        gap = Gap(
            gap_id="GAP-001", rule_id="task_backlinks",
            affected_ids=["T-001"],
            fix_strategy=GapFixStrategy.AUTO_LINK,
        )

        invoker = GeneratorInvoker()
        result = asyncio.run(invoker._fix_task_backlink(gap, bundle))
        assert result is True
        assert task.parent_requirement_id == "REQ-001"

    def test_fix_story_without_test(self):
        """Stub test case should be created for story without test."""
        stories = [_make_story("US-001")]
        bundle = _make_bundle(user_stories=stories, test_cases=[])

        gap = Gap(
            gap_id="GAP-001", rule_id="story_to_test",
            affected_ids=["US-001"],
            fix_strategy=GapFixStrategy.AUTO_LINK,
        )

        invoker = GeneratorInvoker()
        result = invoker._fix_story_without_test(gap, bundle)
        assert result is True
        assert len(bundle.test_cases) == 1
        assert bundle.test_cases[0].parent_user_story_id == "US-001"
        assert "REFINE" in bundle.test_cases[0].id


# ============================================================================
# LLM-Powered Fix Tests (mocked)
# ============================================================================

class TestLLMFixes:
    def test_cost_estimation(self):
        """Cost estimation should vary by model family."""
        assert _estimate_cost("google/gemini-3-flash-preview") < _estimate_cost("openai/gpt-4o")
        assert _estimate_cost("google/gemini-3-flash-preview") > 0
        assert _estimate_cost("anthropic/claude-sonnet-4.6") > _estimate_cost("openai/gpt-4o-mini")

    def test_extract_json_direct(self):
        """Should parse valid JSON directly."""
        invoker = GeneratorInvoker()
        result = invoker._extract_json('{"links": [{"entity": "User"}]}')
        assert result["links"][0]["entity"] == "User"

    def test_extract_json_code_block(self):
        """Should extract JSON from markdown code block."""
        invoker = GeneratorInvoker()
        result = invoker._extract_json('Here is the result:\n```json\n{"links": [{"entity": "Order"}]}\n```\nDone.')
        assert result["links"][0]["entity"] == "Order"

    def test_extract_json_fallback(self):
        """Should find JSON object in mixed text."""
        invoker = GeneratorInvoker()
        result = invoker._extract_json('I think {"key": "value"} is the answer')
        assert result["key"] == "value"

    def test_extract_json_invalid(self):
        """Should return empty dict on totally invalid input."""
        invoker = GeneratorInvoker()
        result = invoker._extract_json("no json here at all")
        assert result == {}

    def test_entity_to_req_llm_mock(self):
        """Entity linking should use LLM when client is available."""
        invoker = GeneratorInvoker({"model": "test-model"})

        # Mock the client using AsyncMock
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "links": [
                {"entity": "Payment", "requirement_id": "REQ-001",
                 "reason": "Payment processing requirement"}
            ]
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        invoker._client = mock_client

        reqs = [_make_req("REQ-001", title="Payment Processing")]
        entity = _make_entity("Payment", fields=[])
        bundle = _make_bundle(
            requirements=reqs,
            entities={"Payment": entity},
        )

        gap = Gap(
            gap_id="GAP-001", rule_id="entity_to_req",
            affected_ids=["Payment"],
            fix_strategy=GapFixStrategy.LLM_EXTEND,
        )

        result = asyncio.run(invoker._fix_entity_to_req(gap, bundle))
        assert result is True
        assert invoker.llm_calls == 1
        assert invoker.cost_usd > 0
        assert any("Payment" in log for log in invoker.fix_log)

    def test_entity_to_req_keyword_fallback(self):
        """Entity linking should fall back to keywords when no API key."""
        invoker = GeneratorInvoker()  # No API key
        invoker.api_key = None

        # Use entity name "Order" which is a single keyword matching requirement
        reqs = [_make_req("REQ-001", title="Order Management Processing")]
        bundle = _make_bundle(
            requirements=reqs,
            entities={"Order": _make_entity("Order")},
        )

        gap = Gap(
            gap_id="GAP-001", rule_id="entity_to_req",
            affected_ids=["Order"],
            fix_strategy=GapFixStrategy.LLM_EXTEND,
        )

        result = asyncio.run(invoker._fix_entity_to_req(gap, bundle))
        assert result is True
        assert invoker.llm_calls == 0  # No LLM calls -- used keywords
        assert any("keyword" in log.lower() for log in invoker.fix_log)

    def test_generator_no_api_key_skips(self):
        """Generator invocation should skip gracefully without API key."""
        invoker = GeneratorInvoker()
        invoker.api_key = None

        bundle = _make_bundle(
            user_stories=[_make_story("US-001")],
        )

        gap = Gap(
            gap_id="GAP-001", rule_id="story_to_test",
            affected_ids=["US-001"],
            fix_strategy=GapFixStrategy.GENERATOR,
            generator_name="test_case",
        )

        result = asyncio.run(invoker.apply_generator_fixes([gap], bundle))
        assert result == 0
        assert any("SKIP" in log or "No API key" in log for log in invoker.fix_log)

    def test_generator_dispatch_unknown(self):
        """Unknown generator name should log but not crash."""
        invoker = GeneratorInvoker({"model": "test"})
        # Force client to exist
        invoker._client = MagicMock()
        invoker.api_key = "test-key"

        gap = Gap(
            gap_id="GAP-001", rule_id="custom_rule",
            affected_ids=["X-001"],
            fix_strategy=GapFixStrategy.GENERATOR,
            generator_name="nonexistent_generator",
        )

        bundle = _make_bundle()
        result = asyncio.run(invoker.apply_generator_fixes([gap], bundle))
        assert result == 0
        assert any("No handler" in log for log in invoker.fix_log)

    def test_budget_tracking(self):
        """LLM calls should increment budget counters."""
        invoker = GeneratorInvoker({"model": "google/gemini-3-flash-preview"})
        assert invoker.llm_calls == 0
        assert invoker.cost_usd == 0.0
        # Simulate calls
        invoker.llm_calls = 5
        invoker.cost_usd = 0.005
        assert invoker.llm_calls == 5
        assert invoker.cost_usd > 0

    def test_format_requirements(self):
        """Format requirements for LLM prompts."""
        invoker = GeneratorInvoker()
        reqs = [_make_req("REQ-001", title="Auth", desc="Handle authentication")]
        text = invoker._format_requirements(reqs)
        assert "REQ-001" in text
        assert "Auth" in text

    def test_format_user_stories(self):
        """Format user stories for LLM prompts."""
        invoker = GeneratorInvoker()
        stories = [_make_story("US-001")]
        text = invoker._format_user_stories(stories)
        assert "US-001" in text
        assert "As a" in text

    def test_api_to_req_llm_fallback(self):
        """API-to-req should try LLM when semantic fails and API key is available."""
        invoker = GeneratorInvoker({"model": "test-model"})

        # Mock the client with LLM response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "links": [
                {"endpoint": "/api/v1/orders", "requirement_id": "REQ-001",
                 "reason": "Order management endpoint"}
            ]
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        invoker._client = mock_client

        # Use a path that won't keyword-match but LLM can reason about
        reqs = [_make_req("REQ-001", title="Order Management")]
        ep = _make_endpoint("GET", "/api/v1/orders", parent_req="",
                            summary="List all orders")
        bundle = _make_bundle(requirements=reqs, api_endpoints=[ep])

        gap = Gap(
            gap_id="GAP-001", rule_id="api_to_req",
            affected_ids=["GET /api/v1/orders"],
            fix_strategy=GapFixStrategy.AUTO_LINK,
        )

        result = asyncio.run(invoker._fix_api_to_req_link(gap, bundle))
        assert result is True
        assert ep.parent_requirement_id == "REQ-001"
        assert invoker.llm_calls == 1
        assert any("[LLM]" in log for log in invoker.fix_log)

    def test_task_backlink_llm_fallback(self):
        """Task-to-req should try LLM when semantic fails and API key is available."""
        invoker = GeneratorInvoker({"model": "test-model"})

        # Mock the client with LLM response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "links": [
                {"task_id": "T-001", "requirement_id": "REQ-001",
                 "reason": "Notification implementation task"}
            ]
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        invoker._client = mock_client

        reqs = [_make_req("REQ-001", title="Push Notification System")]
        task = _make_task("T-001")
        task.title = "Build notification service"
        task.description = "Implement push notification delivery"
        bundle = _make_bundle(requirements=reqs, tasks=[task])

        gap = Gap(
            gap_id="GAP-001", rule_id="task_backlinks",
            affected_ids=["T-001"],
            fix_strategy=GapFixStrategy.AUTO_LINK,
        )

        result = asyncio.run(invoker._fix_task_backlink(gap, bundle))
        assert result is True
        assert task.parent_requirement_id == "REQ-001"
        assert invoker.llm_calls == 1
        assert any("[LLM]" in log for log in invoker.fix_log)

    def test_api_to_req_llm_fallback_to_keywords(self):
        """API-to-req should fall back to keywords when LLM returns no match."""
        invoker = GeneratorInvoker({"model": "test-model"})

        # Mock LLM returning empty links
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({"links": []})

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        invoker._client = mock_client

        reqs = [_make_req("REQ-001", title="Payment Processing")]
        ep = _make_endpoint("POST", "/api/payment/process", parent_req="",
                            summary="Process payment transaction")
        bundle = _make_bundle(requirements=reqs, api_endpoints=[ep])

        gap = Gap(
            gap_id="GAP-001", rule_id="api_to_req",
            affected_ids=["POST /api/payment/process"],
            fix_strategy=GapFixStrategy.AUTO_LINK,
        )

        result = asyncio.run(invoker._fix_api_to_req_link(gap, bundle))
        assert result is True
        assert ep.parent_requirement_id == "REQ-001"
        # LLM was called but returned nothing, keyword fallback linked it
        assert invoker.llm_calls == 1

    def test_task_backlink_no_api_key_uses_keywords(self):
        """Task-to-req should use keywords when no API key available."""
        invoker = GeneratorInvoker()  # No API key
        invoker.api_key = None

        reqs = [_make_req("REQ-001", title="Authentication Security")]
        task = _make_task("T-001")
        task.title = "Implement Authentication Security"
        task.description = "Add authentication security module"
        bundle = _make_bundle(requirements=reqs, tasks=[task])

        gap = Gap(
            gap_id="GAP-001", rule_id="task_backlinks",
            affected_ids=["T-001"],
            fix_strategy=GapFixStrategy.AUTO_LINK,
        )

        result = asyncio.run(invoker._fix_task_backlink(gap, bundle))
        assert result is True
        assert task.parent_requirement_id == "REQ-001"
        assert invoker.llm_calls == 0  # No LLM, only keywords


# ============================================================================
# RefinementReport Tests
# ============================================================================

class TestRefinementReport:
    def test_dry_run_report_generation(self):
        """Dry-run report should contain scores and gaps."""
        report = CompletenessReport(
            rule_results=[
                RuleResult(
                    rule_id="req_to_story", rule_name="Requirement -> Story",
                    current_value=0.8, target_value=0.95,
                    score=0.842, weight=0.15, passed=False,
                    gaps=[Gap(gap_id="GAP-001", rule_id="req_to_story",
                              title="REQ-003 has no story",
                              severity=GapSeverity.HIGH,
                              fix_strategy=GapFixStrategy.GENERATOR)],
                ),
            ],
            overall_score=0.842,
            timestamp="2026-03-01T00:00:00",
        )
        md = generate_dry_run_report(report)
        assert "Overall Score: 84.2%" in md
        assert "GAP-001" in md
        assert "Requirement -> Story" in md

    def test_refinement_report_generation(self):
        """Full refinement report should have before/after comparison."""
        before_report = CompletenessReport(
            rule_results=[
                RuleResult(
                    rule_id="req_to_story", rule_name="Req -> Story",
                    current_value=0.5, target_value=0.95,
                    score=0.526, weight=0.15, passed=False,
                ),
            ],
            overall_score=0.526,
        )
        result = RefinementResult(
            iterations=2,
            before_scores={"req_to_story": 0.526},
            after_scores={"req_to_story": 0.842},
            before_overall=0.526,
            after_overall=0.842,
            gaps_found=5,
            gaps_fixed=3,
            gaps_remaining=2,
            fix_log=["Fixed GAP-001", "Fixed GAP-002"],
            duration_seconds=1.5,
        )
        md = generate_report(result, before_report, None)
        assert "52.6%" in md
        assert "84.2%" in md
        assert "Gaps Found:** 5" in md
        assert "Gaps Fixed:** 3" in md
        assert "Fixed GAP-001" in md


# ============================================================================
# Semantic Matcher Tests
# ============================================================================

class TestSemanticMatcher:
    """Tests for SemanticMatcher and its integration into GeneratorInvoker."""

    def test_matcher_not_available_no_key(self):
        """Matcher should report not available without API key."""
        from requirements_engineer.memory.semantic_matcher import SemanticMatcher
        matcher = SemanticMatcher(api_key=None)
        # Force no env var
        with patch.dict(os.environ, {}, clear=True):
            m = SemanticMatcher(api_key=None)
        assert m.available is False

    def test_matcher_stats_initial(self):
        """Stats should reflect initial state."""
        from requirements_engineer.memory.semantic_matcher import SemanticMatcher
        matcher = SemanticMatcher(api_key="test-key")
        stats = matcher.stats()
        assert stats["index_size"] == 0
        assert stats["cache_size"] == 0
        assert stats["embed_calls"] == 0
        assert stats["cost_usd"] == 0.0

    def test_matcher_cache_key(self):
        """Same text should produce same cache key."""
        from requirements_engineer.memory.semantic_matcher import SemanticMatcher
        k1 = SemanticMatcher._cache_key("hello world")
        k2 = SemanticMatcher._cache_key("hello world")
        k3 = SemanticMatcher._cache_key("different text")
        assert k1 == k2
        assert k1 != k3

    def test_matcher_build_index_with_mock_embeddings(self):
        """Build index with mocked embedding API and verify cosine search."""
        from requirements_engineer.memory.semantic_matcher import SemanticMatcher
        import numpy as np

        matcher = SemanticMatcher(api_key="test-key")

        # Mock embed_batch to return deterministic vectors
        dim = 8
        async def mock_embed_batch(texts):
            vectors = []
            for i, text in enumerate(texts):
                # Create distinct unit vectors for each item
                vec = np.zeros(dim)
                # "auth" words get high weight in dim 0
                if "auth" in text.lower() or "login" in text.lower():
                    vec[0] = 0.9
                    vec[1] = 0.4
                # "payment" words get high weight in dim 2
                elif "payment" in text.lower() or "billing" in text.lower():
                    vec[2] = 0.9
                    vec[3] = 0.4
                # "message" words get high weight in dim 4
                elif "message" in text.lower() or "chat" in text.lower():
                    vec[4] = 0.9
                    vec[5] = 0.4
                else:
                    vec[6] = 0.5
                    vec[7] = 0.5
                vectors.append(vec.tolist())
            return vectors

        matcher.embed_batch = mock_embed_batch

        async def _run():
            items = [
                ("REQ-001", "User authentication and login"),
                ("REQ-002", "Payment processing and billing"),
                ("REQ-003", "Message sending and chat"),
            ]
            count = await matcher.build_index(items)
            assert count == 3
            assert matcher._index_built is True

            # Search for "login" → should match REQ-001 (auth)
            results = await matcher.find_similar("login security", top_k=3)
            assert len(results) > 0
            assert results[0][0] == "REQ-001"
            assert results[0][1] > 0.8  # High similarity

            # Search for "billing" → should match REQ-002 (payment)
            results = await matcher.find_similar("billing invoice", top_k=3)
            assert len(results) > 0
            assert results[0][0] == "REQ-002"

        asyncio.run(_run())

    def test_matcher_find_best_match(self):
        """find_best_match should return top result or None."""
        from requirements_engineer.memory.semantic_matcher import SemanticMatcher
        import numpy as np

        matcher = SemanticMatcher(api_key="test-key")

        # Build a minimal index manually
        matcher._index_ids = ["REQ-001", "REQ-002"]
        matcher._index_texts = ["auth login", "payment billing"]
        # Create normalized vectors
        v1 = np.array([1.0, 0.0], dtype=np.float32)
        v2 = np.array([0.0, 1.0], dtype=np.float32)
        matcher._index_vectors = np.vstack([v1, v2])
        matcher._index_built = True

        # Mock embed_batch for query
        async def mock_embed(texts):
            return [[1.0, 0.0] for _ in texts]
        matcher.embed_batch = mock_embed

        async def _run():
            result = await matcher.find_best_match("test", threshold=0.5)
            assert result is not None
            assert result[0] == "REQ-001"
            assert result[1] > 0.9

            # With very high threshold
            result = await matcher.find_best_match("test", threshold=1.1)
            assert result is None

        asyncio.run(_run())

    def test_matcher_empty_index(self):
        """find_similar on empty index should return empty list."""
        from requirements_engineer.memory.semantic_matcher import SemanticMatcher
        matcher = SemanticMatcher(api_key="test-key")
        results = asyncio.run(matcher.find_similar("anything"))
        assert results == []

    def test_invoker_ensure_matcher_no_key(self):
        """_ensure_matcher should return False without API key."""
        invoker = GeneratorInvoker()
        # Ensure no env var
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_API_KEY", None)
            result = asyncio.run(invoker._ensure_matcher())
        assert result is False

    def test_invoker_build_index_no_matcher(self):
        """build_artifact_index should return False without matcher."""
        invoker = GeneratorInvoker()
        invoker._matcher_checked = True  # Pretend we already checked
        bundle = _make_bundle(requirements=[_make_req("REQ-001")])
        result = asyncio.run(invoker.build_artifact_index(bundle))
        assert result is False

    def test_auto_link_semantic_path(self):
        """Auto-link should use semantic matcher when index is built."""
        invoker = GeneratorInvoker()

        # Create a mock matcher
        mock_matcher = MagicMock()
        mock_matcher.available = True
        mock_matcher.find_similar = AsyncMock(return_value=[
            ("REQ-001", 0.85),
        ])
        mock_matcher.stats.return_value = {"index_size": 3, "embed_calls": 1,
                                            "cache_hits": 0, "cost_usd": 0.001}
        invoker._matcher = mock_matcher
        invoker._index_built = True

        # Create bundle with API endpoint
        ep = MagicMock()
        ep.path = "/api/users/login"
        ep.summary = "User login endpoint"
        ep.parent_requirement_id = None

        bundle = _make_bundle(
            requirements=[_make_req("REQ-001", title="User Authentication")],
            api_endpoints=[ep],
        )
        bundle.endpoint_by_key = {"GET /api/users/login": ep}

        gap = Gap(
            gap_id="GAP-001", rule_id="api_to_req",
            affected_ids=["GET /api/users/login"],
            fix_strategy=GapFixStrategy.AUTO_LINK,
        )

        result = asyncio.run(invoker._fix_api_to_req_link(gap, bundle))
        assert result is True
        assert ep.parent_requirement_id == "REQ-001"
        assert any("SEMANTIC" in log for log in invoker.fix_log)

    def test_auto_link_keyword_fallback_when_semantic_fails(self):
        """Auto-link should fall back to keywords when semantic matching throws."""
        invoker = GeneratorInvoker()
        invoker.api_key = None  # Force keyword path, skip LLM fallback

        # Create a mock matcher that fails
        mock_matcher = MagicMock()
        mock_matcher.available = True
        mock_matcher.find_similar = AsyncMock(side_effect=RuntimeError("API error"))
        invoker._matcher = mock_matcher
        invoker._index_built = True

        # Create bundle with matching keywords
        ep = MagicMock()
        ep.path = "/api/register"
        ep.summary = "Register Auth Endpoint"
        ep.parent_requirement_id = None

        bundle = _make_bundle(
            requirements=[_make_req("REQ-001", title="Register Auth System")],
            api_endpoints=[ep],
        )
        bundle.endpoint_by_key = {"POST /api/register": ep}

        gap = Gap(
            gap_id="GAP-001", rule_id="api_to_req",
            affected_ids=["POST /api/register"],
            fix_strategy=GapFixStrategy.AUTO_LINK,
        )

        result = asyncio.run(invoker._fix_api_to_req_link(gap, bundle))
        assert result is True
        # Should have used keyword fallback, not semantic
        assert any("keyword" in log.lower() or "overlap" in log.lower()
                    for log in invoker.fix_log)

    def test_entity_linking_with_rag_context(self):
        """LLM entity linking should include RAG context when matcher available."""
        invoker = GeneratorInvoker({"model": "test-model"})

        # Mock matcher for RAG context
        mock_matcher = MagicMock()
        mock_matcher.available = True
        mock_matcher.find_similar = AsyncMock(return_value=[
            ("REQ-001", 0.92),
            ("REQ-002", 0.65),
        ])
        invoker._matcher = mock_matcher
        invoker._index_built = True

        # Mock LLM client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "links": [
                {"entity": "UserAccount", "requirement_id": "REQ-001",
                 "reason": "Account management requirement"}
            ]
        })
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        invoker._client = mock_client

        bundle = _make_bundle(
            requirements=[
                _make_req("REQ-001", title="User Account Management"),
                _make_req("REQ-002", title="Payment Processing"),
            ],
            entities={"UserAccount": _make_entity("UserAccount")},
        )

        gap = Gap(
            gap_id="GAP-001", rule_id="entity_to_req",
            affected_ids=["UserAccount"],
            fix_strategy=GapFixStrategy.LLM_EXTEND,
        )

        result = asyncio.run(invoker._fix_entity_to_req(gap, bundle))
        assert result is True

        # Verify RAG context was injected into the LLM call
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages", [])
        user_msg = messages[-1]["content"]
        assert "Semantic Analysis" in user_msg
        assert "REQ-001" in user_msg
        assert "0.92" in user_msg

    def test_matcher_stats_method(self):
        """matcher_stats should return None when no matcher active."""
        invoker = GeneratorInvoker()
        assert invoker.matcher_stats() is None


# ============================================================================
# Integration Test (requires real output directory)
# ============================================================================

WHATSAPP_OUTPUT = Path(__file__).parent.parent.parent / "enterprise_output" / "whatsapp-messaging-service_20260211_025459"


@pytest.mark.skipif(
    not WHATSAPP_OUTPUT.exists(),
    reason="WhatsApp enterprise output directory not available"
)
class TestIntegrationWithRealOutput:
    def test_loader_real_output(self):
        """ArtifactLoader should successfully load real output."""
        loader = ArtifactLoader(WHATSAPP_OUTPUT)
        bundle = loader.load_all()

        assert len(bundle.requirements) > 100
        assert len(bundle.user_stories) > 100
        assert len(bundle.epics) > 0
        assert len(bundle.test_cases) > 500
        assert len(bundle.api_endpoints) > 100
        assert len(bundle.entities) > 20
        assert len(bundle.tasks) > 20
        assert len(bundle.state_machines) > 0
        assert len(bundle.diagrams) > 50

    def test_checker_real_output(self):
        """CompletenessChecker should produce meaningful scores on real output."""
        loader = ArtifactLoader(WHATSAPP_OUTPUT)
        bundle = loader.load_all()

        checker = CompletenessChecker()
        report = checker.check_all(bundle)

        # Overall score should be between 0 and 1
        assert 0.0 < report.overall_score < 1.0

        # Should have multiple rule results
        assert len(report.rule_results) == 12

        # Some rules should pass
        passing = [r for r in report.rule_results if r.passed]
        assert len(passing) >= 4  # At least req_to_story, story_to_test, quality_gates, task_backlinks

        # Should have gaps
        assert len(report.all_gaps) > 0

    def test_dry_run_report_saved(self):
        """Dry-run should save report to quality/ directory."""
        import asyncio
        from requirements_engineer.refinement.refinement_loop import RefinementLoop

        loop = RefinementLoop()
        report = asyncio.run(loop.evaluate_only(WHATSAPP_OUTPUT))

        report_path = WHATSAPP_OUTPUT / "quality" / "completeness_report.md"
        assert report_path.exists()

        content = report_path.read_text(encoding="utf-8")
        assert "Overall Score" in content
        assert "Dimension Scores" in content
