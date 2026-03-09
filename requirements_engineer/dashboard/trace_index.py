"""
Trace Index — Server-side artifact index for the Trace Explorer tab.

Wraps LinkGraph with sorted/filtered/paginated queries, directional trace
chains, impact analysis, and full-text search.  Built once when a project
loads; updated incrementally on edits.
"""

import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..propagation.link_graph import LinkGraph


# ── Artifact type display order ──────────────────────────────────────
TYPE_ORDER = [
    "epic", "requirement", "user-story", "test", "api", "screen",
    "entity", "component", "task", "persona", "user-flow", "diagram",
    "feature", "tech-stack",
]

TYPE_LABELS = {
    "epic": "Epics",
    "requirement": "Requirements",
    "user-story": "User Stories",
    "test": "Tests",
    "api": "API Endpoints",
    "screen": "Screens",
    "entity": "Entities",
    "component": "Components",
    "task": "Tasks",
    "persona": "Personas",
    "user-flow": "User Flows",
    "diagram": "Diagrams",
    "feature": "Features",
    "tech-stack": "Tech Stack",
}

# Edge types that flow "downstream" (parent → child direction)
DOWNSTREAM_EDGES = {
    "epic_requirement", "epic_story", "story_requirement",
    "task_feature", "task_story", "task_requirement",
    "screen_story", "story_screen", "flow_persona", "flow_screen",
    "screen_component", "diagram_of",
    "feature_story", "feature_requirement", "feature_task",
    # Cross-link types (added by _build_cross_links or link_manifest)
    "req_api", "req_story", "req_entity", "req_test", "req_task",
    "story_test", "story_screen", "story_task",
    "epic_story",
    "entity_api", "entity_task",
    "api_story", "api_screen", "api_task", "screen_api",
    "screen_entity", "screen_component",
    "persona_story", "persona_screen",
    "test_api", "test_story",
    "diagram_entity", "component_api",
    "flow_screen", "flow_story", "flow_persona",
    "screen_child", "tech_component",
}


