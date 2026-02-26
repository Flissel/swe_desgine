"""
Tests for Screen Design Agents (Stage 5 Phase 3).

Unit tests run without LLM.
Integration tests require OPENROUTER_API_KEY.
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

# Skip all LLM tests if no API key
HAS_API_KEY = bool(os.environ.get("OPENROUTER_API_KEY"))
skip_no_key = pytest.mark.skipif(
    not HAS_API_KEY, reason="OPENROUTER_API_KEY not set"
)

from requirements_engineer.stages.agents.screen_generator_agent import (
    ScreenGeneratorAgent,
)
from requirements_engineer.stages.agents.screen_reviewer_agent import (
    ScreenReviewerAgent,
)
from requirements_engineer.stages.agents.screen_improver_agent import (
    ScreenImproverAgent,
)
from requirements_engineer.stages.orchestrator.screen_design_orchestrator import (
    ScreenDesignOrchestrator,
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
    """Create a temporary project directory with sample UI artifacts."""
    tmpdir = tempfile.mkdtemp(prefix="screen_test_")
    project_dir = Path(tmpdir)

    # Create sample user_stories.json
    stories = [
        {"id": "US-001", "title": "As a user I want to login", "epic_id": "EPIC-001",
         "description": "User enters email and password to authenticate"},
        {"id": "US-002", "title": "As a user I want to view dashboard", "epic_id": "EPIC-001",
         "description": "User sees overview of key metrics after login"},
        {"id": "US-003", "title": "As a user I want to manage products", "epic_id": "EPIC-002",
         "description": "User can list, add, edit and delete products"},
    ]
    (project_dir / "user_stories.json").write_text(json.dumps(stories, indent=2), encoding="utf-8")

    # Create sample epics.json
    epics = [
        {"id": "EPIC-001", "name": "User Management", "description": "Auth and user profiles"},
        {"id": "EPIC-002", "name": "Product Catalog", "description": "Product CRUD"},
    ]
    (project_dir / "epics.json").write_text(json.dumps(epics, indent=2), encoding="utf-8")

    # Create sample ui_spec.json with components
    ui_dir = project_dir / "ui_design"
    ui_dir.mkdir()
    screens_dir = ui_dir / "screens"
    screens_dir.mkdir()

    ui_spec = {
        "project_name": "Test E-Commerce",
        "components": [
            {"id": "COMP-001", "name": "Button", "component_type": "button"},
            {"id": "COMP-002", "name": "Input", "component_type": "input"},
            {"id": "COMP-003", "name": "Card", "component_type": "card"},
            {"id": "COMP-004", "name": "DataTable", "component_type": "table"},
            {"id": "COMP-005", "name": "NavBar", "component_type": "navigation"},
            {"id": "COMP-006", "name": "Modal", "component_type": "modal"},
        ],
        "screens": [],
        "design_tokens": {},
    }
    (ui_dir / "ui_spec.json").write_text(json.dumps(ui_spec, indent=2), encoding="utf-8")

    # Create sample ux_spec.json
    ux_dir = project_dir / "ux_design"
    ux_dir.mkdir()
    ux_spec = {
        "information_architecture": [
            {"name": "Login Page", "path": "/login", "content_types": ["form", "auth"]},
            {"name": "Dashboard", "path": "/dashboard", "content_types": ["metrics", "charts"]},
            {"name": "Product List", "path": "/products", "content_types": ["table", "filters"]},
        ],
    }
    (ux_dir / "ux_spec.json").write_text(json.dumps(ux_spec, indent=2), encoding="utf-8")

    yield project_dir

    # Cleanup
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def screen_context(tmp_project_dir):
    """Create a PresentationContext for screen testing."""
    return PresentationContext(
        project_id="test-ecommerce",
        output_dir=str(tmp_project_dir),
        artifact_stats={
            "user_stories": 3,
            "epics": 2,
            "components": 6,
        },
        quality_threshold=0.80,
    )


# ======================================================================
# Unit Tests: Enum Values
# ======================================================================

class TestScreenEnumValues:
    """Test that new enum values exist."""

    def test_agent_roles(self):
        assert AgentRole.SCREEN_GENERATOR is not None
        assert AgentRole.SCREEN_REVIEWER is not None
        assert AgentRole.SCREEN_IMPROVER is not None

    def test_agent_capabilities(self):
        assert AgentCapability.SCREEN_GENERATION is not None
        assert AgentCapability.SCREEN_REVIEW is not None

    def test_action_types(self):
        assert ActionType.GENERATE_SCREEN is not None
        assert ActionType.REVIEW_SCREEN is not None
        assert ActionType.IMPROVE_SCREEN is not None
        assert ActionType.SAVE_SCREEN_FILES is not None


# ======================================================================
# Unit Tests: Agent Initialization
# ======================================================================

class TestScreenGeneratorAgentInit:
    """Test ScreenGeneratorAgent initialization."""

    def test_init_default(self):
        agent = ScreenGeneratorAgent(config={})
        assert agent.name == "ScreenGenerator"
        assert agent.role == AgentRole.SCREEN_GENERATOR
        assert AgentCapability.SCREEN_GENERATION in agent.capabilities

    def test_init_with_config(self):
        cfg = {"model": "test-model", "max_screens": 4}
        agent = ScreenGeneratorAgent(config=cfg)
        assert agent.model == "test-model"
        assert agent.max_screens == 4


class TestScreenReviewerAgentInit:
    """Test ScreenReviewerAgent initialization."""

    def test_init_default(self):
        agent = ScreenReviewerAgent(config={})
        assert agent.name == "ScreenReviewer"
        assert agent.role == AgentRole.SCREEN_REVIEWER
        assert AgentCapability.SCREEN_REVIEW in agent.capabilities

    def test_quality_targets(self):
        cfg = {"quality_targets": {"wireframe_quality": 0.99}}
        agent = ScreenReviewerAgent(config=cfg)
        assert agent.targets["wireframe_quality"] == 0.99
        # Default targets should still be present
        assert agent.targets["component_coverage"] == 0.90


class TestScreenImproverAgentInit:
    """Test ScreenImproverAgent initialization."""

    def test_init_default(self):
        agent = ScreenImproverAgent(config={})
        assert agent.name == "ScreenImprover"
        assert agent.role == AgentRole.SCREEN_IMPROVER
        assert AgentCapability.SCREEN_GENERATION in agent.capabilities


# ======================================================================
# Unit Tests: Reviewer with manual screens
# ======================================================================

class TestScreenReviewerNoScreens:
    """Test ScreenReviewer when no screens exist."""

    def test_empty_screens(self, screen_context):
        agent = ScreenReviewerAgent(config={})
        result = asyncio.get_event_loop().run_until_complete(
            agent.execute(screen_context)
        )
        assert not result.success
        assert "No screens" in result.error_message


class TestScreenReviewerWithManualScreens:
    """Test ScreenReviewer with manually created screens."""

    def test_review_good_screen(self, tmp_project_dir, screen_context):
        """A well-formed screen should score high."""
        ui_spec_path = tmp_project_dir / "ui_design" / "ui_spec.json"
        ui_spec = json.loads(ui_spec_path.read_text(encoding="utf-8"))

        # Add a well-formed screen
        ui_spec["screens"] = [{
            "id": "SCREEN-001",
            "name": "Login Page",
            "route": "/login",
            "layout": "fullwidth",
            "description": "User login form",
            "components": ["COMP-001", "COMP-002"],
            "component_layout": [
                {"id": "COMP-001", "name": "Button", "x": 20, "y": 10, "w": 20, "h": 4},
                {"id": "COMP-002", "name": "Input", "x": 10, "y": 4, "w": 40, "h": 4},
            ],
            "data_requirements": ["POST /api/auth/login", "GET /api/auth/session"],
            "parent_user_story": "US-001",
            "wireframe_ascii": (
                "     0    5   10   15   20   25   30   35   40   45   50   55   60\n"
                "   0 +------------------------------------------------------------+\n"
                "     |                    Login Screen                            |\n"
                "   2 |  COMP-005 NavBar                                          |\n"
                "     +------------------------------------------------------------+\n"
                "   4 |            +------[COMP-002 Input]------+                  |\n"
                "     |            |  Email: [______________]   |                  |\n"
                "   6 |            |  Pass:  [______________]   |                  |\n"
                "     |            +----------------------------+                  |\n"
                "   8 |                                                            |\n"
                "     |            +--[COMP-001 Button: Login]--+                  |\n"
                "  10 +------------------------------------------------------------+\n"
            ),
        }]
        ui_spec_path.write_text(json.dumps(ui_spec, indent=2), encoding="utf-8")

        agent = ScreenReviewerAgent(config={})
        result = asyncio.get_event_loop().run_until_complete(
            agent.execute(screen_context)
        )

        assert result.success
        assert result.quality_score > 0.5
        # Report should exist
        report_path = tmp_project_dir / "ui_design" / "screen_review_report.json"
        assert report_path.exists()

    def test_review_bad_screen(self, tmp_project_dir, screen_context):
        """A poorly-formed screen should score low and have issues."""
        ui_spec_path = tmp_project_dir / "ui_design" / "ui_spec.json"
        ui_spec = json.loads(ui_spec_path.read_text(encoding="utf-8"))

        # Add a poorly-formed screen (missing wireframe, bad comp IDs, no data)
        ui_spec["screens"] = [{
            "id": "SCREEN-001",
            "name": "Bad Screen",
            "route": "/bad",
            "layout": "default",
            "components": ["COMP-999", "COMP-888"],  # Invalid IDs
            "component_layout": [],  # Empty
            "data_requirements": [],  # Empty
            "parent_user_story": "",  # Missing
            "wireframe_ascii": "",  # Missing
        }]
        ui_spec_path.write_text(json.dumps(ui_spec, indent=2), encoding="utf-8")

        agent = ScreenReviewerAgent(config={})
        result = asyncio.get_event_loop().run_until_complete(
            agent.execute(screen_context)
        )

        assert result.success  # Review itself succeeds
        assert result.quality_score < 0.5
        assert result.needs_improvement
        assert len(result.quality_issues) > 0


class TestScreenReviewerContainment:
    """Test that containment (parent-child) is not counted as overlap."""

    def test_reviewer_containment_not_overlap(self, tmp_project_dir, screen_context):
        """A container with children inside should not produce overlap issues."""
        ui_spec_path = tmp_project_dir / "ui_design" / "ui_spec.json"
        ui_spec = json.loads(ui_spec_path.read_text(encoding="utf-8"))

        # AuthCard container fully wraps Alert, Input, Button
        ui_spec["screens"] = [{
            "id": "SCREEN-001",
            "name": "Registration",
            "route": "/register",
            "layout": "centered",
            "description": "Registration screen",
            "components": ["COMP-001", "COMP-002", "COMP-003"],
            "component_layout": [
                {"id": "COMP-003", "name": "Card", "x": 10, "y": 2, "w": 40, "h": 26},
                {"id": "COMP-002", "name": "Input", "x": 12, "y": 10, "w": 36, "h": 3},
                {"id": "COMP-001", "name": "Button", "x": 12, "y": 20, "w": 36, "h": 3},
            ],
            "data_requirements": ["POST /api/auth/register"],
            "parent_user_story": "US-001",
            "wireframe_ascii": (
                "     0    5   10   15   20   25   30   35   40   45   50   55   60\n"
                "   0 +------------------------------------------------------------+\n"
                "   2 |          +--[COMP-003 Card]--+                             |\n"
                "  10 |          |  [COMP-002 Input]  |                            |\n"
                "  20 |          |  [COMP-001 Button] |                            |\n"
                "  28 |          +--------------------+                            |\n"
                "  30 +------------------------------------------------------------+\n"
            ),
        }]
        ui_spec_path.write_text(json.dumps(ui_spec, indent=2), encoding="utf-8")

        agent = ScreenReviewerAgent(config={})
        result = asyncio.get_event_loop().run_until_complete(
            agent.execute(screen_context)
        )

        assert result.success
        # No overlap issues should be reported
        overlap_issues = [
            i for i in result.quality_issues
            if i.get("dimension") == "layout_coherence" and "overlap" in i.get("description", "")
        ]
        assert len(overlap_issues) == 0, f"False overlap issues: {overlap_issues}"

        # layout_coherence should be 1.0 (all coords present, no true overlaps)
        report_path = tmp_project_dir / "ui_design" / "screen_review_report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["dimension_scores"]["layout_coherence"] == 1.0

    def test_reviewer_true_overlap_still_detected(self, tmp_project_dir, screen_context):
        """True overlaps (partial, neither contains other) should still be flagged."""
        ui_spec_path = tmp_project_dir / "ui_design" / "ui_spec.json"
        ui_spec = json.loads(ui_spec_path.read_text(encoding="utf-8"))

        # Two sibling components that partially overlap
        ui_spec["screens"] = [{
            "id": "SCREEN-001",
            "name": "Test",
            "route": "/test",
            "layout": "default",
            "description": "Test screen",
            "components": ["COMP-001", "COMP-002"],
            "component_layout": [
                {"id": "COMP-001", "name": "Button", "x": 0, "y": 0, "w": 30, "h": 10},
                {"id": "COMP-002", "name": "Input", "x": 20, "y": 5, "w": 30, "h": 10},
            ],
            "data_requirements": ["GET /api/test"],
            "parent_user_story": "US-001",
            "wireframe_ascii": (
                "     0    5   10   15   20   25   30   35   40   45   50   55   60\n"
                "   0 +----[COMP-001]----+\n"
                "   5 |        +----[COMP-002]----+\n"
                "  10 +--------+---------+--------+\n"
            ),
        }]
        ui_spec_path.write_text(json.dumps(ui_spec, indent=2), encoding="utf-8")

        agent = ScreenReviewerAgent(config={})
        result = asyncio.get_event_loop().run_until_complete(
            agent.execute(screen_context)
        )

        assert result.success
        overlap_issues = [
            i for i in result.quality_issues
            if i.get("dimension") == "layout_coherence" and "overlap" in i.get("description", "")
        ]
        assert len(overlap_issues) == 1, "True overlap should still be detected"


# ======================================================================
# Unit Tests: Improver with known issues
# ======================================================================

class TestScreenImproverWithIssues:
    """Test ScreenImprover with known issues."""

    def test_fix_component_coverage(self, tmp_project_dir, screen_context):
        """Should remove invalid COMP-IDs."""
        ui_spec_path = tmp_project_dir / "ui_design" / "ui_spec.json"
        ui_spec = json.loads(ui_spec_path.read_text(encoding="utf-8"))

        ui_spec["screens"] = [{
            "id": "SCREEN-001",
            "name": "Test Screen",
            "route": "/test",
            "layout": "default",
            "components": ["COMP-001", "COMP-999"],  # COMP-999 is invalid
            "component_layout": [
                {"id": "COMP-001", "name": "Button", "x": 0, "y": 0, "w": 60, "h": 4},
                {"id": "COMP-999", "name": "Ghost", "x": 0, "y": 4, "w": 60, "h": 4},
            ],
            "data_requirements": ["GET /api/test"],
            "parent_user_story": "US-001",
            "wireframe_ascii": "+---+\n| X |\n+---+",
        }]
        ui_spec_path.write_text(json.dumps(ui_spec, indent=2), encoding="utf-8")

        # Set up issues
        screen_context.quality_issues = [{
            "severity": "major",
            "dimension": "component_coverage",
            "screen_id": "SCREEN-001",
            "description": "Invalid COMP-IDs: COMP-999",
            "fix_hint": "Remove invalid IDs",
        }]

        agent = ScreenImproverAgent(config={})
        result = asyncio.get_event_loop().run_until_complete(
            agent.execute(screen_context)
        )

        assert result.success
        assert len(result.improvements_applied) > 0

        # Verify COMP-999 was removed
        updated = json.loads(ui_spec_path.read_text(encoding="utf-8"))
        screen = updated["screens"][0]
        assert "COMP-999" not in screen["components"]
        assert "COMP-001" in screen["components"]

    def test_fix_story_coverage(self, tmp_project_dir, screen_context):
        """Should set parent_user_story field."""
        ui_spec_path = tmp_project_dir / "ui_design" / "ui_spec.json"
        ui_spec = json.loads(ui_spec_path.read_text(encoding="utf-8"))

        ui_spec["screens"] = [{
            "id": "SCREEN-001",
            "name": "Test Screen",
            "route": "/test",
            "layout": "default",
            "components": ["COMP-001"],
            "component_layout": [],
            "data_requirements": [],
            "parent_user_story": "",  # Missing
            "wireframe_ascii": "",
        }]
        ui_spec_path.write_text(json.dumps(ui_spec, indent=2), encoding="utf-8")

        screen_context.quality_issues = [{
            "severity": "minor",
            "dimension": "story_coverage",
            "screen_id": "SCREEN-001",
            "description": "No parent_user_story set",
            "fix_hint": "Set parent_user_story field",
        }]

        agent = ScreenImproverAgent(config={})
        result = asyncio.get_event_loop().run_until_complete(
            agent.execute(screen_context)
        )

        assert result.success
        assert len(result.improvements_applied) > 0

        updated = json.loads(ui_spec_path.read_text(encoding="utf-8"))
        screen = updated["screens"][0]
        assert screen["parent_user_story"] != ""

    def test_fix_layout_coherence(self, tmp_project_dir, screen_context):
        """Should add missing coordinates."""
        ui_spec_path = tmp_project_dir / "ui_design" / "ui_spec.json"
        ui_spec = json.loads(ui_spec_path.read_text(encoding="utf-8"))

        ui_spec["screens"] = [{
            "id": "SCREEN-001",
            "name": "Test Screen",
            "route": "/test",
            "layout": "default",
            "components": ["COMP-001"],
            "component_layout": [
                {"id": "COMP-001", "name": "Button"},  # Missing x,y,w,h
            ],
            "data_requirements": ["GET /api/test"],
            "parent_user_story": "US-001",
            "wireframe_ascii": "+---+\n| X |\n+---+",
        }]
        ui_spec_path.write_text(json.dumps(ui_spec, indent=2), encoding="utf-8")

        screen_context.quality_issues = [{
            "severity": "minor",
            "dimension": "layout_coherence",
            "screen_id": "SCREEN-001",
            "description": "Missing x/y/w/h in layout entry: COMP-001",
            "fix_hint": "Add missing coordinate fields",
        }]

        agent = ScreenImproverAgent(config={})
        result = asyncio.get_event_loop().run_until_complete(
            agent.execute(screen_context)
        )

        assert result.success
        assert len(result.improvements_applied) > 0

        updated = json.loads(ui_spec_path.read_text(encoding="utf-8"))
        layout = updated["screens"][0]["component_layout"][0]
        assert "x" in layout
        assert "y" in layout
        assert "w" in layout
        assert "h" in layout

    def test_improver_skips_containment(self, tmp_project_dir, screen_context):
        """Improver should NOT push children out of containers."""
        ui_spec_path = tmp_project_dir / "ui_design" / "ui_spec.json"
        ui_spec = json.loads(ui_spec_path.read_text(encoding="utf-8"))

        # Container with children - improver should leave this alone
        ui_spec["screens"] = [{
            "id": "SCREEN-001",
            "name": "Registration",
            "route": "/register",
            "layout": "centered",
            "description": "Registration screen",
            "components": ["COMP-001", "COMP-003"],
            "component_layout": [
                {"id": "COMP-003", "name": "Card", "x": 10, "y": 2, "w": 40, "h": 26},
                {"id": "COMP-001", "name": "Button", "x": 12, "y": 20, "w": 36, "h": 3},
            ],
            "data_requirements": ["POST /api/register"],
            "parent_user_story": "US-001",
            "wireframe_ascii": "+---+\n| X |\n+---+",
        }]
        ui_spec_path.write_text(json.dumps(ui_spec, indent=2), encoding="utf-8")

        # Even if an overlap issue is reported, containment should be skipped
        screen_context.quality_issues = [{
            "severity": "minor",
            "dimension": "layout_coherence",
            "screen_id": "SCREEN-001",
            "description": "1 component overlap(s) in SCREEN-001",
            "fix_hint": "Adjust x,y,w,h to resolve overlaps",
        }]

        agent = ScreenImproverAgent(config={})
        result = asyncio.get_event_loop().run_until_complete(
            agent.execute(screen_context)
        )

        assert result.success

        # Button should still be at y=20 (inside the card), not pushed to y=28
        updated = json.loads(ui_spec_path.read_text(encoding="utf-8"))
        layout = updated["screens"][0]["component_layout"]
        button = next(c for c in layout if c["id"] == "COMP-001")
        assert button["y"] == 20, f"Button should stay at y=20, got y={button['y']}"

    def test_no_issues(self, screen_context):
        """Should succeed with no issues."""
        screen_context.quality_issues = []
        agent = ScreenImproverAgent(config={})
        result = asyncio.get_event_loop().run_until_complete(
            agent.execute(screen_context)
        )
        assert result.success
        assert "No issues" in result.notes


# ======================================================================
# Unit Tests: Orchestrator Init
# ======================================================================

class TestScreenDesignOrchestratorInit:
    """Test ScreenDesignOrchestrator initialization."""

    def test_init_default(self):
        orch = ScreenDesignOrchestrator(config={})
        assert "screen_generator" in orch.agents
        assert "screen_reviewer" in orch.agents
        assert "screen_improver" in orch.agents

    def test_init_with_config(self):
        cfg = {
            "orchestrator": {"max_iterations": 2, "target_quality": 0.9},
            "agents": {},
            "quality_targets": {},
        }
        orch = ScreenDesignOrchestrator(config=cfg)
        assert orch.max_iterations == 2
        assert orch.target_quality == 0.9


# ======================================================================
# Unit Tests: JSON parsing
# ======================================================================

class TestJsonParsing:
    """Test robust JSON parsing in ScreenGeneratorAgent."""

    def test_direct_json(self):
        agent = ScreenGeneratorAgent(config={})
        result = agent._parse_json_robust('{"name": "test"}')
        assert result == {"name": "test"}

    def test_markdown_fence(self):
        agent = ScreenGeneratorAgent(config={})
        result = agent._parse_json_robust('```json\n{"name": "test"}\n```')
        assert result == {"name": "test"}

    def test_generic_fence(self):
        agent = ScreenGeneratorAgent(config={})
        result = agent._parse_json_robust('```\n{"name": "test"}\n```')
        assert result == {"name": "test"}

    def test_bracket_matching(self):
        agent = ScreenGeneratorAgent(config={})
        result = agent._parse_json_robust('Here is the JSON: {"name": "test"} end')
        assert result == {"name": "test"}

    def test_empty_input(self):
        agent = ScreenGeneratorAgent(config={})
        assert agent._parse_json_robust("") is None
        assert agent._parse_json_robust("   ") is None

    def test_invalid_json(self):
        agent = ScreenGeneratorAgent(config={})
        assert agent._parse_json_robust("not json at all") is None


# ======================================================================
# Integration Tests (require LLM / API key)
# ======================================================================

@skip_no_key
class TestScreenGeneratorAgentLLM:
    """Integration test: ScreenGeneratorAgent with real LLM."""

    def test_generate_screens(self, tmp_project_dir, screen_context):
        cfg = {
            "model": "google/gemini-3-flash-preview",
            "temperature": 0.3,
            "max_tokens": 8000,
            "max_screens": 2,  # Limit to 2 for speed
        }
        agent = ScreenGeneratorAgent(config=cfg)
        result = asyncio.get_event_loop().run_until_complete(
            agent.execute(screen_context)
        )

        assert result.success, f"Screen generation failed: {result.error_message}"
        assert len(result.generated_files) > 0

        # Check ui_spec.json was updated
        ui_spec = json.loads(
            (tmp_project_dir / "ui_design" / "ui_spec.json").read_text(encoding="utf-8")
        )
        assert len(ui_spec["screens"]) > 0

        # Check screen has wireframe
        screen = ui_spec["screens"][0]
        assert screen.get("wireframe_ascii"), "Screen should have ASCII wireframe"
        assert screen.get("name"), "Screen should have a name"
        assert screen.get("route"), "Screen should have a route"


@skip_no_key
class TestScreenDesignOrchestratorLLM:
    """Integration test: Full orchestrator with real LLM."""

    def test_full_run(self, tmp_project_dir):
        cfg = {
            "orchestrator": {
                "max_iterations": 2,
                "stagnation_threshold": 2,
                "max_replans": 1,
                "target_quality": 0.60,  # Lower target for test speed
            },
            "max_screens": 2,
            "agents": {
                "screen_generator": {
                    "model": "google/gemini-3-flash-preview",
                    "temperature": 0.3,
                    "max_tokens": 8000,
                },
                "screen_reviewer": {
                    "model": "google/gemini-3-flash-preview",
                    "temperature": 0.3,
                    "max_tokens": 4000,
                },
                "screen_improver": {
                    "model": "google/gemini-3-flash-preview",
                    "temperature": 0.3,
                    "max_tokens": 4000,
                },
            },
            "quality_targets": {
                "wireframe_quality": 0.60,
                "component_coverage": 0.60,
                "story_coverage": 0.60,
                "layout_coherence": 0.60,
                "data_completeness": 0.60,
            },
        }

        orch = ScreenDesignOrchestrator(config=cfg)
        result = asyncio.get_event_loop().run_until_complete(
            orch.run(
                project_id="test-ecommerce",
                project_name="E-Commerce Platform",
                output_dir=str(tmp_project_dir),
                artifact_stats={"user_stories": 3, "components": 6},
            )
        )

        assert result["success"], f"Orchestrator failed: {result.get('error')}"
        assert result["iterations_completed"] >= 1

        # Check screens were created
        ui_spec = json.loads(
            (tmp_project_dir / "ui_design" / "ui_spec.json").read_text(encoding="utf-8")
        )
        assert len(ui_spec["screens"]) > 0, "No screens were generated"
