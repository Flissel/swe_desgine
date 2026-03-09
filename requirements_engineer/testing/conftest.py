"""
Pytest Configuration and Fixtures for Requirements Engineering Testing.

Provides:
- Sample project fixtures
- Training data collector fixtures
- Stage evaluator fixtures
- Mock LLM fixtures
"""

import pytest
from pathlib import Path
from typing import Dict, Any
import json
import tempfile

# Import training data components
from requirements_engineer.training.collector import TrainingDataCollector
from requirements_engineer.training.live_logger import LiveLogger, EventType, reset_live_logger
from requirements_engineer.training.schemas import StageEvaluationResult

# Import evaluator components
from .stage_evaluators.base_evaluator import EvaluatorConfig
from .stage_evaluators.discovery_evaluator import DiscoveryEvaluator
from .stage_evaluators.analysis_evaluator import AnalysisEvaluator
from .stage_evaluators.specification_evaluator import SpecificationEvaluator
from .stage_evaluators.validation_evaluator import ValidationEvaluator
from .stage_evaluators.presentation_evaluator import PresentationEvaluator


# =============================================================================
# MARKERS
# =============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "real_llm: mark test as requiring real LLM calls (may incur costs)"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test"
    )
    config.addinivalue_line(
        "markers", "stage1: mark test for stage 1 (discovery)"
    )
    config.addinivalue_line(
        "markers", "stage2: mark test for stage 2 (analysis)"
    )
    config.addinivalue_line(
        "markers", "stage3: mark test for stage 3 (specification)"
    )
    config.addinivalue_line(
        "markers", "stage4: mark test for stage 4 (validation)"
    )
    config.addinivalue_line(
        "markers", "stage5: mark test for stage 5 (presentation)"
    )


# =============================================================================
# PROJECT FIXTURES
# =============================================================================

@pytest.fixture(scope="session")
def sample_project_input() -> Dict[str, Any]:
    """Sample project input for testing."""
    return {
        "id": "test_project",
        "Name": "Test E-Commerce Platform",
        "Domain": "E-Commerce",
        "Description": """
        A modern e-commerce platform for online shopping.
        The system should support user registration, product browsing,
        shopping cart management, and secure checkout.
        """,
        "Features": [
            "User authentication and authorization",
            "Product catalog with search and filtering",
            "Shopping cart with quantity management",
            "Secure payment processing",
            "Order tracking and history"
        ],
        "Constraints": [
            "Must comply with PCI-DSS for payment processing",
            "Response time under 2 seconds for all pages",
            "Support for 10,000 concurrent users"
        ],
        "Stakeholders": [
            {"name": "End Users", "role": "Primary users of the platform"},
            {"name": "Admin Users", "role": "Manage products and orders"},
            {"name": "Payment Provider", "role": "External payment integration"}
        ]
    }


@pytest.fixture
def minimal_project_input() -> Dict[str, Any]:
    """Minimal project input for quick tests."""
    return {
        "id": "minimal_test",
        "Name": "Simple Test",
        "Description": "A simple test project",
        "Features": ["Feature 1", "Feature 2"]
    }


# =============================================================================
# JOURNAL FIXTURES
# =============================================================================

@pytest.fixture
def empty_journal():
    """Empty RequirementJournal for testing."""
    try:
        from requirements_engineer.core.re_journal import RequirementJournal
        return RequirementJournal(project_name="Test Project")
    except ImportError:
        # Mock journal if module not available
        class MockJournal:
            project_name = "Test Project"
            stats = {}

            def get_nodes_by_stage(self, stage):
                return []

        return MockJournal()


# =============================================================================
# TRAINING DATA FIXTURES
# =============================================================================

@pytest.fixture
def training_collector(tmp_path):
    """TrainingDataCollector fixture with temp output."""
    TrainingDataCollector.reset()
    collector = TrainingDataCollector.get_instance({
        "output_dir": str(tmp_path / "training_data"),
        "auto_create_samples": True
    })
    yield collector
    TrainingDataCollector.reset()


@pytest.fixture
def live_logger():
    """LiveLogger fixture."""
    reset_live_logger()
    logger = LiveLogger()
    yield logger
    reset_live_logger()


@pytest.fixture
def event_recorder(live_logger):
    """Records all events emitted during test."""
    recorded_events = []

    def callback(event):
        recorded_events.append({
            "type": event.type.value,
            "data": event.data,
            "timestamp": event.timestamp
        })

    live_logger.add_observer(callback)
    yield recorded_events
    live_logger.remove_observer(callback)


