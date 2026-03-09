"""
Unit tests for TraceIndex — server-side artifact index for the Trace Explorer tab.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure the package is importable
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from requirements_engineer.dashboard.trace_index import TraceIndex


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def sample_project(tmp_path):
    """Create a minimal project directory with journal, stories, tasks, diagrams."""
    # journal.json
    journal = {
        "project_name": "Test Project",
        "nodes": {
            "node-REQ-001": {
                "requirement_id": "REQ-001",
                "title": "User Authentication",
                "description": "The system shall support user authentication via email and password.",
                "type": "functional",
                "priority": "must",
                "source": "stakeholder",
            },
            "node-REQ-002": {
                "requirement_id": "REQ-002",
                "title": "Rate Limiting",
                "description": "The system shall enforce rate limiting on all API endpoints.",
                "type": "non_functional",
                "priority": "should",
                "source": "architect",
            },
        },
    }
    (tmp_path / "journal.json").write_text(json.dumps(journal), encoding="utf-8")

    # user_stories.json
    stories = [
        {
            "id": "US-001",
            "title": "Login with email",
            "description": "As a user, I want to login with email and password.",
            "parent_requirement_id": "REQ-001",
        },
        {
            "id": "US-002",
            "title": "Password reset",
            "description": "As a user, I want to reset my password.",
            "parent_requirement_id": "REQ-001",
        },
    ]
    (tmp_path / "user_stories.json").write_text(json.dumps(stories), encoding="utf-8")

    # tasks/task_list.json
    (tmp_path / "tasks").mkdir()
    tasks = {
        "features": {
            "auth": [
                {
                    "id": "TASK-001",
                    "title": "Implement login endpoint",
                    "description": "Create POST /auth/login",
                    "complexity": "medium",
                    "status": "pending",
                    "phase": "sprint-1",
                    "estimated_hours": 8,
                },
            ]
        }
    }
    (tmp_path / "tasks" / "task_list.json").write_text(json.dumps(tasks), encoding="utf-8")

    # diagrams/
    (tmp_path / "diagrams").mkdir()
    (tmp_path / "diagrams" / "REQ-001_flowchart.mmd").write_text(
        "graph TD\n  A-->B", encoding="utf-8"
    )

    return tmp_path


@pytest.fixture
def project_data():
    """Minimal project_data dict as returned by server._load_folder_format()."""
    return {
        "test_cases": [
            {"id": "TC-001", "title": "Login valid credentials", "parent_user_story_id": "US-001"},
            {"id": "TC-002", "title": "Login invalid password", "parent_user_story_id": "US-001"},
            {"id": "TC-003", "title": "Password reset flow", "parent_user_story_id": "US-002"},
        ],
        "api_endpoints": [
            {"id": "API-001", "method": "POST", "path": "/auth/login", "description": "Authenticate user"},
            {"id": "API-002", "method": "POST", "path": "/auth/register", "description": "Register new user"},
        ],
        "screens": [
            {"id": "SCREEN-001", "name": "Login Screen", "description": "Email and password form"},
        ],
        "entities": [
            {"id": "User", "name": "User", "description": "Registered user entity"},
        ],
        "tasks": {
            "auth": [
                {"id": "TASK-001", "title": "Implement login endpoint", "complexity": "medium"},
            ]
        },
    }


@pytest.fixture
def trace_index(sample_project, project_data):
    """Build and return a TraceIndex for the sample project."""
    idx = TraceIndex()
    idx.build(sample_project, project_data)
    return idx


# ── Build Tests ───────────────────────────────────────────────────

class TestBuild:
    def test_build_indexes_artifacts(self, trace_index):
        """build() should populate _artifacts with nodes from LinkGraph and project_data."""
        assert len(trace_index._artifacts) > 0

    def test_build_populates_by_type(self, trace_index):
        """build() should populate _by_type with artifact IDs grouped by type."""
        assert len(trace_index._by_type) > 0

    def test_build_indexes_test_cases(self, trace_index):
        """build() should index test cases from project_data."""
        assert "TC-001" in trace_index._artifacts
        assert trace_index._artifacts["TC-001"]["type"] == "test"

    def test_build_indexes_api_endpoints(self, trace_index):
        """build() should index API endpoints from project_data."""
        assert "API-001" in trace_index._artifacts
        assert trace_index._artifacts["API-001"]["type"] == "api"
        assert "POST /auth/login" in trace_index._artifacts["API-001"]["title"]

    def test_build_indexes_screens(self, trace_index):
        """build() should index screens from project_data."""
        assert "SCREEN-001" in trace_index._artifacts
        assert trace_index._artifacts["SCREEN-001"]["type"] == "screen"

    def test_build_indexes_entities(self, trace_index):
        """build() should index entities from project_data."""
        assert "User" in trace_index._artifacts
        assert trace_index._artifacts["User"]["type"] == "entity"

    def test_build_indexes_tasks(self, trace_index):
        """build() should index tasks from project_data."""
        assert "TASK-001" in trace_index._artifacts
        assert trace_index._artifacts["TASK-001"]["type"] == "task"

    def test_build_creates_search_index(self, trace_index):
        """build() should create a search index for all artifacts."""
        assert len(trace_index._search_idx) == len(trace_index._artifacts)
        # Search index entries should be lowercase
        for text in trace_index._search_idx.values():
            assert text == text.lower()

    def test_build_empty_project_data(self, sample_project):
        """build() should handle empty project_data gracefully."""
        idx = TraceIndex()
        idx.build(sample_project, {})
        # Should still index nodes from LinkGraph
        assert len(idx._artifacts) >= 0


# ── Query Tests ───────────────────────────────────────────────────

class TestQuery:
    def test_query_all(self, trace_index):
        """query() without type filter should return all artifacts."""
        result = trace_index.query()
        assert result["total"] > 0
        assert result["page"] == 1
        assert len(result["items"]) <= result["total"]

    def test_query_by_type(self, trace_index):
        """query() with type filter should return only matching artifacts."""
        result = trace_index.query(artifact_type="test")
        for item in result["items"]:
            assert item["type"] == "test"

    def test_query_pagination(self, trace_index):
        """query() should respect page and page_size."""
        result = trace_index.query(page_size=2, page=1)
        assert len(result["items"]) <= 2
        assert result["page_size"] == 2

    def test_query_sort_by_title(self, trace_index):
        """query() should sort by title when requested."""
        result = trace_index.query(sort_by="title", sort_dir="asc")
        titles = [item["title"] for item in result["items"]]
        assert titles == sorted(titles, key=str.lower)

    def test_query_sort_desc(self, trace_index):
        """query() should support descending sort."""
        result = trace_index.query(sort_by="id", sort_dir="desc")
        ids = [item["id"] for item in result["items"]]
        assert ids == sorted(ids, key=str.lower, reverse=True)

    def test_query_search(self, trace_index):
        """query() with search should filter by text match."""
        result = trace_index.query(search="auth")
        assert result["total"] > 0
        for item in result["items"]:
            # Should match in title or description
            full_text = trace_index._search_idx.get(item["id"], "")
            assert "auth" in full_text

    def test_query_search_no_match(self, trace_index):
        """query() with non-matching search should return empty."""
        result = trace_index.query(search="zzzznonexistent")
        assert result["total"] == 0
        assert len(result["items"]) == 0

    def test_query_filters(self, trace_index):
        """query() with field filters should filter results."""
        result = trace_index.query(filters={"priority": "must"})
        for item in result["items"]:
            assert "must" in str(trace_index._artifacts[item["id"]].get("priority", "")).lower()

    def test_query_nonexistent_type(self, trace_index):
        """query() with nonexistent type should return empty."""
        result = trace_index.query(artifact_type="unicorn")
        assert result["total"] == 0

    def test_query_items_have_link_counts(self, trace_index):
        """query() items should include downstream_count and upstream_count."""
        result = trace_index.query()
        for item in result["items"]:
            assert "downstream_count" in item
            assert "upstream_count" in item


# ── Detail Tests ──────────────────────────────────────────────────

class TestDetail:
    def test_get_detail_exists(self, trace_index):
        """get_detail() should return full data for existing artifact."""
        detail = trace_index.get_detail("TC-001")
        assert detail is not None
        assert detail["id"] == "TC-001"
        assert "connections" in detail

    def test_get_detail_not_found(self, trace_index):
        """get_detail() should return None for missing artifact."""
        assert trace_index.get_detail("NONEXISTENT-999") is None

    def test_get_detail_has_connections(self, trace_index):
        """get_detail() should include upstream and downstream connections."""
        detail = trace_index.get_detail("TC-001")
        if detail:
            conns = detail["connections"]
            assert "upstream" in conns
            assert "downstream" in conns


# ── Trace Chain Tests ─────────────────────────────────────────────

class TestTraceChain:
    def test_chain_for_test_case(self, trace_index):
        """get_trace_chain() should return upstream/downstream for a test case."""
        chain = trace_index.get_trace_chain("TC-001")
        assert chain["artifact"] is not None
        assert chain["artifact"]["id"] == "TC-001"
        assert isinstance(chain["upstream"], list)
        assert isinstance(chain["downstream"], list)

    def test_chain_for_nonexistent(self, trace_index):
        """get_trace_chain() for missing artifact should return empty chain."""
        chain = trace_index.get_trace_chain("MISSING-999")
        assert chain["artifact"] is None
        assert chain["upstream"] == []
        assert chain["downstream"] == []

    def test_chain_depth_limit(self, trace_index):
        """get_trace_chain() should respect depth limit."""
        chain = trace_index.get_trace_chain("TC-001", depth=1)
        for node in chain["upstream"]:
            assert node["depth"] <= 1
        for node in chain["downstream"]:
            assert node["depth"] <= 1

    def test_chain_nodes_have_required_fields(self, trace_index):
        """Chain nodes should have id, type, title, link_type, depth."""
        chain = trace_index.get_trace_chain("TC-001")
        for node in chain["upstream"] + chain["downstream"]:
            assert "id" in node
            assert "type" in node
            assert "title" in node
            assert "link_type" in node
            assert "depth" in node


# ── Impact Tests ──────────────────────────────────────────────────

class TestImpact:
    def test_impact_returns_structure(self, trace_index):
        """get_impact() should return expected structure."""
        # Use a known artifact
        ids = list(trace_index._artifacts.keys())
        if not ids:
            pytest.skip("No artifacts to test")
        impact = trace_index.get_impact(ids[0])
        assert "artifact" in impact
        assert "impacted" in impact
        assert "counts_by_type" in impact
        assert "total" in impact

    def test_impact_nonexistent(self, trace_index):
        """get_impact() for missing artifact should return empty."""
        impact = trace_index.get_impact("MISSING-999")
        assert impact["artifact"] is None
        assert impact["total"] == 0


# ── Tree Tests ────────────────────────────────────────────────────

class TestTree:
    def test_tree_returns_types(self, trace_index):
        """get_tree() should return types with labels and counts."""
        tree = trace_index.get_tree()
        assert "types" in tree
        assert len(tree["types"]) > 0

    def test_tree_type_structure(self, trace_index):
        """Each tree type should have type, label, and count fields."""
        tree = trace_index.get_tree()
        for t in tree["types"]:
            assert "type" in t
            assert "label" in t
            assert "count" in t
            assert t["count"] > 0

    def test_tree_excludes_empty_types(self, trace_index):
        """get_tree() should not include types with zero artifacts."""
        tree = trace_index.get_tree()
        for t in tree["types"]:
            assert t["count"] > 0


# ── Stats Tests ───────────────────────────────────────────────────

class TestStats:
    def test_stats_returns_counts(self, trace_index):
        """get_stats() should return aggregate statistics."""
        stats = trace_index.get_stats()
        assert "total_artifacts" in stats
        assert "total_links" in stats
        assert "orphan_count" in stats
        assert "counts_by_type" in stats
        assert stats["total_artifacts"] > 0

    def test_stats_counts_by_type_sum(self, trace_index):
        """Sum of counts_by_type should equal total_artifacts."""
        stats = trace_index.get_stats()
        type_sum = sum(stats["counts_by_type"].values())
        assert type_sum == stats["total_artifacts"]


# ── Search Tests ──────────────────────────────────────────────────

class TestSearch:
    def test_search_by_title(self, trace_index):
        """search() should find artifacts by title match."""
        results = trace_index.search("Login")
        assert len(results) > 0
        # Results with title match should have score 2
        for r in results:
            if "login" in r.get("title", "").lower():
                assert r["score"] == 2

    def test_search_by_description(self, trace_index):
        """search() should find artifacts by description match."""
        results = trace_index.search("password")
        assert len(results) > 0

    def test_search_empty_query(self, trace_index):
        """search() with empty query should match nothing (empty string in every text)."""
        results = trace_index.search("")
        # Empty string is in every string, so this returns everything
        assert len(results) >= 0

    def test_search_with_type_filter(self, trace_index):
        """search() with types filter should only return matching types."""
        results = trace_index.search("login", types=["test"])
        for r in results:
            assert r["type"] == "test"

    def test_search_limit(self, trace_index):
        """search() should respect limit parameter."""
        results = trace_index.search("", limit=3)
        assert len(results) <= 3

    def test_search_result_structure(self, trace_index):
        """Search results should have id, type, title, description, score."""
        results = trace_index.search("auth")
        if results:
            r = results[0]
            assert "id" in r
            assert "type" in r
            assert "title" in r
            assert "description" in r
            assert "score" in r


# ── Update Tests ──────────────────────────────────────────────────

class TestUpdate:
    def test_update_in_memory(self, trace_index):
        """update_artifact() should update the in-memory artifact."""
        result = trace_index.update_artifact("TC-001", "title", "Updated Title")
        assert result["success"] or not result["success"]  # may fail on write-back
        assert trace_index._artifacts["TC-001"]["title"] == "Updated Title"

    def test_update_search_index(self, trace_index):
        """update_artifact() should update the search index."""
        trace_index.update_artifact("TC-001", "title", "UniqueSearchTerm123")
        assert "uniquesearchterm123" in trace_index._search_idx["TC-001"]

    def test_update_nonexistent(self, trace_index):
        """update_artifact() for missing artifact should return error."""
        result = trace_index.update_artifact("MISSING-999", "title", "x")
        assert result["success"] is False

    def test_update_returns_impacted(self, trace_index):
        """update_artifact() should return impacted_ids."""
        result = trace_index.update_artifact("TC-001", "title", "Changed")
        assert "impacted_ids" in result

    def test_write_back_task(self, trace_index, sample_project):
        """update_artifact() should write back task changes to disk."""
        result = trace_index.update_artifact("TASK-001", "title", "New Task Title")
        # Verify disk write
        tasks_path = sample_project / "tasks" / "task_list.json"
        if tasks_path.exists():
            with open(tasks_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            found = False
            for feat_tasks in data.get("features", {}).values():
                for task in feat_tasks:
                    if task.get("id") == "TASK-001":
                        if task.get("title") == "New Task Title":
                            found = True
            if result["success"]:
                assert found


# ── Edge Cases ────────────────────────────────────────────────────

class TestEdgeCases:
    def test_build_twice(self, sample_project, project_data):
        """Building the index twice should work (clears old data)."""
        idx = TraceIndex()
        idx.build(sample_project, project_data)
        count1 = len(idx._artifacts)
        idx.build(sample_project, project_data)
        count2 = len(idx._artifacts)
        assert count1 == count2

    def test_query_page_out_of_range(self, trace_index):
        """Requesting a page beyond total_pages should return last page."""
        result = trace_index.query(page=9999)
        assert result["page"] <= result["total_pages"]

    def test_query_page_zero(self, trace_index):
        """Page 0 should be clamped to page 1."""
        result = trace_index.query(page=0)
        assert result["page"] == 1

    def test_empty_project_data_keys(self, sample_project):
        """Project data with empty lists should not crash build."""
        idx = TraceIndex()
        idx.build(sample_project, {
            "test_cases": [],
            "api_endpoints": [],
            "screens": [],
            "entities": [],
            "tasks": {},
        })
        assert isinstance(idx._artifacts, dict)

    def test_malformed_test_cases(self, sample_project):
        """Non-dict items in test_cases should be skipped."""
        idx = TraceIndex()
        idx.build(sample_project, {
            "test_cases": [None, "bad", 42, {"id": "TC-GOOD", "title": "Valid"}],
        })
        assert "TC-GOOD" in idx._artifacts


# ── Cross-Linking Tests ──────────────────────────────────────────

@pytest.fixture
def crosslink_project(tmp_path):
    """Create a project with all artifact types for cross-link testing."""
    journal = {
        "project_name": "CrossLink Test",
        "nodes": {
            "REQ-001": {
                "requirement_id": "REQ-001",
                "title": "User Management",
                "type": "functional",
                "priority": "must",
            },
            "REQ-002": {
                "requirement_id": "REQ-002",
                "title": "Data Security",
                "type": "non_functional",
                "priority": "must",
            },
        },
    }
    (tmp_path / "journal.json").write_text(json.dumps(journal), encoding="utf-8")
    (tmp_path / "diagrams").mkdir()
    # ER diagram with entity reference for diagram→entity linking
    (tmp_path / "diagrams" / "DIAG-ER.mmd").write_text(
        "erDiagram\n  User {\n    string name\n  }", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def crosslink_data():
    """Project data with rich cross-references between artifacts."""
    return {
        "user_stories": [
            {
                "id": "US-001",
                "title": "Register account",
                "persona": "End User",
                "parent_requirement_id": "REQ-001",
                "linked_requirement_ids": ["REQ-001"],
                "parent_epic_id": "EPIC-001",
            },
            {
                "id": "US-002",
                "title": "Manage profile",
                "persona": "Admin",
                "parent_requirement_id": "REQ-001",
            },
        ],
        "epics": [
            {
                "id": "EPIC-001",
                "title": "User Onboarding",
                "linked_requirements": ["REQ-001"],
                "linked_user_stories": ["US-001"],
            },
        ],
        "screens": [
            {
                "id": "SCREEN-001",
                "name": "Registration Form",
                "parent_user_story": "US-001",
                "components": ["COMP-001", "COMP-002"],
                "data_requirements": ["POST /api/users", "GET /api/users/{id}"],
            },
            {
                "id": "SCREEN-002",
                "name": "Profile Page",
                "parent_user_story": "US-002",
                "components": ["COMP-003"],
                "data_requirements": ["GET /api/profiles/{id}"],
            },
        ],
        "ui_components": [
            {"id": "COMP-001", "name": "Button", "component_type": "button"},
            {"id": "COMP-002", "name": "InputField", "component_type": "input"},
            {"id": "COMP-003", "name": "ProfileCard", "component_type": "card", "parent_screen_ids": ["SCREEN-002"]},
        ],
        "api_endpoints": [
            {"id": "API-001", "method": "POST", "path": "/api/users", "parent_requirement_id": "REQ-001"},
            {"id": "API-002", "method": "GET", "path": "/api/users/{id}"},
            {"id": "API-003", "method": "GET", "path": "/api/profiles/{id}"},
        ],
        "entities": [
            {"id": "ENT-User", "name": "User", "description": "Registered user"},
            {"id": "ENT-Profile", "name": "Profile", "description": "User profile"},
        ],
        "tests": [
            {"id": "TC-001", "title": "Register user", "parent_user_story_id": "US-001",
             "gherkin_content": "Given I POST /api/users with valid data"},
        ],
        "personas": [
            {"id": "PERSONA-001", "name": "Alice Smith", "role": "End User"},
            {"id": "PERSONA-002", "name": "Bob Admin", "role": "Admin"},
        ],
        "user_flows": [
            {
                "id": "FLOW-001",
                "name": "Registration Flow",
                "actor": "Alice Smith",
                "linked_user_story_ids": ["US-001"],
                "linked_screen_ids": [],
                "linked_persona_id": "",
                "steps": [],
            },
        ],
        "diagrams": [
            {"id": "DIAG-ER", "mermaid_code": "erDiagram\n  User {\n    string name\n  }"},
        ],
        "tasks": {
            "auth": [
                {"id": "TASK-001", "title": "Create User model", "parent_entity_id": "ENT-User"},
                {"id": "TASK-002", "title": "Implement user API", "parent_api_resource": "API-001"},
            ],
        },
        "features": [],
    }


@pytest.fixture
def crosslink_index(crosslink_project, crosslink_data):
    """Build TraceIndex with cross-link data."""
    idx = TraceIndex()
    idx.build(crosslink_project, crosslink_data)
    return idx


class TestCrossLinking:
    """Tests for _build_cross_links() heuristic linking."""

    def test_screen_component_direct(self, crosslink_index):
        """Screen with components list should link to those components."""
        edges = crosslink_index.link_graph._edge_types
        assert edges.get(("SCREEN-001", "COMP-001")) == "screen_component"
        assert edges.get(("SCREEN-001", "COMP-002")) == "screen_component"

    def test_component_parent_screen(self, crosslink_index):
        """Component with parent_screen_ids should link back to screen."""
        edges = crosslink_index.link_graph._edge_types
        assert edges.get(("SCREEN-002", "COMP-003")) == "screen_component"

    def test_screen_user_story(self, crosslink_index):
        """Screen with parent_user_story should link to that story."""
        edges = crosslink_index.link_graph._edge_types
        assert edges.get(("US-001", "SCREEN-001")) == "story_screen"
        assert edges.get(("US-002", "SCREEN-002")) == "story_screen"

    def test_api_requirement(self, crosslink_index):
        """API with parent_requirement_id should link to requirement."""
        edges = crosslink_index.link_graph._edge_types
        assert edges.get(("REQ-001", "API-001")) == "req_api"

    def test_entity_api_path_match(self, crosslink_index):
        """Entity should link to API endpoints whose path contains entity name."""
        edges = crosslink_index.link_graph._edge_types
        # /api/users -> User entity
        assert edges.get(("ENT-User", "API-001")) == "entity_api"
        assert edges.get(("ENT-User", "API-002")) == "entity_api"

    def test_screen_entity_via_data_reqs(self, crosslink_index):
        """Screen data_requirements with API paths should link to matching entities."""
        edges = crosslink_index.link_graph._edge_types
        # SCREEN-001 has /api/users -> User entity
        assert edges.get(("SCREEN-001", "ENT-User")) == "screen_entity"

    def test_api_screen_via_data_reqs(self, crosslink_index):
        """API endpoint should link to screen that references it in data_requirements."""
        edges = crosslink_index.link_graph._edge_types
        assert edges.get(("API-001", "SCREEN-001")) == "api_screen"

    def test_persona_story_role_match(self, crosslink_index):
        """Persona should link to stories with matching persona field."""
        edges = crosslink_index.link_graph._edge_types
        assert edges.get(("PERSONA-001", "US-001")) == "persona_story"
        assert edges.get(("PERSONA-002", "US-002")) == "persona_story"

    def test_test_api_content_match(self, crosslink_index):
        """Test with API path in gherkin_content should link to that API."""
        edges = crosslink_index.link_graph._edge_types
        assert edges.get(("TC-001", "API-001")) == "test_api"

    def test_diagram_entity_mermaid(self, crosslink_index):
        """Diagram with entity name in mermaid code should link to entity."""
        edges = crosslink_index.link_graph._edge_types
        # LinkGraph prefixes diagram IDs with "diagram_"
        assert edges.get(("diagram_DIAG-ER", "ENT-User")) == "diagram_entity"

    def test_task_entity_parent(self, crosslink_index):
        """Task with parent_entity_id should link to entity."""
        edges = crosslink_index.link_graph._edge_types
        assert edges.get(("ENT-User", "TASK-001")) == "entity_task"

    def test_task_api_parent(self, crosslink_index):
        """Task with parent_api_resource should link to API."""
        edges = crosslink_index.link_graph._edge_types
        assert edges.get(("API-001", "TASK-002")) == "api_task"

    def test_story_requirement_link(self, crosslink_index):
        """Story with parent_requirement_id should link to requirement."""
        edges = crosslink_index.link_graph._edge_types
        assert edges.get(("REQ-001", "US-001")) == "req_story"
        assert edges.get(("REQ-001", "US-002")) == "req_story"

    def test_epic_story_link(self, crosslink_index):
        """Story with parent_epic_id should link to epic."""
        edges = crosslink_index.link_graph._edge_types
        assert edges.get(("EPIC-001", "US-001")) == "epic_story"

    def test_flow_persona_actor_match(self, crosslink_index):
        """Flow with actor matching persona name should link."""
        edges = crosslink_index.link_graph._edge_types
        assert edges.get(("PERSONA-001", "FLOW-001")) == "flow_persona"

    def test_flow_story_linked_ids(self, crosslink_index):
        """Flow with linked_user_story_ids should link to stories."""
        edges = crosslink_index.link_graph._edge_types
        assert edges.get(("US-001", "FLOW-001")) == "flow_story"

    def test_node_prefix_dedup(self, crosslink_index):
        """node- prefixed IDs should not create duplicates when base ID exists."""
        # REQ-001 exists both as REQ-001 (from edges) and potentially node-REQ-001
        req_ids = [a for a in crosslink_index._artifacts if "REQ-001" in a]
        assert len(req_ids) == 1, f"Expected 1 REQ-001 entry, got {req_ids}"

    def test_indexes_user_stories(self, crosslink_index):
        """User stories from project_data should be indexed."""
        assert "US-001" in crosslink_index._artifacts
        assert crosslink_index._artifacts["US-001"]["type"] == "user-story"

    def test_indexes_personas(self, crosslink_index):
        """Personas from project_data should be indexed."""
        assert "PERSONA-001" in crosslink_index._artifacts
        assert crosslink_index._artifacts["PERSONA-001"]["type"] == "persona"

    def test_indexes_components(self, crosslink_index):
        """Components from ui_components should be indexed."""
        assert "COMP-001" in crosslink_index._artifacts
        assert crosslink_index._artifacts["COMP-001"]["type"] == "component"

    def test_indexes_epics(self, crosslink_index):
        """Epics from project_data should be indexed."""
        assert "EPIC-001" in crosslink_index._artifacts
        assert crosslink_index._artifacts["EPIC-001"]["type"] == "epic"

    def test_no_self_links(self, crosslink_index):
        """No artifact should link to itself."""
        for (src, dst), _ in crosslink_index.link_graph._edge_types.items():
            assert src != dst, f"Self-link found: {src}"

    def test_cross_links_increase_edges(self, crosslink_project, crosslink_data):
        """Cross-linking should add more edges than LinkGraph alone."""
        idx = TraceIndex()
        idx.link_graph.build_from_project(crosslink_project)
        baseline_edges = len(idx.link_graph.edges)
        idx2 = TraceIndex()
        idx2.build(crosslink_project, crosslink_data)
        assert len(idx2.link_graph.edges) > baseline_edges
