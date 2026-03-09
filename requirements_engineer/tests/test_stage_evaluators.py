"""
Tests for Stage Evaluators.

Tests each stage evaluator:
- DiscoveryEvaluator (Stage 1)
- AnalysisEvaluator (Stage 2)
- SpecificationEvaluator (Stage 3)
- ValidationEvaluator (Stage 4)
- PresentationEvaluator (Stage 5)
"""

import pytest
from pathlib import Path

from requirements_engineer.testing.stage_evaluators import (
    BaseStageEvaluator,
    EvaluatorConfig,
    DiscoveryEvaluator,
    AnalysisEvaluator,
    SpecificationEvaluator,
    ValidationEvaluator,
    PresentationEvaluator,
)
from requirements_engineer.training.schemas import StageEvaluationResult


@pytest.fixture
def mock_config(tmp_path) -> EvaluatorConfig:
    """Mock evaluator configuration."""
    return EvaluatorConfig(
        use_real_llm=False,
        quality_thresholds={
            "min_completeness": 0.5,
            "min_consistency": 0.5,
            "min_testability": 0.5,
            "min_clarity": 0.5,
        },
        timeout_seconds=30,
        collect_training_data=False,
        verbose=False
    )


@pytest.fixture
def sample_project():
    """Sample project input."""
    return {
        "id": "test_project",
        "Name": "Test Project",
        "Description": "A test project for evaluation",
        "Features": ["Feature 1", "Feature 2"],
    }


@pytest.fixture
def mock_journal():
    """Mock journal object."""
    class MockJournal:
        project_name = "Test Project"
        stats = {}

        def get_nodes_by_stage(self, stage):
            return []

    return MockJournal()


class TestDiscoveryEvaluator:
    """Tests for Discovery stage evaluator."""

    def test_initialization(self, mock_config):
        """Test evaluator initialization."""
        evaluator = DiscoveryEvaluator(mock_config)
        assert evaluator.stage_number == 1
        assert evaluator.stage_name == "discovery"

    def test_mock_execution(self, mock_config, sample_project, mock_journal):
        """Test mock execution returns valid results."""
        evaluator = DiscoveryEvaluator(mock_config)
        result = evaluator.evaluate(sample_project, mock_journal)

        assert isinstance(result, StageEvaluationResult)
        assert result.stage_number == 1
        assert result.stage_name == "discovery"
        assert result.duration_ms >= 0

    def test_validate_output(self, mock_config):
        """Test output validation."""
        evaluator = DiscoveryEvaluator(mock_config)

        mock_output = [
            {"title": "Req 1", "description": "Desc", "type": "functional", "priority": "must"},
            {"title": "Req 2", "description": "Desc", "type": "non_functional", "priority": "should"},
        ]

        metrics = evaluator.validate_output(mock_output)
        assert "completeness" in metrics
        assert "field_coverage" in metrics
        assert metrics["field_coverage"] == 1.0

    def test_empty_output(self, mock_config):
        """Test validation of empty output."""
        evaluator = DiscoveryEvaluator(mock_config)
        metrics = evaluator.validate_output([])
        assert metrics["completeness"] == 0.0


class TestAnalysisEvaluator:
    """Tests for Analysis stage evaluator."""

    def test_initialization(self, mock_config):
        """Test evaluator initialization."""
        evaluator = AnalysisEvaluator(mock_config)
        assert evaluator.stage_number == 2
        assert evaluator.stage_name == "analysis"

    def test_mock_execution(self, mock_config, sample_project, mock_journal):
        """Test mock execution."""
        evaluator = AnalysisEvaluator(mock_config)
        result = evaluator.evaluate(sample_project, mock_journal)

        assert isinstance(result, StageEvaluationResult)
        assert result.stage_number == 2

    def test_validate_output(self, mock_config):
        """Test output validation."""
        evaluator = AnalysisEvaluator(mock_config)

        mock_output = [
            {"type": "functional", "priority": "must", "dependencies": ["REQ-001"]},
            {"type": "non_functional", "priority": "should", "dependencies": []},
        ]

        metrics = evaluator.validate_output(mock_output)
        assert "classification" in metrics
        assert "prioritization" in metrics
        assert metrics["classification"] == 1.0
        assert metrics["prioritization"] == 1.0


