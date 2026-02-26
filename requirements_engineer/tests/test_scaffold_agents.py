"""
Tests for Project Scaffold Agents.

Tests use real LLM calls via OpenRouter backend.
Requires OPENROUTER_API_KEY environment variable.
"""

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

# Load .env file if present (for OPENROUTER_API_KEY)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Skip all tests if no API key
HAS_API_KEY = bool(os.environ.get("OPENROUTER_API_KEY"))
skip_no_key = pytest.mark.skipif(
    not HAS_API_KEY, reason="OPENROUTER_API_KEY not set"
)

from requirements_engineer.stages.agents.project_scaffold_agent import (
    ProjectScaffoldAgent,
    slugify,
)
from requirements_engineer.stages.agents.scaffold_reviewer_agent import (
    ScaffoldReviewerAgent,
)
from requirements_engineer.stages.agents.scaffold_improver_agent import (
    ScaffoldImproverAgent,
)
from requirements_engineer.stages.orchestrator.scaffold_orchestrator import (
    ScaffoldOrchestrator,
)
from requirements_engineer.stages.agents.base_presentation_agent import (
    PresentationContext,
    AgentRole,
    AgentCapability,
)
from requirements_engineer.stages.orchestrator.presentation_ledger import (
    ActionType,
)


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture
def tmp_project_dir():
    """Create a temporary project directory with sample artifacts."""
    tmpdir = tempfile.mkdtemp(prefix="scaffold_test_")
    project_dir = Path(tmpdir)

    # Create sample epics.json
    epics = [
        {"id": "EPIC-001", "name": "User Authentication", "description": "Handle user login, registration, and session management"},
        {"id": "EPIC-002", "name": "Product Catalog", "description": "Manage product listings, search, and filtering"},
        {"id": "EPIC-003", "name": "Order Management", "description": "Handle shopping cart, checkout, and order tracking"},
    ]
    (project_dir / "epics.json").write_text(json.dumps(epics, indent=2), encoding="utf-8")

    # Create sample tech_stack.json
    tech_stack = {
        "architecture_pattern": "Microservices",
        "backend_framework": "FastAPI",
        "frontend_framework": "React",
        "database": "PostgreSQL",
        "ci_cd": "GitHub Actions",
        "containerization": "Docker",
        "programming_language": "Python",
    }
    (project_dir / "tech_stack.json").write_text(json.dumps(tech_stack, indent=2), encoding="utf-8")

    # Create sample feature_breakdown.json
    features = {
        "features": [
            {"id": "F-001", "name": "Login", "epic_id": "EPIC-001"},
            {"id": "F-002", "name": "Registration", "epic_id": "EPIC-001"},
            {"id": "F-003", "name": "Product Search", "epic_id": "EPIC-002"},
            {"id": "F-004", "name": "Shopping Cart", "epic_id": "EPIC-003"},
        ]
    }
    (project_dir / "feature_breakdown.json").write_text(json.dumps(features, indent=2), encoding="utf-8")

    # Create sample user_stories.json
    stories = [
        {"id": "US-001", "title": "As a user I want to login", "epic_id": "EPIC-001"},
        {"id": "US-002", "title": "As a user I want to search products", "epic_id": "EPIC-002"},
    ]
    (project_dir / "user_stories.json").write_text(json.dumps(stories, indent=2), encoding="utf-8")

    # Create sample diagrams
    diagrams_dir = project_dir / "diagrams"
    diagrams_dir.mkdir()
    (diagrams_dir / "REQ-001_flowchart.mmd").write_text("graph TD\n  A-->B", encoding="utf-8")
    (diagrams_dir / "REQ-002_sequence.mmd").write_text("sequenceDiagram\n  A->>B: Hello", encoding="utf-8")

    # Create sample requirements.md
    (project_dir / "requirements.md").write_text(
        "# Requirements\n\n## REQ-001\nUser authentication system\n",
        encoding="utf-8",
    )

    yield project_dir

    # Cleanup
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def scaffold_context(tmp_project_dir):
    """Create a PresentationContext for scaffold testing."""
    return PresentationContext(
        project_id="test-ecommerce",
        output_dir=str(tmp_project_dir),
        artifact_stats={
            "epics": 3,
            "requirements": 1,
            "user_stories": 2,
            "diagrams": 2,
        },
        quality_threshold=0.85,
        config={
            "scaffold": {
                "output_dir": "project_scaffold",
                "structure_strategy": "auto",
            }
        },
    )


# ======================================================================
# Unit Tests (no LLM required)
# ======================================================================