# =============================================================================
# EVALUATOR CONFIG FIXTURES
# =============================================================================

@pytest.fixture
def mock_evaluator_config(tmp_path) -> EvaluatorConfig:
    """Evaluator config with mocks enabled."""
    return EvaluatorConfig(
        use_real_llm=False,
        mock_responses_path=str(tmp_path / "mock_responses"),
        quality_thresholds={
            "min_completeness": 0.7,
            "min_consistency": 0.7,
            "min_testability": 0.6,
            "min_clarity": 0.7,
        },
        timeout_seconds=60,
        collect_training_data=True,
        verbose=False
    )


@pytest.fixture
def real_evaluator_config(tmp_path) -> EvaluatorConfig:
    """Evaluator config with real LLM calls."""
    return EvaluatorConfig(
        use_real_llm=True,
        quality_thresholds={
            "min_completeness": 0.8,
            "min_consistency": 0.9,
            "min_testability": 0.75,
            "min_clarity": 0.8,
        },
        timeout_seconds=300,
        collect_training_data=True,
        output_dir=str(tmp_path / "output"),
        verbose=True
    )


# =============================================================================
# STAGE EVALUATOR FIXTURES
# =============================================================================

@pytest.fixture
def discovery_evaluator(mock_evaluator_config) -> DiscoveryEvaluator:
    """Discovery stage evaluator fixture."""
    return DiscoveryEvaluator(mock_evaluator_config)


@pytest.fixture
def analysis_evaluator(mock_evaluator_config) -> AnalysisEvaluator:
    """Analysis stage evaluator fixture."""
    return AnalysisEvaluator(mock_evaluator_config)


@pytest.fixture
def specification_evaluator(mock_evaluator_config) -> SpecificationEvaluator:
    """Specification stage evaluator fixture."""
    return SpecificationEvaluator(mock_evaluator_config)


@pytest.fixture
def validation_evaluator(mock_evaluator_config) -> ValidationEvaluator:
    """Validation stage evaluator fixture."""
    return ValidationEvaluator(mock_evaluator_config)


@pytest.fixture
def presentation_evaluator(mock_evaluator_config) -> PresentationEvaluator:
    """Presentation stage evaluator fixture."""
    return PresentationEvaluator(mock_evaluator_config)


# =============================================================================
# MOCK DATA FIXTURES
# =============================================================================

@pytest.fixture
def mock_requirements():
    """Sample mock requirements data."""
    return [
        {
            "requirement_id": "REQ-001",
            "title": "User Authentication",
            "description": "Users must be able to register and login",
            "type": "functional",
            "priority": "must",
            "acceptance_criteria": [
                "User can register with email",
                "User can login with credentials"
            ]
        },
        {
            "requirement_id": "REQ-002",
            "title": "Product Catalog",
            "description": "Display products with details",
            "type": "functional",
            "priority": "must",
            "acceptance_criteria": [
                "Products are displayed in grid",
                "Product details are visible"
            ]
        }
    ]


@pytest.fixture
def mock_llm_responses(tmp_path):
    """Create mock LLM response files."""
    responses_dir = tmp_path / "mock_responses"
    responses_dir.mkdir(parents=True, exist_ok=True)

    # Discovery response
    discovery_response = {
        "content": json.dumps([
            {
                "title": "Test Requirement",
                "description": "A test requirement",
                "type": "functional",
                "priority": "must"
            }
        ]),
        "prompt_tokens": 100,
        "completion_tokens": 50
    }
    with open(responses_dir / "discovery.json", "w") as f:
        json.dump(discovery_response, f)

    # Analysis response
    analysis_response = {
        "content": json.dumps({
            "classification": "functional",
            "priority": "must"
        }),
        "prompt_tokens": 150,
        "completion_tokens": 40
    }
    with open(responses_dir / "analysis.json", "w") as f:
        json.dump(analysis_response, f)

    return str(responses_dir)


# =============================================================================
# HELPER FIXTURES
# =============================================================================

@pytest.fixture
def temp_output_dir(tmp_path):
    """Temporary output directory."""
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


@pytest.fixture
def assert_valid_evaluation():
    """Helper to assert evaluation result is valid."""
    def _assert(result: StageEvaluationResult):
        assert isinstance(result, StageEvaluationResult)
        assert result.stage_number > 0
        assert result.stage_name != ""
        assert result.duration_ms >= 0
        assert isinstance(result.metrics, dict)
        assert isinstance(result.passed, bool)
        assert 0.0 <= result.quality_score <= 1.0
    return _assert