class TestSpecificationEvaluator:
    """Tests for Specification stage evaluator."""

    def test_initialization(self, mock_config):
        """Test evaluator initialization."""
        evaluator = SpecificationEvaluator(mock_config)
        assert evaluator.stage_number == 3
        assert evaluator.stage_name == "specification"

    def test_mock_execution(self, mock_config, sample_project, mock_journal):
        """Test mock execution."""
        evaluator = SpecificationEvaluator(mock_config)
        result = evaluator.evaluate(sample_project, mock_journal)

        assert isinstance(result, StageEvaluationResult)
        assert result.stage_number == 3

    def test_validate_output(self, mock_config):
        """Test output validation with diagrams."""
        evaluator = SpecificationEvaluator(mock_config)

        mock_output = [
            {
                "acceptance_criteria": ["Criterion 1", "Criterion 2"],
                "mermaid_diagrams": {"flowchart": "graph TD\n    A-->B"},
                "work_package": "Feature 1"
            },
        ]

        metrics = evaluator.validate_output(mock_output)
        assert "testability" in metrics
        assert "diagram_coverage" in metrics
        assert metrics["testability"] == 1.0
        assert metrics["diagram_coverage"] == 1.0


class TestValidationEvaluator:
    """Tests for Validation stage evaluator."""

    def test_initialization(self, mock_config):
        """Test evaluator initialization."""
        evaluator = ValidationEvaluator(mock_config)
        assert evaluator.stage_number == 4
        assert evaluator.stage_name == "validation"

    def test_mock_execution(self, mock_config, sample_project, mock_journal):
        """Test mock execution."""
        evaluator = ValidationEvaluator(mock_config)
        result = evaluator.evaluate(sample_project, mock_journal)

        assert isinstance(result, StageEvaluationResult)
        assert result.stage_number == 4

    def test_validate_output(self, mock_config):
        """Test output validation with quality scores."""
        evaluator = ValidationEvaluator(mock_config)

        mock_output = [
            {
                "validation_status": "validated",
                "completeness_score": 0.9,
                "consistency_score": 0.85,
                "testability_score": 0.88,
                "clarity_score": 0.92,
                "feasibility_score": 0.8,
                "traceability_score": 0.87,
                "quality_issues": [],
                "is_valid": True
            },
        ]

        metrics = evaluator.validate_output(mock_output)
        assert "validation_coverage" in metrics
        assert "completeness" in metrics
        assert metrics["validation_coverage"] == 1.0


class TestPresentationEvaluator:
    """Tests for Presentation stage evaluator."""

    def test_initialization(self, mock_config):
        """Test evaluator initialization."""
        evaluator = PresentationEvaluator(mock_config)
        assert evaluator.stage_number == 5
        assert evaluator.stage_name == "presentation"

    def test_mock_execution(self, mock_config, sample_project, mock_journal):
        """Test mock execution."""
        evaluator = PresentationEvaluator(mock_config)
        result = evaluator.evaluate(sample_project, mock_journal)

        assert isinstance(result, StageEvaluationResult)
        assert result.stage_number == 5

    def test_validate_output(self, mock_config):
        """Test output validation with pages."""
        evaluator = PresentationEvaluator(mock_config)

        mock_output = {
            "pages": [
                {
                    "name": "index.html",
                    "content_length": 5000,
                    "has_navigation": True,
                    "has_mermaid": True,
                    "accessibility_score": 0.85
                },
                {
                    "name": "requirements.html",
                    "content_length": 8000,
                    "has_navigation": True,
                    "has_mermaid": False,
                    "accessibility_score": 0.80
                }
            ],
            "quality_score": 0.85
        }

        metrics = evaluator.validate_output(mock_output)
        assert "page_coverage" in metrics
        assert "navigation" in metrics
        assert "accessibility" in metrics


class TestEvaluatorConfig:
    """Tests for EvaluatorConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = EvaluatorConfig()
        assert config.use_real_llm is False
        assert config.timeout_seconds == 300
        assert "min_completeness" in config.quality_thresholds

    def test_custom_thresholds(self):
        """Test custom quality thresholds."""
        config = EvaluatorConfig(
            quality_thresholds={"min_custom": 0.9}
        )
        assert config.quality_thresholds["min_custom"] == 0.9


class TestStageEvaluationResult:
    """Tests for StageEvaluationResult."""

    def test_quality_score_calculation(self):
        """Test automatic quality score calculation."""
        result = StageEvaluationResult(
            stage_number=1,
            stage_name="discovery",
            metrics={"completeness": 0.8, "consistency": 0.9}
        )
        # Quality score calculated in __post_init__ (allow floating point tolerance)
        assert abs(result.quality_score - 0.85) < 0.001

    def test_passed_with_issues(self):
        """Test result with issues."""
        result = StageEvaluationResult(
            stage_number=1,
            stage_name="discovery",
            passed=False,
            issues_found=["Low completeness score"]
        )
        assert result.passed is False
        assert len(result.issues_found) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
