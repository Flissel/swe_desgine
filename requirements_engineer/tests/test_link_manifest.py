"""Tests for _build_link_manifest and TraceIndex._load_link_manifest."""
import json
import tempfile
from pathlib import Path

import pytest

from requirements_engineer.run_re_system import _build_link_manifest, _write_link_manifest


# ── Stub dataclasses ──────────────────────────────────────────────────────────

class _Req:
    def __init__(self, req_id):
        self.requirement_id = req_id


class _Story:
    def __init__(self, sid, req_id=None, epic_id=None):
        self.id = sid
        self.parent_requirement_id = req_id
        self.parent_epic_id = epic_id


class _Epic:
    def __init__(self, eid):
        self.id = eid


class _API:
    def __init__(self, path, req_id=None):
        self.path = path
        self.id = path
        self.parent_requirement_id = req_id


class _Entity:
    def __init__(self, name, src_reqs=None):
        self.id = name
        self.name = name
        self.source_requirements = src_reqs or []


class _TC:
    def __init__(self, tid, story_id=None, req_id=None):
        self.id = tid
        self.parent_user_story_id = story_id
        self.parent_requirement_id = req_id


class _Screen:
    def __init__(self, sid, parent_story=None, components=None, data_reqs=None):
        self.id = sid
        self.parent_user_story = parent_story
        self.components = components or []
        self.data_requirements = data_reqs or []


class _Comp:
    def __init__(self, cid, screen_ids=None):
        self.id = cid
        self.parent_screen_ids = screen_ids or []


class _UISpec:
    def __init__(self, screens=None, components=None):
        self.screens = screens or []
        self.components = components or []


class _Task:
    def __init__(self, tid, story_id=None, req_id=None, entity_id=None, api_res=None):
        self.id = tid
        self.parent_user_story_id = story_id
        self.parent_requirement_id = req_id
        self.parent_entity_id = entity_id
        self.parent_api_resource = api_res


class _TaskBreakdown:
    def __init__(self, tasks):
        self._tasks = tasks

    @property
    def tasks(self):
        return self._tasks


# ── Tests ─────────────────────────────────────────────────────────────────────

def _build(**kwargs):
    defaults = dict(
        requirements=[], user_stories=[], epics=[],
        api_endpoints=[], entities_dict={}, test_cases=[],
        ui_spec=None, task_breakdown=None,
    )
    defaults.update(kwargs)
    return _build_link_manifest(**defaults)


def _edges_of(manifest, etype):
    return [(e["src"], e["dst"]) for e in manifest["edges"] if e["type"] == etype]