class TraceIndex:
    """Pre-computed artifact index for fast sort/filter/paginate/trace."""

    def __init__(self):
        self.project_dir: Optional[Path] = None
        self.link_graph = LinkGraph()

        # Flat lookup: id → {id, type, title, description, priority, ...}
        self._artifacts: Dict[str, dict] = {}
        # type → [ids]  (sorted by id)
        self._by_type: Dict[str, List[str]] = defaultdict(list)
        # Full-text search index: id → lowercase searchable text
        self._search_idx: Dict[str, str] = {}

    # ── Build ────────────────────────────────────────────────────────

    def build(self, project_dir: Path, project_data: dict):
        """
        Build the index from a loaded project.

        Args:
            project_dir:  Path to the project output directory.
            project_data: The dict returned by server._load_folder_format().
        """
        self.project_dir = Path(project_dir)
        self._artifacts.clear()
        self._by_type.clear()
        self._search_idx.clear()

        # 1) Let LinkGraph build its node/edge graph from disk
        self.link_graph.build_from_project(self.project_dir)

        # 2) Supplement from project_data (which already has richer parsed
        #    objects that LinkGraph may not fully capture, e.g. test cases,
        #    API endpoint details loaded by server._load_folder_format).
        self._index_from_link_graph()
        self._index_extra_from_project_data(project_data)

        # 3) Cross-links: prefer pre-computed link_manifest.json (zero heuristics),
        #    fall back to heuristic matching for projects without a manifest.
        manifest_path = self.project_dir / "link_manifest.json"
        if manifest_path.exists():
            self._load_link_manifest(manifest_path)
        else:
            self._build_cross_links(project_data)

        # 4) Build search index
        for aid, art in self._artifacts.items():
            text = f"{art.get('title', '')} {art.get('description', '')}"
            self._search_idx[aid] = text.lower()

        print(f"[TraceIndex] Indexed {len(self._artifacts)} artifacts, "
              f"{len(self.link_graph.edges)} edges")

    def _load_link_manifest(self, manifest_path: Path):
        """Load pre-computed edges from link_manifest.json.

        Each edge is only added if both src and dst exist in the artifact index,
        so stale or cross-project IDs are silently skipped.
        """
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            edges = data.get("edges", [])
            loaded = 0
            for edge in edges:
                src = edge.get("src", "")
                dst = edge.get("dst", "")
                etype = edge.get("type", "link")
                if src in self._artifacts and dst in self._artifacts:
                    self.link_graph._adjacency.setdefault(src, {})[dst] = etype
                    self.link_graph._reverse_adjacency.setdefault(dst, {})[src] = etype
                    loaded += 1
            skipped = len(edges) - loaded
            print(f"[TraceIndex] link_manifest: {loaded} edges loaded"
                  + (f", {skipped} skipped (unknown IDs)" if skipped else ""))
        except Exception as exc:
            print(f"[TraceIndex] Warning: could not load link_manifest.json: {exc}")
            # Fall back to heuristics so the dashboard still works
            self._build_cross_links({})

    # ── Private: indexing helpers ────────────────────────────────────

    def _index_from_link_graph(self):
        """Import every node from LinkGraph into the flat index."""
        for nid, data in self.link_graph.nodes.items():
            if nid in self._artifacts:
                continue
            # Skip "node-" prefixed duplicates when base ID exists
            if nid.startswith("node-") and nid[5:] in self.link_graph.nodes:
                continue
            art_type = data.get("type", "unknown")
            # Normalise type names
            if art_type == "user_story":
                art_type = "user-story"
            elif art_type == "functional" or art_type == "non_functional":
                art_type = "requirement"

            rec = {
                "id": nid,
                "type": art_type,
                "title": data.get("title", nid),
                "description": data.get("description", ""),
                "priority": data.get("priority", ""),
                "status": data.get("validation_status", data.get("status", "")),
                "file_path": data.get("file", ""),
            }
            self._artifacts[nid] = rec
            self._by_type[art_type].append(nid)

    def _index_extra_from_project_data(self, pd: dict):
        """Pick up artifacts from project_data that LinkGraph may miss."""

        # Test cases — often only referenced in traceability, not as
        # LinkGraph nodes.  The server parses them from .feature files.
        # Server uses "tests" key; older code uses "test_cases".
        for tc in (pd.get("tests", []) or pd.get("test_cases", [])):
            if not isinstance(tc, dict):
                continue
            tid = tc.get("id", "")
            if not tid or tid in self._artifacts:
                continue
            self._artifacts[tid] = {
                "id": tid,
                "type": "test",
                "title": tc.get("title", tc.get("name", tid)),
                "description": tc.get("description", ""),
                "priority": tc.get("priority", ""),
                "status": tc.get("status", ""),
                "parent_story": tc.get("parent_user_story_id", "") or tc.get("linked_user_story", ""),
            }
            self._by_type["test"].append(tid)
            # Link to parent story if not already present
            parent = (
                tc.get("parent_user_story_id", "")
                or tc.get("linked_user_story", "")
                or tc.get("user_story_id", "")
            )
            if parent:
                self.link_graph._add_edge(tid, parent, "test_story")

        # API endpoints from parsed openapi
        for ep in pd.get("api_endpoints", []):
            if not isinstance(ep, dict):
                continue
            eid = ep.get("id", "")
            if not eid or eid in self._artifacts:
                continue
            method = ep.get("method", "")
            path = ep.get("path", "")
            self._artifacts[eid] = {
                "id": eid,
                "type": "api",
                "title": f"{method} {path}" if method else ep.get("title", eid),
                "description": ep.get("description", ep.get("summary", "")),
                "priority": "",
                "status": "",
            }
            self._by_type["api"].append(eid)

        # Screens from individual SCREEN-*.json files (if server parsed them)
        for scr in pd.get("screens", []):
            if not isinstance(scr, dict):
                continue
            sid = scr.get("id", "")
            if not sid or sid in self._artifacts:
                continue
            self._artifacts[sid] = {
                "id": sid,
                "type": "screen",
                "title": scr.get("name", scr.get("title", sid)),
                "description": scr.get("description", ""),
                "priority": "",
                "status": "",
            }
            self._by_type["screen"].append(sid)

        # Entities from data dictionary
        _entities = pd.get("entities", [])
        if not _entities:
            dd = pd.get("data_dictionary", {})
            if isinstance(dd, dict):
                _entities = dd.get("entities", [])
        for ent in _entities:
            if not isinstance(ent, dict):
                continue
            eid = ent.get("id", ent.get("name", ""))
            if not eid or eid in self._artifacts:
                continue
            self._artifacts[eid] = {
                "id": eid,
                "type": "entity",
                "title": ent.get("name", eid),
                "description": ent.get("description", ""),
                "priority": "",
                "status": "",
            }
            self._by_type["entity"].append(eid)

        # Tasks from features dict
        for feat_tasks in pd.get("tasks", {}).values() if isinstance(pd.get("tasks"), dict) else []:
            if not isinstance(feat_tasks, list):
                continue
            for task in feat_tasks:
                tid = task.get("id", "")
                if not tid or tid in self._artifacts:
                    continue
                self._artifacts[tid] = {
                    "id": tid,
                    "type": "task",
                    "title": task.get("title", tid),
                    "description": task.get("description", ""),
                    "priority": task.get("complexity", ""),
                    "status": task.get("status", ""),
                    "phase": task.get("phase", ""),
                    "estimated_hours": task.get("estimated_hours", 0),
                }
                self._by_type["task"].append(tid)

        # User stories from project_data
        for us in pd.get("user_stories", []):
            if not isinstance(us, dict):
                continue
            uid = us.get("id", "")
            if not uid or uid in self._artifacts:
                continue
            self._artifacts[uid] = {
                "id": uid,
                "type": "user-story",
                "title": us.get("title", uid),
                "description": us.get("action", us.get("description", "")),
                "priority": us.get("priority", ""),
                "status": us.get("status", ""),
                "persona": us.get("persona", ""),
            }
            self._by_type["user-story"].append(uid)

        # Epics from project_data
        for ep in pd.get("epics", []):
            if not isinstance(ep, dict):
                continue
            eid = ep.get("id", "")
            if not eid or eid in self._artifacts:
                continue
            self._artifacts[eid] = {
                "id": eid,
                "type": "epic",
                "title": ep.get("title", ep.get("name", eid)),
                "description": ep.get("description", ""),
                "priority": ep.get("priority", ""),
                "status": ep.get("status", ""),
            }
            self._by_type["epic"].append(eid)

        # Personas from project_data
        for p in pd.get("personas", []):
            if not isinstance(p, dict):
                continue
            pid = p.get("id", "")
            if not pid or pid in self._artifacts:
                continue
            self._artifacts[pid] = {
                "id": pid,
                "type": "persona",
                "title": p.get("name", p.get("role", pid)),
                "description": p.get("description", p.get("bio", "")),
                "priority": "",
                "status": "",
            }
            self._by_type["persona"].append(pid)

        # User flows from project_data
        for uf in pd.get("user_flows", []):
            if not isinstance(uf, dict):
                continue
            fid = uf.get("id", "")
            if not fid or fid in self._artifacts:
                continue
            self._artifacts[fid] = {
                "id": fid,
                "type": "user-flow",
                "title": uf.get("name", uf.get("title", fid)),
                "description": uf.get("description", ""),
                "priority": "",
                "status": "",
            }
            self._by_type["user-flow"].append(fid)

        # Tech stack (singleton) — link to all components
        ts = pd.get("tech_stack")
        if isinstance(ts, dict):
            ts_id = ts.get("id", "TECH-STACK")
            if ts_id not in self._artifacts:
                self._artifacts[ts_id] = {
                    "id": ts_id,
                    "type": "tech-stack",
                    "title": f"{ts.get('backend_framework', '')} / {ts.get('frontend_framework', '')}".strip(" /"),
                    "description": ts.get("rationale", ""),
                    "priority": "",
                    "status": "",
                }
                self._by_type["tech-stack"].append(ts_id)

        # Features from project_data
        for feat in pd.get("features", []):
            if not isinstance(feat, dict):
                continue
            fid = feat.get("id", "")
            if not fid or fid in self._artifacts:
                continue
            self._artifacts[fid] = {
                "id": fid,
                "type": "feature",
                "title": feat.get("title", feat.get("name", fid)),
                "description": feat.get("description", ""),
                "priority": feat.get("priority", ""),
                "status": feat.get("status", ""),
            }
            self._by_type["feature"].append(fid)

        # Components from project_data
        for comp in pd.get("ui_components", []):
            if not isinstance(comp, dict):
                continue
            cid = comp.get("id", "")
            if not cid or cid in self._artifacts:
                continue
            self._artifacts[cid] = {
                "id": cid,
                "type": "component",
                "title": comp.get("name", cid),
                "description": comp.get("description", ""),
                "priority": "",
                "status": "",
            }
            self._by_type["component"].append(cid)

        # Sort each type list by ID for consistency
        for t in self._by_type:
            self._by_type[t].sort()

    # ── Cross-linking heuristics ────────────────────────────────────

    def _build_cross_links(self, pd: dict):
        """
        Build cross-links between artifact types using heuristic matching.

        Ports the 12 key linking strategies from autoLinker.js into the
        server-side index so the Trace Explorer has the same rich edges
        that the Canvas graph gets from frontend JS auto-linkers.
        """
        edges_before = len(self.link_graph.edges)
        added = 0

        # Gather raw data lists from project_data
        # (server uses "ui_components" not "components", "tests" not "test_cases")
        screens = pd.get("screens", [])
        components = pd.get("ui_components", []) or pd.get("components", [])
        api_endpoints = pd.get("api_endpoints", [])
        entities = pd.get("entities", [])
        # Entities may be nested in data_dictionary
        if not entities:
            dd = pd.get("data_dictionary", {})
            if isinstance(dd, dict):
                entities = dd.get("entities", [])
        test_cases = pd.get("tests", []) or pd.get("test_cases", [])
        personas = pd.get("personas", [])
        user_stories = pd.get("user_stories", [])
        diagrams = pd.get("diagrams", [])
        tasks_dict = pd.get("tasks", {})  # {feature_id: [tasks]}
        epics = pd.get("epics", [])
        features = pd.get("features", [])
        user_flows = pd.get("user_flows", [])

        # Helper: only add edge if both nodes exist in our index
        def _link(src: str, dst: str, edge_type: str) -> bool:
            nonlocal added
            if not src or not dst or src == dst:
                return False
            if src not in self._artifacts or dst not in self._artifacts:
                return False
            # Avoid duplicating existing edges
            existing = self.link_graph._edge_types.get((src, dst))
            if existing:
                return False
            rev = self.link_graph._edge_types.get((dst, src))
            if rev:
                return False
            self.link_graph._add_edge(src, dst, edge_type)
            added += 1
            return True

        # Helper: find artifact id by partial match within a type
        def _find_id(art_type: str, partial: str) -> Optional[str]:
            if not partial:
                return None
            # Exact match first
            if partial in self._artifacts:
                return partial
            # Try with "node-" prefix (LinkGraph convention)
            if f"node-{partial}" in self._artifacts:
                return f"node-{partial}"
            partial_upper = partial.upper()
            for aid in self._by_type.get(art_type, []):
                if partial_upper in aid.upper():
                    return aid
            # For entities: strip common prefixes like "ENTITY-"
            if art_type == "entity" and "-" in partial:
                suffix = partial.split("-", 1)[1]
                for aid in self._by_type.get("entity", []):
                    if suffix.upper() in aid.upper():
                        return aid
            return None

        # ── 1. Screen → Component (via content_types matching) ──────
        if screens and components:
            CONTENT_TO_COMP = {
                "dashboard": {"card", "chart"},
                "kpis": {"card", "chart"},
                "real-time-dashboard": {"card", "chart", "table"},
                "form": {"input", "button", "select"},
                "forms": {"input", "button", "select"},
                "list": {"table"},
                "table": {"table"},
                "filters": {"input", "select", "button"},
                "search": {"input"},
                "status": {"badge"},
                "status-overview": {"badge", "card"},
                "alerts": {"badge", "modal"},
                "configuration": {"input", "select", "button"},
                "security": {"input", "button"},
                "detail-view": {"card", "table"},
                "rules-engine": {"table", "input"},
                "charts": {"chart"},
                "logs": {"table"},
                "queue": {"table", "badge"},
                "quick-actions": {"button"},
                "modal": {"modal"},
                "navigation": {"navigation"},
                "progress": {"progress"},
            }
            for scr in screens:
                sid = scr.get("id", "")
                if not sid:
                    continue
                # Method 1: direct component list
                for comp_ref in (scr.get("components") or []):
                    comp_id = comp_ref if isinstance(comp_ref, str) else ""
                    if comp_id:
                        _link(sid, comp_id, "screen_component")
                # Method 2: content_types → component_type matching
                content_types = scr.get("content_types") or []
                if content_types:
                    matching = set()
                    for ct in content_types:
                        matching.update(CONTENT_TO_COMP.get(ct, set()))
                    if matching:
                        for comp in components:
                            cid = comp.get("id", "")
                            ctype = (comp.get("component_type") or "").lower()
                            if ctype in matching:
                                _link(sid, cid, "screen_component")

        # ── 1b. IA-Screen children + content_types from LinkGraph ────
        # LinkGraph loads IA screens with children and content_types
        if components:
            for nid, ndata in self.link_graph.nodes.items():
                if ndata.get("type") != "screen":
                    continue
                data = ndata.get("data", {})
                # IA parent → child links
                for child_id in (data.get("children") or []):
                    _link(nid, child_id, "screen_child")
                # content_types → component matching
                content_types = data.get("content_types") or []
                if content_types:
                    matching = set()
                    for ct in content_types:
                        matching.update(CONTENT_TO_COMP.get(ct, set()))
                    if matching:
                        for comp in components:
                            cid = comp.get("id", "")
                            ctype = (comp.get("component_type") or "").lower()
                            if ctype in matching:
                                _link(nid, cid, "screen_component")

        # ── 2. Component → Screen (via parent_screen_ids) ───────────
        if components:
            for comp in components:
                cid = comp.get("id", "")
                for psid in (comp.get("parent_screen_ids") or []):
                    _link(psid, cid, "screen_component")
                ps = comp.get("parent_screen") or comp.get("screen_id", "")
                if ps:
                    found = _find_id("screen", ps)
                    if found:
                        _link(found, cid, "screen_component")

        # ── 3. Screen → User Story (via parent_user_story) ──────────
        if screens:
            for scr in screens:
                sid = scr.get("id", "")
                parent_us = scr.get("parent_user_story") or scr.get("user_story_id", "")
                if parent_us:
                    found = _find_id("user-story", parent_us)
                    if found:
                        _link(found, sid, "story_screen")

        # ── 4. API → Requirement (via parent_requirement_id) ────────
        if api_endpoints:
            for ep in api_endpoints:
                eid = ep.get("id", "")
                parent_req = ep.get("parent_requirement_id") or ep.get("requirement_id", "")
                if parent_req:
                    found = _find_id("requirement", parent_req)
                    if found:
                        _link(found, eid, "req_api")
                for rq in (ep.get("linked_requirements") or []):
                    found = _find_id("requirement", rq)
                    if found:
                        _link(found, eid, "req_api")

        # ── 5. Entity → API (via path segment matching) ─────────────
        if entities and api_endpoints:
            entity_map = {}
            for ent in entities:
                name = (ent.get("name") or ent.get("id", "")).lower()
                if name:
                    eid = ent.get("id") or ent.get("name", "")
                    entity_map[name] = eid
                    if name.endswith("s"):
                        entity_map[name[:-1]] = eid
            for ep in api_endpoints:
                path = ep.get("path", "")
                ep_id = ep.get("id", "")
                segments = [s for s in path.split("/") if s and not s.startswith("{")]
                for seg in segments:
                    seg_lower = seg.lower()
                    ent_id = entity_map.get(seg_lower) or entity_map.get(
                        seg_lower.rstrip("s")
                    )
                    if ent_id:
                        _link(ent_id, ep_id, "entity_api")

        # ── 6. Screen → Entity (via data_requirements path) ────────
        if screens and entities:
            entity_map = {}
            for ent in entities:
                name = (ent.get("name") or ent.get("id", "")).lower()
                if name:
                    eid = ent.get("id") or ent.get("name", "")
                    entity_map[name] = eid
                    if name.endswith("s"):
                        entity_map[name[:-1]] = eid
            for scr in screens:
                sid = scr.get("id", "")
                for api_ref in (scr.get("data_requirements") or []):
                    path = re.sub(
                        r"^(GET|POST|PUT|DELETE|PATCH|WS)\s+", "", api_ref, flags=re.I
                    ).strip()
                    segments = [s for s in path.split("/") if s and not s.startswith("{")]
                    for seg in segments:
                        seg_lower = seg.lower()
                        ent_id = entity_map.get(seg_lower) or entity_map.get(
                            seg_lower.rstrip("s")
                        )
                        if ent_id:
                            _link(sid, ent_id, "screen_entity")

        # ── 7. API → Screen (via screen.data_requirements) ──────────
        if screens and api_endpoints:
            path_to_api = {}
            for ep in api_endpoints:
                p = (ep.get("path") or "").lower()
                if p:
                    path_to_api[p] = ep.get("id", "")
            for scr in screens:
                sid = scr.get("id", "")
                for api_ref in (scr.get("data_requirements") or []):
                    path = re.sub(
                        r"^(GET|POST|PUT|DELETE|PATCH|WS)\s+", "", api_ref, flags=re.I
                    ).strip().lower()
                    ep_id = path_to_api.get(path, "")
                    if ep_id:
                        _link(ep_id, sid, "api_screen")

        # ── 8. Persona → User Story (via role matching) ─────────────
        if personas and user_stories:
            for persona in personas:
                pid = persona.get("id", "")
                prole = (persona.get("role") or "").lower()
                pname = (persona.get("name") or "").lower()
                if not prole and not pname:
                    continue
                for story in user_stories:
                    sp = (story.get("persona") or "").lower()
                    usid = story.get("id", "")
                    if sp and (
                        (prole and prole in sp)
                        or (pname and pname in sp)
                    ):
                        _link(pid, usid, "persona_story")

        # ── 9. Test → API (via API path in content) ─────────────────
        if test_cases and api_endpoints:
            api_paths = []
            for ep in api_endpoints:
                p = (ep.get("path") or "").lower()
                if p:
                    api_paths.append((p, ep.get("id", "")))
            for tc in test_cases:
                tid = tc.get("id", "")
                content = (
                    tc.get("gherkin_content", "")
                    or tc.get("title", "")
                    or tc.get("description", "")
                ).lower()
                if not content:
                    continue
                for path, ep_id in api_paths:
                    if path in content:
                        _link(tid, ep_id, "test_api")

        # ── 10. Diagram → Entity (via mermaid code) ─────────────────
        if entities:
            entity_names = set()
            ename_to_id = {}
            for ent in entities:
                name = (ent.get("name") or ent.get("id", "")).lower()
                if name and len(name) > 2:
                    entity_names.add(name)
                    ename_to_id[name] = ent.get("id") or ent.get("name", "")
            # Check diagrams from project_data
            for diag in diagrams:
                did = diag.get("id", "")
                code = (
                    diag.get("mermaid_code") or diag.get("code") or ""
                ).lower()
                if not code:
                    continue
                # Try both raw ID and prefixed version
                actual_id = did if did in self._artifacts else f"diagram_{did}"
                for ename in entity_names:
                    if ename in code:
                        ent_id = ename_to_id[ename]
                        _link(actual_id, ent_id, "diagram_entity")
            # Also check LinkGraph diagram nodes (have mermaid_code in node data)
            for nid, ndata in self.link_graph.nodes.items():
                if ndata.get("type") != "diagram":
                    continue
                code = (ndata.get("mermaid_code") or ndata.get("code", "")).lower()
                if not code:
                    continue
                for ename in entity_names:
                    if ename in code:
                        ent_id = ename_to_id[ename]
                        _link(nid, ent_id, "diagram_entity")

        # ── 11. Task → Feature/Entity/API (via parent fields) ───────
        if isinstance(tasks_dict, dict):
            for feat_id, task_list in tasks_dict.items():
                if not isinstance(task_list, list):
                    continue
                feat_found = _find_id("feature", feat_id) or _find_id("epic", feat_id)
                for task in task_list:
                    tid = task.get("id", "")
                    if not tid:
                        continue
                    # Explicit parent_entity_id
                    pent = task.get("parent_entity_id", "")
                    if pent:
                        found_ent = _find_id("entity", pent)
                        if found_ent:
                            _link(found_ent, tid, "entity_task")
                    # Explicit parent_api_resource
                    papi = task.get("parent_api_resource", "")
                    if papi:
                        found_api = _find_id("api", papi)
                        if found_api:
                            _link(found_api, tid, "api_task")
                    # Explicit parent_requirement_id
                    preq = task.get("parent_requirement_id", "")
                    if preq:
                        found_req = _find_id("requirement", preq)
                        if found_req:
                            _link(found_req, tid, "req_task")
                    # Explicit parent_user_story_id
                    pus = task.get("parent_user_story_id", "")
                    if pus:
                        found_us = _find_id("user-story", pus)
                        if found_us:
                            _link(found_us, tid, "story_task")
                    # Feature parent from dict key
                    if feat_found:
                        _link(feat_found, tid, "feature_task")

        # ── 11b. Ungrouped Task → User Story (via title matching) ────
        # TASK-REFINE-* tasks follow pattern "Implement X" / "Test X"
        # where X matches a user story title.
        if isinstance(tasks_dict, dict) and user_stories:
            # Build story title → id lookup (normalized)
            import unicodedata
            def _norm(s):
                # Normalize umlauts and lowercase
                s = s.lower().strip()
                s = s.replace("ue", "u").replace("oe", "o").replace("ae", "a")
                s = s.replace("ss", "s")
                return s
            story_title_map: Dict[str, str] = {}
            for story in user_stories:
                stitle = story.get("title", "")
                sid = story.get("id", "")
                if stitle and sid:
                    story_title_map[_norm(stitle)] = sid

            for feat_id, task_list in tasks_dict.items():
                if not isinstance(task_list, list):
                    continue
                for task in task_list:
                    tid = task.get("id", "")
                    if not tid or tid not in self._artifacts:
                        continue
                    # Skip if already linked
                    if tid in self.link_graph._adjacency or tid in self.link_graph._reverse_adjacency:
                        continue
                    title = task.get("title", "")
                    # Strip "Implement " / "Test " prefix
                    for prefix in ("Implement ", "Test "):
                        if title.startswith(prefix):
                            feature_name = title[len(prefix):]
                            norm_name = _norm(feature_name)
                            matched_sid = story_title_map.get(norm_name)
                            if matched_sid:
                                _link(matched_sid, tid, "story_task")
                                break
                            # Partial match: story title contains task name or vice versa
                            for stitle_norm, sid in story_title_map.items():
                                if norm_name in stitle_norm or stitle_norm in norm_name:
                                    _link(sid, tid, "story_task")
                                    break
                            break

        # ── 12. Epic → Requirement + Epic → Story (from epic data) ──
        if epics:
            for epic in epics:
                eid = epic.get("id", "")
                for req_id in (epic.get("linked_requirements") or []):
                    found = _find_id("requirement", req_id)
                    if found:
                        _link(found, eid, "epic_requirement")
                for us_id in (epic.get("linked_user_stories") or []):
                    found = _find_id("user-story", us_id)
                    if found:
                        _link(eid, found, "epic_story")

        # ── 13. User Story → Requirement (via linked_requirement) ───
        if user_stories:
            for story in user_stories:
                usid = story.get("id", "")
                # Try multiple field names for requirement link
                req_id = (
                    story.get("linked_requirement")
                    or story.get("parent_requirement_id")
                    or ""
                )
                if req_id:
                    found = _find_id("requirement", req_id)
                    if found:
                        _link(found, usid, "req_story")
                # Also handle linked_requirement_ids array
                for rid in (story.get("linked_requirement_ids") or []):
                    found = _find_id("requirement", rid)
                    if found:
                        _link(found, usid, "req_story")

        # ── 14. Persona → Screen (via story intermediary) ───────────
        if personas and user_stories and screens:
            story_to_screens: Dict[str, List[str]] = defaultdict(list)
            for scr in screens:
                sus = scr.get("parent_user_story", "")
                if sus:
                    story_to_screens[sus].append(scr.get("id", ""))
            for persona in personas:
                pid = persona.get("id", "")
                prole = (persona.get("role") or "").lower()
                pname = (persona.get("name") or "").lower()
                for story in user_stories:
                    sp = (story.get("persona") or "").lower()
                    if sp and ((prole and prole in sp) or (pname and pname in sp)):
                        for scr_id in story_to_screens.get(story.get("id", ""), []):
                            _link(pid, scr_id, "persona_screen")

        # ── 15. Component → API (via parent screen data_reqs) ───────
        if components and screens and api_endpoints:
            screen_by_id = {s.get("id", ""): s for s in screens if s.get("id")}
            path_to_api = {}
            for ep in api_endpoints:
                p = (ep.get("path") or "").lower()
                if p:
                    path_to_api[p] = ep.get("id", "")
            for comp in components:
                cid = comp.get("id", "")
                for psid in (comp.get("parent_screen_ids") or []):
                    scr = screen_by_id.get(psid)
                    if not scr:
                        continue
                    for api_ref in (scr.get("data_requirements") or []):
                        path = re.sub(
                            r"^(GET|POST|PUT|DELETE|PATCH|WS)\s+", "", api_ref, flags=re.I
                        ).strip().lower()
                        ep_id = path_to_api.get(path, "")
                        if ep_id:
                            _link(cid, ep_id, "component_api")

        # ── 16. User Story → Epic (via parent_epic_id) ──────────────
        if user_stories:
            for story in user_stories:
                usid = story.get("id", "")
                epic_id = story.get("parent_epic_id", "")
                if epic_id:
                    found = _find_id("epic", epic_id)
                    if found:
                        _link(found, usid, "epic_story")

        # ── 17. User Flow → Screen + Persona (via steps/actor/links) ─
        if user_flows:
            # Pre-build persona name lookup
            persona_name_map = {}
            for persona in personas:
                pname = (persona.get("name") or "").lower()
                prole = (persona.get("role") or "").lower()
                pid = persona.get("id", "")
                if pname:
                    persona_name_map[pname] = pid
                if prole:
                    persona_name_map[prole] = pid

            for flow in user_flows:
                fid = flow.get("id", "")
                # Flow → screens via steps
                for step in (flow.get("steps") or []):
                    screen_name = step.get("screen", "")
                    if screen_name:
                        for scr in screens:
                            sname = (scr.get("name") or scr.get("title", "")).lower().replace(" ", "")
                            if screen_name.lower().replace(" ", "") in sname or sname in screen_name.lower().replace(" ", ""):
                                _link(fid, scr.get("id", ""), "flow_screen")
                                break
                # Flow → persona via actor or persona field
                flow_actor = (flow.get("actor") or flow.get("persona") or "").lower()
                if flow_actor:
                    matched_pid = persona_name_map.get(flow_actor)
                    if not matched_pid:
                        # Partial match
                        for key, pid in persona_name_map.items():
                            if flow_actor in key or key in flow_actor:
                                matched_pid = pid
                                break
                    if matched_pid:
                        _link(matched_pid, fid, "flow_persona")
                # Flow → explicit linked IDs
                for sid in (flow.get("linked_screen_ids") or []):
                    _link(fid, sid, "flow_screen")
                lpid = flow.get("linked_persona_id", "")
                if lpid:
                    _link(lpid, fid, "flow_persona")
                for usid in (flow.get("linked_user_story_ids") or []):
                    _link(usid, fid, "flow_story")

        # ── 18. Entity → Requirement (via source_requirements) ──────
        if entities:
            for ent in entities:
                eid = ent.get("id") or ent.get("name", "")
                for req_id in (ent.get("source_requirements") or []):
                    found = _find_id("requirement", req_id)
                    if found:
                        _link(found, eid, "req_entity")

        # ── 19. Tech Stack → Components ────────────────────────────
        ts = pd.get("tech_stack")
        if isinstance(ts, dict) and components:
            ts_id = ts.get("id", "TECH-STACK")
            for comp in components:
                cid = comp.get("id", "")
                if cid:
                    _link(ts_id, cid, "tech_component")

        new_edges = added
        print(f"[TraceIndex] Cross-linking added {new_edges} edges "
              f"(was {edges_before}, now {len(self.link_graph.edges)})")

    # ── Query (paginated, sorted, filtered) ──────────────────────────

    def query(
        self,
        artifact_type: Optional[str] = None,
        sort_by: str = "id",
        sort_dir: str = "asc",
        page: int = 1,
        page_size: int = 50,
        filters: Optional[Dict[str, str]] = None,
        search: str = "",
    ) -> dict:
        """
        Paginated sorted filtered artifact list.

        Returns dict with keys: items, total, page, page_size, total_pages.
        """
        # 1) Collect candidate IDs
        if artifact_type and artifact_type in self._by_type:
            ids = list(self._by_type[artifact_type])
        elif artifact_type:
            ids = []
        else:
            ids = list(self._artifacts.keys())

        # 2) Full-text search filter
        if search:
            q = search.lower()
            ids = [i for i in ids if q in self._search_idx.get(i, "")]

        # 3) Field filters
        if filters:
            for fld, val in filters.items():
                val_lower = val.lower()
                ids = [
                    i for i in ids
                    if val_lower in str(self._artifacts.get(i, {}).get(fld, "")).lower()
                ]

        total = len(ids)

        # 4) Sort
        reverse = sort_dir == "desc"
        ids.sort(
            key=lambda i: str(self._artifacts.get(i, {}).get(sort_by, "")).lower(),
            reverse=reverse,
        )

        # 5) Paginate
        total_pages = max(1, math.ceil(total / page_size))
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        page_ids = ids[start : start + page_size]

        # 6) Build summary items (light — no full data)
        items = []
        for aid in page_ids:
            art = self._artifacts.get(aid, {})
            # Count children/parents
            downstream = len(self.link_graph._adjacency.get(aid, set()))
            upstream = len(self.link_graph._reverse_adjacency.get(aid, set()))
            items.append({
                "id": aid,
                "type": art.get("type", ""),
                "title": art.get("title", ""),
                "priority": art.get("priority", ""),
                "status": art.get("status", ""),
                "downstream_count": downstream,
                "upstream_count": upstream,
            })

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    # ── Detail ───────────────────────────────────────────────────────

    def get_detail(self, artifact_id: str) -> Optional[dict]:
        """Full artifact data for detail view."""
        art = self._artifacts.get(artifact_id)
        if not art:
            return None

        # Merge with LinkGraph node data (which stores the full `data` dict)
        lg_node = self.link_graph.get_node(artifact_id)
        full_data = {}
        if lg_node:
            full_data = lg_node.get("data", lg_node)

        result = {**art, "data": full_data}

        # Add direct connections summary
        result["connections"] = self._get_connections(artifact_id)

        return result

    def _get_connections(self, artifact_id: str) -> dict:
        """Summarise direct connections for an artifact."""
        downstream = []
        for target in self.link_graph._adjacency.get(artifact_id, set()):
            edge_type = self.link_graph._edge_types.get(
                (artifact_id, target), "related"
            )
            tgt_art = self._artifacts.get(target, {})
            downstream.append({
                "id": target,
                "type": tgt_art.get("type", ""),
                "title": tgt_art.get("title", target),
                "edge_type": edge_type,
            })

        upstream = []
        for source in self.link_graph._reverse_adjacency.get(artifact_id, set()):
            edge_type = self.link_graph._edge_types.get(
                (source, artifact_id), "related"
            )
            src_art = self._artifacts.get(source, {})
            upstream.append({
                "id": source,
                "type": src_art.get("type", ""),
                "title": src_art.get("title", source),
                "edge_type": edge_type,
            })

        return {"upstream": upstream, "downstream": downstream}

    # ── Trace chain ──────────────────────────────────────────────────

    def get_trace_chain(self, artifact_id: str, depth: int = 5) -> dict:
        """
        Build directional trace chain: upstream toward epics,
        downstream toward tests/tasks.

        Returns {artifact, upstream: [...], downstream: [...]}.
        """
        art = self._artifacts.get(artifact_id)
        if not art:
            return {"artifact": None, "upstream": [], "downstream": []}

        upstream = self._bfs_directional(artifact_id, "upstream", depth)
        downstream = self._bfs_directional(artifact_id, "downstream", depth)

        return {
            "artifact": {
                "id": artifact_id,
                "type": art.get("type", ""),
                "title": art.get("title", ""),
            },
            "upstream": upstream,
            "downstream": downstream,
        }

    def _bfs_directional(
        self, start_id: str, direction: str, max_depth: int
    ) -> List[dict]:
        """BFS in one direction only (upstream or downstream)."""
        visited: Set[str] = {start_id}
        result: List[dict] = []
        # queue: (node_id, depth, edge_type_from_parent)
        queue: List[Tuple[str, int, str]] = []

        if direction == "upstream":
            # Follow reverse_adjacency (incoming edges = who points to me)
            for source in self.link_graph._reverse_adjacency.get(start_id, set()):
                et = self.link_graph._edge_types.get((source, start_id), "related")
                queue.append((source, 1, et))
        else:
            # Follow adjacency (outgoing edges = who I point to)
            for target in self.link_graph._adjacency.get(start_id, set()):
                et = self.link_graph._edge_types.get((start_id, target), "related")
                queue.append((target, 1, et))

        while queue:
            nid, d, edge_type = queue.pop(0)
            if nid in visited:
                continue
            visited.add(nid)

            art = self._artifacts.get(nid, {})
            result.append({
                "id": nid,
                "type": art.get("type", ""),
                "title": art.get("title", nid),
                "link_type": edge_type,
                "depth": d,
            })

            if d >= max_depth:
                continue

            if direction == "upstream":
                for source in self.link_graph._reverse_adjacency.get(nid, set()):
                    if source not in visited:
                        et = self.link_graph._edge_types.get((source, nid), "related")
                        queue.append((source, d + 1, et))
            else:
                for target in self.link_graph._adjacency.get(nid, set()):
                    if target not in visited:
                        et = self.link_graph._edge_types.get((nid, target), "related")
                        queue.append((target, d + 1, et))

        # Sort by depth then type order
        type_rank = {t: i for i, t in enumerate(TYPE_ORDER)}
        result.sort(key=lambda x: (x["depth"], type_rank.get(x["type"], 99)))
        return result

    # ── Impact analysis ──────────────────────────────────────────────

    def get_impact(self, artifact_id: str, depth: int = 3) -> dict:
        """
        Downstream-only impact analysis.  What would be affected if
        this artifact changes?

        Returns {artifact, impacted: [...], counts_by_type: {...}, total}.
        """
        art = self._artifacts.get(artifact_id)
        if not art:
            return {"artifact": None, "impacted": [], "counts_by_type": {}, "total": 0}

        # Get all linked nodes (both directions) from LinkGraph
        all_linked = self.link_graph.get_linked_nodes(artifact_id, depth=depth)

        impacted = []
        counts: Dict[str, int] = defaultdict(int)
        for nid in all_linked:
            a = self._artifacts.get(nid, {})
            atype = a.get("type", "unknown")
            counts[atype] += 1
            impacted.append({
                "id": nid,
                "type": atype,
                "title": a.get("title", nid),
            })

        return {
            "artifact": {
                "id": artifact_id,
                "type": art.get("type", ""),
                "title": art.get("title", ""),
            },
            "impacted": impacted,
            "counts_by_type": dict(counts),
            "total": len(impacted),
        }

    # ── Navigation tree ──────────────────────────────────────────────

    def get_tree(self) -> dict:
        """
        Hierarchical tree for left-pane navigation.

        Returns {types: [{type, label, count, children: [...]}]}.
        """
        types = []
        for t in TYPE_ORDER:
            ids = self._by_type.get(t, [])
            if not ids:
                continue
            types.append({
                "type": t,
                "label": TYPE_LABELS.get(t, t),
                "count": len(ids),
            })

        return {"types": types}

    # ── Stats ────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Counts by type, total links, orphan count."""
        counts = {t: len(ids) for t, ids in self._by_type.items() if ids}
        return {
            "total_artifacts": len(self._artifacts),
            "total_links": len(self.link_graph.edges),
            "orphan_count": len(self.link_graph.get_orphan_nodes()),
            "counts_by_type": counts,
        }

    # ── Search ───────────────────────────────────────────────────────

    def search(
        self, query_text: str, types: Optional[List[str]] = None, limit: int = 50
    ) -> List[dict]:
        """Full-text search across title + description."""
        q = query_text.lower()
        results = []
        for aid, text in self._search_idx.items():
            if q not in text:
                continue
            art = self._artifacts.get(aid, {})
            if types and art.get("type", "") not in types:
                continue
            # Simple relevance: title match > description match
            score = 2 if q in art.get("title", "").lower() else 1
            results.append({
                "id": aid,
                "type": art.get("type", ""),
                "title": art.get("title", ""),
                "description": art.get("description", "")[:200],
                "score": score,
            })
        results.sort(key=lambda x: (-x["score"], x["title"]))
        return results[:limit]

    # ── Update (edit + write-back) ───────────────────────────────────

    def update_artifact(self, artifact_id: str, field: str, value: Any) -> dict:
        """
        Update an artifact field in-memory and write back to source file.

        Returns {success, impacted_ids}.
        """
        art = self._artifacts.get(artifact_id)
        if not art:
            return {"success": False, "error": "Artifact not found", "impacted_ids": []}

        # Update in-memory
        art[field] = value

        # Update LinkGraph node
        lg_node = self.link_graph.get_node(artifact_id)
        if lg_node:
            lg_node[field] = value

        # Update search index
        text = f"{art.get('title', '')} {art.get('description', '')}"
        self._search_idx[artifact_id] = text.lower()

        # Write back to disk
        success = self._write_back(artifact_id, field, value)

        # Compute impacted IDs
        impacted = self.link_graph.get_linked_nodes(artifact_id, depth=2)

        return {
            "success": success,
            "impacted_ids": impacted,
        }

    def _write_back(self, artifact_id: str, field: str, value: Any) -> bool:
        """Write the updated field back to its source file on disk."""
        if not self.project_dir:
            return False

        art = self._artifacts.get(artifact_id, {})
        art_type = art.get("type", "")

        try:
            if art_type == "requirement":
                return self._write_back_requirement(artifact_id, field, value)
            elif art_type == "user-story":
                return self._write_back_user_story(artifact_id, field, value)
            elif art_type == "task":
                return self._write_back_task(artifact_id, field, value)
            elif art_type == "diagram":
                return self._write_back_diagram(artifact_id, field, value)
            # Other types: best-effort via LinkGraph node data
            return False
        except Exception as e:
            print(f"[TraceIndex] Write-back failed for {artifact_id}: {e}")
            return False

    def _write_back_requirement(self, aid: str, field: str, value: Any) -> bool:
        """Update requirement in journal.json."""
        journal_path = self.project_dir / "journal.json"
        if not journal_path.exists():
            return False

        with open(journal_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        nodes = data.get("nodes", {})
        # Try both the artifact id and node-prefixed variant
        node_key = None
        for key in [aid, f"node-{aid}"]:
            if key in nodes:
                node_key = key
                break

        if node_key is None:
            return False

        nodes[node_key][field] = value

        with open(journal_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True

    def _write_back_user_story(self, aid: str, field: str, value: Any) -> bool:
        """Update user story in user_stories.json."""
        us_path = self.project_dir / "user_stories.json"
        if not us_path.exists():
            return False

        with open(us_path, "r", encoding="utf-8") as f:
            stories = json.load(f)

        if not isinstance(stories, list):
            stories = stories.get("user_stories", [])

        for story in stories:
            if story.get("id") == aid:
                story[field] = value
                with open(us_path, "w", encoding="utf-8") as f:
                    json.dump(stories, f, indent=2, ensure_ascii=False)
                return True
        return False

    def _write_back_task(self, aid: str, field: str, value: Any) -> bool:
        """Update task in tasks/task_list.json."""
        tasks_path = self.project_dir / "tasks" / "task_list.json"
        if not tasks_path.exists():
            return False

        with open(tasks_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", {})
        for feat_tasks in features.values():
            for task in feat_tasks:
                if task.get("id") == aid:
                    task[field] = value
                    with open(tasks_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    return True
        return False

    def _write_back_diagram(self, aid: str, field: str, value: Any) -> bool:
        """Update diagram .mmd file."""
        if field != "content":
            return False
        lg_node = self.link_graph.get_node(aid)
        if not lg_node:
            return False
        file_path = lg_node.get("file", "")
        if not file_path:
            return False
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(value)
        return True