class TestSlugify:
    """Test the slugify utility."""

    def test_basic(self):
        assert slugify("Hello World") == "hello-world"

    def test_special_chars(self):
        assert slugify("User Auth & Login!") == "user-auth-login"

    def test_underscores(self):
        assert slugify("order_management") == "order-management"

    def test_empty(self):
        assert slugify("") == ""


class TestEnumExtensions:
    """Test that new enum values exist."""

    def test_agent_roles(self):
        assert AgentRole.PROJECT_SCAFFOLD is not None
        assert AgentRole.SCAFFOLD_REVIEWER is not None
        assert AgentRole.SCAFFOLD_IMPROVER is not None

    def test_agent_capabilities(self):
        assert AgentCapability.SCAFFOLD_GENERATION is not None
        assert AgentCapability.FILE_PLACEMENT is not None

    def test_action_types(self):
        assert ActionType.GENERATE_SCAFFOLD is not None
        assert ActionType.REVIEW_SCAFFOLD is not None
        assert ActionType.IMPROVE_SCAFFOLD is not None
        assert ActionType.PLACE_DOCUMENTS is not None


class TestProjectScaffoldAgentInit:
    """Test ProjectScaffoldAgent initialization."""

    def test_init_default(self):
        agent = ProjectScaffoldAgent(config={})
        assert agent.name == "ProjectScaffold"
        assert agent.role == AgentRole.PROJECT_SCAFFOLD
        assert AgentCapability.SCAFFOLD_GENERATION in agent.capabilities

    def test_init_with_config(self):
        cfg = {"model": "test-model", "scaffold": {"output_dir": "custom"}}
        agent = ProjectScaffoldAgent(config=cfg)
        assert agent.model == "test-model"
        assert agent.scaffold_config["output_dir"] == "custom"


class TestScaffoldReviewerAgentInit:
    """Test ScaffoldReviewerAgent initialization."""

    def test_init_default(self):
        agent = ScaffoldReviewerAgent(config={})
        assert agent.name == "ScaffoldReviewer"
        assert agent.role == AgentRole.SCAFFOLD_REVIEWER

    def test_quality_targets(self):
        cfg = {"quality_targets": {"epic_coverage": 0.99}}
        agent = ScaffoldReviewerAgent(config=cfg)
        assert agent.targets["epic_coverage"] == 0.99


class TestScaffoldImproverAgentInit:
    """Test ScaffoldImproverAgent initialization."""

    def test_init_default(self):
        agent = ScaffoldImproverAgent(config={})
        assert agent.name == "ScaffoldImprover"
        assert agent.role == AgentRole.SCAFFOLD_IMPROVER


class TestScaffoldReviewerNoScaffold:
    """Test ScaffoldReviewer when scaffold doesn't exist."""

    def test_missing_scaffold_dir(self, scaffold_context):
        agent = ScaffoldReviewerAgent(config={})
        result = asyncio.get_event_loop().run_until_complete(
            agent.execute(scaffold_context)
        )
        assert not result.success
        assert "not found" in result.error_message