class TestBuildLinkManifest:
    def test_empty_inputs_returns_empty_edges(self):
        m = _build()
        assert m["edges"] == []
        assert m["stats"]["total_edges"] == 0

    def test_req_story_edge(self):
        m = _build(
            requirements=[_Req("REQ-001")],
            user_stories=[_Story("US-001", req_id="REQ-001")],
        )
        assert ("REQ-001", "US-001") in _edges_of(m, "req_story")

    def test_epic_story_edge(self):
        m = _build(
            epics=[_Epic("EPIC-001")],
            user_stories=[_Story("US-001", epic_id="EPIC-001")],
        )
        assert ("EPIC-001", "US-001") in _edges_of(m, "epic_story")

    def test_req_api_edge(self):
        m = _build(
            requirements=[_Req("REQ-001")],
            api_endpoints=[_API("/api/users", req_id="REQ-001")],
        )
        assert ("REQ-001", "/api/users") in _edges_of(m, "req_api")

    def test_api_story_edge_via_shared_req(self):
        m = _build(
            requirements=[_Req("REQ-001")],
            user_stories=[_Story("US-001", req_id="REQ-001")],
            api_endpoints=[_API("/api/users", req_id="REQ-001")],
        )
        assert ("/api/users", "US-001") in _edges_of(m, "api_story")

    def test_req_entity_edge(self):
        m = _build(
            requirements=[_Req("REQ-001")],
            entities_dict={"User": _Entity("User", src_reqs=["REQ-001"])},
        )
        assert ("REQ-001", "User") in _edges_of(m, "req_entity")

    def test_entity_api_edge(self):
        m = _build(
            requirements=[_Req("REQ-001")],
            api_endpoints=[_API("/api/users", req_id="REQ-001")],
            entities_dict={"User": _Entity("User", src_reqs=["REQ-001"])},
        )
        assert ("User", "/api/users") in _edges_of(m, "entity_api")

    def test_story_test_edge(self):
        m = _build(
            user_stories=[_Story("US-001")],
            test_cases=[_TC("TC-001", story_id="US-001")],
        )
        assert ("US-001", "TC-001") in _edges_of(m, "story_test")

    def test_req_test_edge(self):
        m = _build(
            requirements=[_Req("REQ-001")],
            test_cases=[_TC("TC-001", req_id="REQ-001")],
        )
        assert ("REQ-001", "TC-001") in _edges_of(m, "req_test")

    def test_story_screen_edge(self):
        ui = _UISpec(screens=[_Screen("SCREEN-001", parent_story="US-001")])
        m = _build(user_stories=[_Story("US-001")], ui_spec=ui)
        assert ("US-001", "SCREEN-001") in _edges_of(m, "story_screen")

    def test_screen_component_from_screen_components(self):
        ui = _UISpec(
            screens=[_Screen("SCREEN-001", components=["COMP-001"])],
        )
        m = _build(ui_spec=ui)
        assert ("SCREEN-001", "COMP-001") in _edges_of(m, "screen_component")

    def test_screen_component_from_comp_parent_screen_ids(self):
        ui = _UISpec(
            components=[_Comp("COMP-001", screen_ids=["SCREEN-001"])],
        )
        m = _build(ui_spec=ui)
        assert ("SCREEN-001", "COMP-001") in _edges_of(m, "screen_component")

    def test_screen_api_edge(self):
        ui = _UISpec(screens=[_Screen("SCREEN-001", data_reqs=["/api/users"])])
        m = _build(ui_spec=ui)
        assert ("SCREEN-001", "/api/users") in _edges_of(m, "screen_api")

    def test_story_task_edge(self):
        tb = _TaskBreakdown([_Task("TASK-001", story_id="US-001")])
        m = _build(user_stories=[_Story("US-001")], task_breakdown=tb)
        assert ("US-001", "TASK-001") in _edges_of(m, "story_task")

    def test_req_task_edge(self):
        tb = _TaskBreakdown([_Task("TASK-001", req_id="REQ-001")])
        m = _build(requirements=[_Req("REQ-001")], task_breakdown=tb)
        assert ("REQ-001", "TASK-001") in _edges_of(m, "req_task")

    def test_entity_task_edge(self):
        tb = _TaskBreakdown([_Task("TASK-001", entity_id="User")])
        m = _build(
            entities_dict={"User": _Entity("User")},
            task_breakdown=tb,
        )
        assert ("User", "TASK-001") in _edges_of(m, "entity_task")

    def test_api_task_edge(self):
        tb = _TaskBreakdown([_Task("TASK-001", api_res="/api/users")])
        m = _build(task_breakdown=tb)
        assert ("/api/users", "TASK-001") in _edges_of(m, "api_task")

    def test_no_self_links(self):
        # A story that somehow references itself should be skipped
        m = _build(user_stories=[_Story("US-001", req_id="US-001")])
        for e in m["edges"]:
            assert e["src"] != e["dst"]

    def test_deduplication(self):
        # Two components referencing same screen — only one screen_component edge
        ui = _UISpec(
            screens=[_Screen("SCREEN-001", components=["COMP-001"])],
            components=[_Comp("COMP-001", screen_ids=["SCREEN-001"])],
        )
        m = _build(ui_spec=ui)
        pairs = _edges_of(m, "screen_component")
        assert pairs.count(("SCREEN-001", "COMP-001")) == 1

    def test_stats_populated(self):
        m = _build(
            requirements=[_Req("REQ-001")],
            user_stories=[_Story("US-001", req_id="REQ-001")],
        )
        assert m["stats"]["total_edges"] == 1
        assert "req_story" in m["stats"]["edge_types"]
        assert m["stats"]["by_type"]["req_story"] == 1

    def test_version_and_timestamp(self):
        m = _build()
        assert m["version"] == 1
        assert "generated_at" in m


class TestWriteLinkManifest:
    def test_writes_json_file(self):
        m = _build(
            requirements=[_Req("REQ-001")],
            user_stories=[_Story("US-001", req_id="REQ-001")],
        )
        with tempfile.TemporaryDirectory() as td:
            _write_link_manifest(Path(td), m)
            p = Path(td) / "link_manifest.json"
            assert p.exists()
            data = json.loads(p.read_text(encoding="utf-8"))
            assert data["stats"]["total_edges"] == 1


class TestTraceIndexLoadManifest:
    """Integration: TraceIndex._load_link_manifest reads edges into LinkGraph."""

    def _make_index_with_artifacts(self, artifact_ids):
        from requirements_engineer.dashboard.trace_index import TraceIndex
        idx = TraceIndex()
        for aid in artifact_ids:
            idx._artifacts[aid] = {"id": aid, "type": "requirement", "title": aid}
        return idx

    def test_loads_edges_into_link_graph(self):
        idx = self._make_index_with_artifacts(["REQ-001", "US-001"])
        manifest = {
            "version": 1,
            "generated_at": "2026-01-01T00:00:00",
            "edges": [{"src": "REQ-001", "dst": "US-001", "type": "req_story"}],
        }
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "link_manifest.json"
            p.write_text(json.dumps(manifest), encoding="utf-8")
            idx._load_link_manifest(p)

        assert idx.link_graph._adjacency.get("REQ-001", {}).get("US-001") == "req_story"
        assert idx.link_graph._reverse_adjacency.get("US-001", {}).get("REQ-001") == "req_story"

    def test_skips_unknown_artifact_ids(self):
        idx = self._make_index_with_artifacts(["REQ-001"])
        manifest = {
            "edges": [{"src": "REQ-001", "dst": "UNKNOWN-999", "type": "req_story"}],
        }
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "link_manifest.json"
            p.write_text(json.dumps(manifest), encoding="utf-8")
            idx._load_link_manifest(p)

        assert "UNKNOWN-999" not in idx.link_graph._adjacency.get("REQ-001", {})

    def test_fallback_on_corrupt_manifest(self):
        idx = self._make_index_with_artifacts(["REQ-001"])
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "link_manifest.json"
            p.write_text("NOT JSON", encoding="utf-8")
            # Should not raise; fallback to _build_cross_links({}) silently
            idx._load_link_manifest(p)
