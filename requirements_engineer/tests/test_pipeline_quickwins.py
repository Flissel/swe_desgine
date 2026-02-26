"""Tests for pipeline quick wins (4 workstreams)."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ── WS2: Cross-Stage Output Validation ────────────────────────────────────

class TestCrossStageValidation:
    """Tests for _validate_stage_output() helper."""

    def _validate(self, stage_key, context, manifest=None):
        from requirements_engineer.run_re_system import _validate_stage_output
        return _validate_stage_output(stage_key, context, manifest)

    def test_valid_requirements_returns_true(self):
        assert self._validate(3, {"requirements": [1, 2, 3]}) is True

    def test_empty_requirements_returns_false(self):
        assert self._validate(3, {"requirements": []}) is False

    def test_none_ux_spec_returns_false(self):
        assert self._validate(9, {"ux_spec": None}) is False

    def test_valid_ux_spec_returns_true(self):
        assert self._validate(9, {"ux_spec": MagicMock()}) is True

    def test_unknown_stage_returns_true(self):
        assert self._validate(999, {"whatever": None}) is True

    def test_data_dict_with_entities_valid(self):
        dd = MagicMock()
        dd.entities = {"user": {}, "message": {}}
        assert self._validate("12a", {"data_dict": dd}) is True

    def test_data_dict_none_invalid(self):
        assert self._validate("12a", {"data_dict": None}) is False

    def test_annotates_manifest_stage(self):
        from requirements_engineer.core.pipeline_manifest import PipelineManifest
        manifest = PipelineManifest.__new__(PipelineManifest)
        manifest.stages = []

        # Add a fake completed stage
        from requirements_engineer.core.pipeline_manifest import StageRecord
        stage = StageRecord(step=3, name="discovery", description="test", status="completed")
        manifest.stages.append(stage)

        result = self._validate(3, {"requirements": []}, manifest)
        assert result is False
        assert stage.quality_gate is not None
        assert stage.quality_gate["output_validation"] == "empty"
        assert stage.quality_gate["missing_output"] == "requirements"


# ── WS4: Pipeline Manifest Validation ─────────────────────────────────────

class TestManifestValidation:
    """Tests for PipelineManifest.validate_prerequisites()."""

    def _make_manifest(self, stages):
        from requirements_engineer.core.pipeline_manifest import PipelineManifest, StageRecord
        m = PipelineManifest.__new__(PipelineManifest)
        m.stages = stages
        return m

    def _make_stage(self, name, step, status="completed", outputs=None):
        from requirements_engineer.core.pipeline_manifest import StageRecord
        s = StageRecord(step=step, name=name, description="test", status=status)
        s.outputs = outputs or []
        return s

    def test_all_outputs_present_no_warnings(self):
        stages = [
            self._make_stage("discovery", 3, outputs=[{"name": "requirements", "count": 126}]),
            self._make_stage("user_stories", 5, outputs=[{"name": "user_stories", "count": 50}]),
        ]
        m = self._make_manifest(stages)
        warnings = m.validate_prerequisites()
        assert len(warnings) == 0

    def test_empty_discovery_warns(self):
        stages = [
            self._make_stage("discovery", 3, outputs=[{"name": "requirements", "count": 0}]),
        ]
        m = self._make_manifest(stages)
        warnings = m.validate_prerequisites()
        assert len(warnings) == 1
        assert warnings[0]["stage"] == "discovery"
        assert "requirements" in warnings[0]["warning"]

    def test_skipped_stage_ignored(self):
        stages = [
            self._make_stage("discovery", 3, status="skipped", outputs=[]),
        ]
        m = self._make_manifest(stages)
        warnings = m.validate_prerequisites()
        assert len(warnings) == 0

    def test_missing_output_name_warns(self):
        stages = [
            self._make_stage("discovery", 3, outputs=[{"name": "something_else", "count": 10}]),
        ]
        m = self._make_manifest(stages)
        warnings = m.validate_prerequisites()
        assert len(warnings) == 1

    def test_zero_count_warns(self):
        stages = [
            self._make_stage("api_spec", "11a", outputs=[{"name": "api_endpoints", "count": 0}]),
        ]
        m = self._make_manifest(stages)
        warnings = m.validate_prerequisites()
        assert len(warnings) == 1
        assert "api_endpoints" in warnings[0]["warning"]


# ── WS3: Master Document Orphan Metrics ───────────────────────────────────

class TestMasterDocOrphanMetrics:
    """Tests for create_master_document with orphan generator params."""

    def _create_doc(self, **kwargs):
        from requirements_engineer.run_re_system import create_master_document
        defaults = {
            "project_name": "test-project",
            "output_dir": Path(tempfile.mkdtemp()),
            "requirements_count": 10,
            "user_stories_count": 8,
            "test_cases_count": 15,
        }
        defaults.update(kwargs)
        return create_master_document(**defaults)

    def test_includes_arch_services_count(self):
        md = self._create_doc(arch_services_count=17)
        assert "Architecture Services" in md
        assert "17" in md

    def test_includes_state_machines_count(self):
        md = self._create_doc(state_machines_count=8)
        assert "State Machines" in md
        assert "8" in md

    def test_includes_compositions_count(self):
        md = self._create_doc(compositions_count=24)
        assert "Component Compositions" in md
        assert "24" in md

    def test_includes_factory_count(self):
        md = self._create_doc(factory_count=48)
        assert "Test Factories" in md
        assert "48" in md

    def test_zero_counts_omitted(self):
        md = self._create_doc()
        # Metrics table rows should not appear for zero counts
        # (ToC links are always present, so check the table row marker)
        assert "| Architecture Services |" not in md
        assert "| State Machines |" not in md
        assert "| Component Compositions |" not in md
        assert "| Test Factories |" not in md

    def test_toc_has_architecture_link(self):
        md = self._create_doc()
        assert "Architecture Design" in md
        assert "architecture/architecture_overview.md" in md

    def test_toc_has_infrastructure_link(self):
        md = self._create_doc()
        assert "Infrastructure" in md
        assert "infrastructure/docker-compose.yml" in md

    def test_toc_has_test_factories_link(self):
        md = self._create_doc()
        assert "Test Factories" in md or "testing/factories/" in md
        assert "testing/factories/" in md


# ── WS3c: Traceability SM Flag ────────────────────────────────────────────

class TestTraceabilitySmFlag:
    """Tests for [SM] flag in traceability matrix entity column."""

    def _make_req(self, req_id, title="Test Req"):
        from requirements_engineer.core.re_journal import RequirementNode
        return RequirementNode(requirement_id=req_id, title=title, type="functional", priority="must")

    def _make_story(self, us_id, parent_req):
        from requirements_engineer.generators.user_story_generator import UserStory
        return UserStory(id=us_id, title="Story", persona="user", action="act", benefit="benefit",
                         parent_requirement_id=parent_req)

    def _make_tc(self, tc_id, parent_us):
        from requirements_engineer.generators.test_case_generator import TestCase
        return TestCase(id=tc_id, title="Test", description="desc", steps=[], expected_result="result",
                        parent_user_story_id=parent_us)

    def _make_sm(self, entity):
        sm = MagicMock()
        sm.entity = entity
        return sm

    def _make_endpoint(self, method, path, parent_req):
        ep = MagicMock()
        ep.method = method
        ep.path = path
        ep.parent_requirement_id = parent_req
        return ep

    def test_entity_with_state_machine_gets_flag(self):
        from requirements_engineer.run_re_system import create_traceability_matrix
        from types import SimpleNamespace

        reqs = [self._make_req("REQ-001", "User authentication")]
        stories = [self._make_story("US-001", "REQ-001")]
        tests = [self._make_tc("TC-001", "US-001")]
        eps = [self._make_endpoint("POST", "/api/v1/users", "REQ-001")]
        # MagicMock(name=...) sets _mock_name, not .name — use SimpleNamespace
        user_entity = SimpleNamespace(name="user")
        entities = {"user": user_entity}
        state_machines = [self._make_sm("user")]

        md = create_traceability_matrix(reqs, stories, tests, api_endpoints=eps,
                                         entities=entities, state_machines=state_machines)
        assert "[SM]" in md

    def test_entity_without_sm_no_flag(self):
        from requirements_engineer.run_re_system import create_traceability_matrix
        from types import SimpleNamespace

        reqs = [self._make_req("REQ-001", "User auth")]
        stories = [self._make_story("US-001", "REQ-001")]
        tests = [self._make_tc("TC-001", "US-001")]
        eps = [self._make_endpoint("GET", "/api/v1/users", "REQ-001")]
        user_entity = SimpleNamespace(name="user")
        entities = {"user": user_entity}

        md = create_traceability_matrix(reqs, stories, tests, api_endpoints=eps,
                                         entities=entities, state_machines=[])
        assert "[SM]" not in md

    def test_empty_state_machines_no_flags(self):
        from requirements_engineer.run_re_system import create_traceability_matrix

        reqs = [self._make_req("REQ-001")]
        stories = []
        tests = []

        md = create_traceability_matrix(reqs, stories, tests, state_machines=None)
        assert "[SM]" not in md


# ── WS1: Tree Search Config ──────────────────────────────────────────────

class TestTreeSearchConfig:
    """Tests for tree search config."""

    def test_treesearch_enabled_in_config(self):
        from omegaconf import OmegaConf
        config = OmegaConf.load(str(Path(__file__).parent.parent / "re_config.yaml"))
        assert config.treesearch.enabled is True

    def test_treesearch_max_calls_capped(self):
        from omegaconf import OmegaConf
        config = OmegaConf.load(str(Path(__file__).parent.parent / "re_config.yaml"))
        assert config.treesearch.max_total_llm_calls <= 100
        assert config.treesearch.max_total_llm_calls > 0

    def test_treesearch_quality_thresholds_set(self):
        from omegaconf import OmegaConf
        config = OmegaConf.load(str(Path(__file__).parent.parent / "re_config.yaml"))
        assert config.treesearch.quality_threshold > 0
        assert config.treesearch.requirement.quality_threshold > 0
        assert config.treesearch.user_story.quality_threshold > 0
        assert config.treesearch.test_case.quality_threshold > 0