class TestScaffoldReviewerWithManualScaffold:
    """Test ScaffoldReviewer with manually created scaffold."""

    def test_review_basic_scaffold(self, tmp_project_dir, scaffold_context):
        scaffold_dir = tmp_project_dir / "project_scaffold"
        scaffold_dir.mkdir()

        # Create minimal scaffold
        (scaffold_dir / "README.md").write_text("# Test Project\n", encoding="utf-8")
        (scaffold_dir / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
        (scaffold_dir / "src").mkdir()
        (scaffold_dir / "src" / "services").mkdir()

        # Create manifest
        manifest = {
            "project_name": "test",
            "structure_strategy": "service_based",
            "epic_mapping": {
                "EPIC-001": "src/services/auth-service",
            },
            "statistics": {"directories_created": 3, "files_created": 2, "docs_placed": 0},
            "created_directories": [],
            "created_files": [],
            "placed_documents": [],
        }
        (scaffold_dir / "scaffold_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

        # Create mapped directory
        (scaffold_dir / "src" / "services" / "auth-service").mkdir(parents=True)

        agent = ScaffoldReviewerAgent(config={})
        result = asyncio.get_event_loop().run_until_complete(
            agent.execute(scaffold_context)
        )

        assert result.success
        assert result.quality_score > 0
        # Should have issues since not all epics are covered
        assert len(result.quality_issues) > 0


class TestScaffoldImproverWithIssues:
    """Test ScaffoldImprover with known issues."""

    def test_fix_missing_readme(self, tmp_project_dir, scaffold_context):
        scaffold_dir = tmp_project_dir / "project_scaffold"
        scaffold_dir.mkdir()

        # Create manifest
        (scaffold_dir / "scaffold_manifest.json").write_text(
            json.dumps({"improvements_applied": []}), encoding="utf-8"
        )

        # Set up issues in context
        scaffold_context.quality_issues = [
            {
                "severity": "major",
                "dimension": "config_completeness",
                "description": "Missing required config: README.md",
                "fix_hint": "Generate README.md",
            }
        ]

        agent = ScaffoldImproverAgent(config={})
        result = asyncio.get_event_loop().run_until_complete(
            agent.execute(scaffold_context)
        )

        assert result.success
        assert len(result.improvements_applied) > 0
        assert (scaffold_dir / "README.md").exists()


class TestScaffoldOrchestratorInit:
    """Test ScaffoldOrchestrator initialization."""

    def test_init_default(self):
        orch = ScaffoldOrchestrator(config={})
        assert "project_scaffold" in orch.agents
        assert "scaffold_reviewer" in orch.agents
        assert "scaffold_improver" in orch.agents

    def test_init_with_config(self):
        cfg = {
            "orchestrator": {"max_iterations": 2, "target_quality": 0.9},
            "agents": {},
            "quality_targets": {},
        }
        orch = ScaffoldOrchestrator(config=cfg)
        assert orch.max_iterations == 2
        assert orch.target_quality == 0.9


# ======================================================================
# Integration Tests (require LLM / API key)
# ======================================================================

@skip_no_key
class TestProjectScaffoldAgentLLM:
    """Integration test: ProjectScaffoldAgent with real LLM."""

    def test_generate_scaffold(self, tmp_project_dir, scaffold_context):
        cfg = {
            "model": "google/gemini-3-flash-preview",
            "temperature": 0.3,
            "max_tokens": 8000,
            "scaffold": {
                "output_dir": "project_scaffold",
                "structure_strategy": "auto",
            },
        }
        agent = ProjectScaffoldAgent(config=cfg)
        result = asyncio.get_event_loop().run_until_complete(
            agent.execute(scaffold_context)
        )

        assert result.success, f"Scaffold generation failed: {result.error_message}"

        scaffold_dir = tmp_project_dir / "project_scaffold"
        assert scaffold_dir.exists(), "Scaffold directory was not created"

        # Check manifest exists
        manifest_path = scaffold_dir / "scaffold_manifest.json"
        assert manifest_path.exists(), "scaffold_manifest.json not created"

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "structure_strategy" in manifest
        assert manifest["statistics"]["directories_created"] > 0

        # Check at least some directories were created
        dirs = [d for d in scaffold_dir.rglob("*") if d.is_dir()]
        assert len(dirs) > 3, f"Expected >3 directories, got {len(dirs)}"

        # Check at least one README exists
        readmes = list(scaffold_dir.rglob("README.md"))
        assert len(readmes) > 0, "No README.md files created"


@skip_no_key
class TestScaffoldOrchestratorLLM:
    """Integration test: Full orchestrator with real LLM."""

    def test_full_run(self, tmp_project_dir):
        cfg = {
            "orchestrator": {
                "max_iterations": 2,
                "stagnation_threshold": 2,
                "max_replans": 1,
                "target_quality": 0.70,
            },
            "agents": {
                "project_scaffold": {
                    "model": "google/gemini-3-flash-preview",
                    "temperature": 0.3,
                    "max_tokens": 8000,
                },
                "scaffold_reviewer": {
                    "model": "google/gemini-3-flash-preview",
                    "temperature": 0.3,
                    "max_tokens": 4000,
                },
                "scaffold_improver": {
                    "model": "google/gemini-3-flash-preview",
                    "temperature": 0.3,
                    "max_tokens": 4000,
                },
            },
            "quality_targets": {
                "epic_coverage": 0.80,
                "doc_placement": 0.70,
                "structure_sanity": 0.80,
                "config_completeness": 0.60,
                "naming_consistency": 0.80,
            },
        }

        orch = ScaffoldOrchestrator(config=cfg)
        result = asyncio.get_event_loop().run_until_complete(
            orch.run(
                project_id="test-ecommerce",
                project_name="E-Commerce Platform",
                output_dir=str(tmp_project_dir),
                artifact_stats={"epics": 3, "diagrams": 2},
            )
        )

        assert result["success"], f"Orchestrator failed: {result.get('error')}"
        assert result["iterations_completed"] >= 1

        scaffold_dir = tmp_project_dir / "project_scaffold"
        assert scaffold_dir.exists()

        # Check manifest
        manifest = scaffold_dir / "scaffold_manifest.json"
        assert manifest.exists()

        # Check some structure was created
        dirs = [d for d in scaffold_dir.rglob("*") if d.is_dir()]
        assert len(dirs) > 2
