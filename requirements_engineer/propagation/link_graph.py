"""
Link Graph - Maintains a graph of all node relationships for fast traversal.

Builds from project files and supports queries for linked nodes and orphan detection.
"""

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Tuple

from .models import Edge


class LinkGraph:
    """
    Maintains a graph of all node relationships for fast traversal.

    Rebuilds on project load, supports incremental updates on changes.
    """

    def __init__(self):
        """Initialize an empty link graph."""
        self.nodes: Dict[str, dict] = {}  # node_id -> node data
        self.edges: List[Edge] = []
        self._adjacency: Dict[str, Set[str]] = defaultdict(set)  # For fast lookup
        self._reverse_adjacency: Dict[str, Set[str]] = defaultdict(set)  # Incoming edges
        self._edge_types: Dict[Tuple[str, str], str] = {}  # (source, target) -> edge_type

    def clear(self):
        """Clear all nodes and edges."""
        self.nodes.clear()
        self.edges.clear()
        self._adjacency.clear()
        self._reverse_adjacency.clear()
        self._edge_types.clear()

    def build_from_project(self, project_path: Path):
        """
        Build complete graph from project files.

        Args:
            project_path: Path to project directory
        """
        self.clear()
        project_path = Path(project_path)

        # 1. Load journal.json -> RequirementNodes
        journal_path = project_path / "journal.json"
        if journal_path.exists():
            self._load_journal(journal_path)

        # 2. Load user_stories.md -> Epics, UserStories
        user_stories_path = project_path / "user_stories" / "user_stories.md"
        if user_stories_path.exists():
            self._load_user_stories(user_stories_path)

        # 3. Load task_list.json -> Tasks with dependencies
        tasks_path = project_path / "tasks" / "task_list.json"
        if tasks_path.exists():
            self._load_tasks(tasks_path)

        # 4. Load diagrams
        diagrams_path = project_path / "diagrams"
        if diagrams_path.exists():
            self._load_diagrams(diagrams_path)

        # 5. Load additional artifacts from JSON files
        self._load_additional_artifacts(project_path)

        # 6. Load discovered links (auto-linked by user approval)
        self._load_discovered_links(project_path)

    def _load_journal(self, journal_path: Path):
        """Load RequirementNodes from journal.json."""
        try:
            with open(journal_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[LinkGraph] Failed to load journal: {e}")
            return

        nodes_data = data.get("nodes", {})
        if isinstance(nodes_data, dict):
            for node_id, node_data in nodes_data.items():
                self._add_requirement_node(node_id, node_data)

    def _add_requirement_node(self, node_id: str, node_data: dict):
        """Add a requirement node and its edges."""
        # Store node
        self.nodes[node_id] = node_data

        # Also index by requirement_id if available
        req_id = node_data.get("requirement_id", "")
        if req_id and req_id != node_id:
            self.nodes[req_id] = node_data

        # Extract edges from node data
        # Parent relationship
        parent = node_data.get("parent_requirement")
        if parent:
            self._add_edge(node_id, parent, "parent")

        # Dependencies
        for dep in node_data.get("dependencies", []):
            self._add_edge(node_id, dep, "dependency")

        # Conflicts
        for conflict in node_data.get("conflicts", []):
            self._add_edge(node_id, conflict, "conflict")

        # Related requirements
        for related in node_data.get("related_requirements", []):
            self._add_edge(node_id, related, "related")

    def _load_user_stories(self, user_stories_path: Path):
        """Load Epics and UserStories from user_stories.md."""
        try:
            with open(user_stories_path, "r", encoding="utf-8") as f:
                content = f.read()
        except IOError as e:
            print(f"[LinkGraph] Failed to load user stories: {e}")
            return

        # Parse Epics
        epic_pattern = r'## (EPIC-\d+):\s*([^\n]+)'
        linked_reqs_pattern = r'\*\*Verknüpfte Requirements:\*\*\s*\[([^\]]+)\]'
        linked_stories_pattern = r'\*\*User Stories:\*\*\s*\[([^\]]+)\]'

        current_epic = None
        for line in content.split('\n'):
            epic_match = re.match(epic_pattern, line)
            if epic_match:
                current_epic = epic_match.group(1)
                title = epic_match.group(2)

                # Add epic node
                if current_epic not in self.nodes:
                    self.nodes[current_epic] = {
                        "id": current_epic,
                        "title": title,
                        "type": "epic"
                    }

            elif current_epic:
                # Check for linked requirements
                req_match = re.search(linked_reqs_pattern, line)
                if req_match:
                    reqs = [r.strip() for r in req_match.group(1).split(',')]
                    for req in reqs:
                        if req:
                            self._add_edge(current_epic, req, "epic_requirement")

                # Check for linked user stories
                story_match = re.search(linked_stories_pattern, line)
                if story_match:
                    stories = [s.strip() for s in story_match.group(1).split(',')]
                    for story in stories:
                        if story:
                            self._add_edge(current_epic, story, "epic_story")

        # Parse individual User Stories
        us_pattern = r'### (US-\d+):\s*([^\n]+)'
        parent_req_pattern = r'\*\*Parent Requirement:\*\*\s*(\S+)'

        current_us = None
        for line in content.split('\n'):
            us_match = re.match(us_pattern, line)
            if us_match:
                current_us = us_match.group(1)
                title = us_match.group(2)

                if current_us not in self.nodes:
                    self.nodes[current_us] = {
                        "id": current_us,
                        "title": title,
                        "type": "user_story"
                    }

            elif current_us:
                parent_match = re.search(parent_req_pattern, line)
                if parent_match:
                    parent_req = parent_match.group(1)
                    self._add_edge(current_us, parent_req, "story_requirement")

    def _load_tasks(self, tasks_path: Path):
        """Load Tasks from task_list.json."""
        try:
            with open(tasks_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[LinkGraph] Failed to load tasks: {e}")
            return

        # Load tasks
        tasks = data.get("tasks", [])
        for task in tasks:
            task_id = task.get("id", "")
            if not task_id:
                continue

            self.nodes[task_id] = {
                "id": task_id,
                "title": task.get("title", ""),
                "type": "task",
                "data": task
            }

            # Parent relationships
            parent_feature = task.get("parent_feature_id", "")
            if parent_feature:
                self._add_edge(task_id, parent_feature, "task_feature")

            parent_story = task.get("parent_user_story_id", "")
            if parent_story:
                self._add_edge(task_id, parent_story, "task_story")

            parent_req = task.get("parent_requirement_id", "")
            if parent_req:
                self._add_edge(task_id, parent_req, "task_requirement")

            # Dependencies
            for dep in task.get("depends_on", []):
                self._add_edge(task_id, dep, "task_dependency")

            # Blocks
            for blocked in task.get("blocks", []):
                self._add_edge(task_id, blocked, "task_blocks")

        # Load dependency graph if present
        dep_graph = data.get("dependency_graph", {})
        for task_id, deps in dep_graph.items():
            for dep in deps:
                self._add_edge(task_id, dep, "task_dependency")

    def _load_diagrams(self, diagrams_path: Path):
        """Load diagram files and link them to nodes."""
        for diagram_file in diagrams_path.glob("*.mmd"):
            # Extract node ID from filename (e.g., REQ-001_flowchart.mmd)
            stem = diagram_file.stem
            parts = stem.split("_")
            if parts:
                node_id = parts[0]
                diagram_type = parts[1] if len(parts) > 1 else "diagram"

                diagram_id = f"diagram_{stem}"
                self.nodes[diagram_id] = {
                    "id": diagram_id,
                    "title": f"{node_id} {diagram_type}",
                    "type": "diagram",
                    "file": str(diagram_file)
                }

                # Link diagram to its parent node
                if node_id in self.nodes:
                    self._add_edge(diagram_id, node_id, "diagram_of")

    def _add_edge(self, source: str, target: str, edge_type: str):
        """Add an edge to the graph."""
        edge = Edge(source=source, target=target, edge_type=edge_type)

        # Avoid duplicates
        if edge not in self.edges:
            self.edges.append(edge)
            self._adjacency[source].add(target)
            self._reverse_adjacency[target].add(source)
            self._edge_types[(source, target)] = edge_type

    def get_linked_nodes(self, node_id: str, depth: int = 1, include_types: Optional[List[str]] = None) -> List[str]:
        """
        Get all nodes linked to the given node up to depth.

        Args:
            node_id: Starting node ID
            depth: Maximum traversal depth (1 = direct links only)
            include_types: If provided, only include these edge types

        Returns:
            List of linked node IDs
        """
        visited = set()
        result = []
        queue = [(node_id, 0)]

        while queue:
            current, d = queue.pop(0)

            if current in visited:
                continue

            visited.add(current)

            if current != node_id:
                result.append(current)

            if d >= depth:
                continue

            # Get outgoing edges
            for target in self._adjacency.get(current, set()):
                if include_types:
                    edge_type = self._edge_types.get((current, target), "")
                    if edge_type not in include_types:
                        continue
                if target not in visited:
                    queue.append((target, d + 1))

            # Get incoming edges (reverse direction)
            for source in self._reverse_adjacency.get(current, set()):
                if include_types:
                    edge_type = self._edge_types.get((source, current), "")
                    if edge_type not in include_types:
                        continue
                if source not in visited:
                    queue.append((source, d + 1))

        return result

    def get_link_type(self, source: str, target: str) -> Optional[str]:
        """Get the edge type between two nodes."""
        # Check both directions
        edge_type = self._edge_types.get((source, target))
        if edge_type:
            return edge_type

        edge_type = self._edge_types.get((target, source))
        if edge_type:
            return f"reverse_{edge_type}"

        return None

    def get_orphan_nodes(self) -> List[str]:
        """
        Find nodes with no incoming or outgoing edges.

        Returns:
            List of orphan node IDs
        """
        connected = set()

        for edge in self.edges:
            connected.add(edge.source)
            connected.add(edge.target)

        orphans = [
            node_id for node_id in self.nodes
            if node_id not in connected
        ]

        return orphans

    def get_nodes_by_type(self, node_type: str) -> List[str]:
        """Get all nodes of a specific type."""
        return [
            node_id for node_id, data in self.nodes.items()
            if data.get("type") == node_type
        ]

    def get_node(self, node_id: str) -> Optional[dict]:
        """Get node data by ID."""
        return self.nodes.get(node_id)

    def update_node(self, node_id: str, new_data: dict, new_links: Optional[Dict[str, List[str]]] = None):
        """
        Update a node and optionally its edges.

        Args:
            node_id: Node ID to update
            new_data: New node data
            new_links: Optional dict of link_type -> [target_ids]
        """
        # Update node data
        if node_id in self.nodes:
            self.nodes[node_id].update(new_data)
        else:
            self.nodes[node_id] = new_data

        # Update edges if provided
        if new_links:
            # Remove existing edges from this node
            self.edges = [e for e in self.edges if e.source != node_id]
            if node_id in self._adjacency:
                for target in self._adjacency[node_id]:
                    self._edge_types.pop((node_id, target), None)
                self._adjacency[node_id].clear()

            # Add new edges
            for edge_type, targets in new_links.items():
                for target in targets:
                    self._add_edge(node_id, target, edge_type)

    def get_statistics(self) -> Dict[str, Any]:
        """Get graph statistics."""
        type_counts = defaultdict(int)
        for node_data in self.nodes.values():
            type_counts[node_data.get("type", "unknown")] += 1

        edge_type_counts = defaultdict(int)
        for edge in self.edges:
            edge_type_counts[edge.edge_type] += 1

        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "orphan_count": len(self.get_orphan_nodes()),
            "nodes_by_type": dict(type_counts),
            "edges_by_type": dict(edge_type_counts),
        }

    def _load_additional_artifacts(self, project_path: Path):
        """Load additional artifact types from JSON files."""
        # Load from ux_design/ux_spec.json (personas, user_flows, screens)
        ux_spec_path = project_path / "ux_design" / "ux_spec.json"
        if ux_spec_path.exists():
            self._load_ux_spec(ux_spec_path)

        # Load from ui_design/ui_spec.json (components)
        ui_spec_path = project_path / "ui_design" / "ui_spec.json"
        if ui_spec_path.exists():
            self._load_ui_spec(ui_spec_path)

        # Load tech stack from subfolder
        tech_stack_path = project_path / "tech_stack" / "tech_stack.json"
        if tech_stack_path.exists():
            self._load_tech_stack(tech_stack_path)

        # Fallback: Load from root level (legacy format)
        personas_path = project_path / "personas.json"
        if personas_path.exists():
            self._load_json_artifacts(personas_path, "persona", "PERSONA")

        user_flows_path = project_path / "user_flows.json"
        if user_flows_path.exists():
            self._load_json_artifacts(user_flows_path, "user-flow", "FLOW")

        screens_path = project_path / "screens.json"
        if screens_path.exists():
            self._load_json_artifacts(screens_path, "screen", "SCREEN")

        components_path = project_path / "ui_components.json"
        if components_path.exists():
            self._load_json_artifacts(components_path, "component", "COMP")

        api_path = project_path / "api_endpoints.json"
        if api_path.exists():
            self._load_json_artifacts(api_path, "api", "API")

        data_dict_path = project_path / "data_dictionary.json"
        if data_dict_path.exists():
            self._load_data_dictionary(data_dict_path)

        features_path = project_path / "work_breakdown.json"
        if features_path.exists():
            self._load_work_breakdown(features_path)

        # Fallback tech stack at root
        tech_stack_root = project_path / "tech_stack.json"
        if tech_stack_root.exists():
            self._load_tech_stack(tech_stack_root)

        print(f"[LinkGraph] Loaded {len(self.nodes)} nodes, {len(self.edges)} edges")

    def _load_ux_spec(self, file_path: Path):
        """Load UX spec containing personas, user_flows, screens."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[LinkGraph] Failed to load UX spec: {e}")
            return

        # Load personas
        for persona in data.get("personas", []):
            if not isinstance(persona, dict):
                continue
            node_id = persona.get("id") or f"PERSONA-{len(self.nodes)}"
            self.nodes[node_id] = {
                "id": node_id,
                "title": persona.get("name") or persona.get("role", node_id),
                "type": "persona",
                "description": persona.get("quote", ""),
                "data": persona
            }

        # Load user flows
        for flow in data.get("user_flows", []):
            if not isinstance(flow, dict):
                continue
            node_id = flow.get("id") or f"FLOW-{len(self.nodes)}"
            self.nodes[node_id] = {
                "id": node_id,
                "title": flow.get("name") or flow.get("title", node_id),
                "type": "user-flow",
                "description": flow.get("description", ""),
                "data": flow
            }
            # Link to persona
            persona_id = flow.get("persona_id")
            if persona_id:
                self._add_edge(node_id, persona_id, "flow_persona")
            # Link to screens in steps
            for step in flow.get("steps", []):
                screen_id = step.get("screen_id") if isinstance(step, dict) else None
                if screen_id:
                    self._add_edge(node_id, screen_id, "flow_screen")

        # Load screens
        for screen in data.get("screens", []):
            if not isinstance(screen, dict):
                continue
            node_id = screen.get("id") or f"SCREEN-{len(self.nodes)}"
            self.nodes[node_id] = {
                "id": node_id,
                "title": screen.get("name") or screen.get("title", node_id),
                "type": "screen",
                "description": screen.get("description", ""),
                "data": screen
            }
            # Link to user story
            story_id = screen.get("user_story_id") or screen.get("parent_user_story")
            if story_id:
                self._add_edge(node_id, story_id, "screen_story")

        # Load information architecture
        for ia in data.get("information_architecture", []):
            if not isinstance(ia, dict):
                continue
            node_id = ia.get("id") or f"IA-{len(self.nodes)}"
            self.nodes[node_id] = {
                "id": node_id,
                "title": ia.get("name", node_id),
                "type": "screen",
                "description": ia.get("path", ""),
                "data": ia
            }

        print(f"[LinkGraph] Loaded UX spec: {len(data.get('personas', []))} personas, {len(data.get('user_flows', []))} flows, {len(data.get('screens', []))} screens")

    def _load_ui_spec(self, file_path: Path):
        """Load UI spec containing components."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[LinkGraph] Failed to load UI spec: {e}")
            return

        # Load components
        for comp in data.get("components", []):
            if not isinstance(comp, dict):
                continue
            node_id = comp.get("id") or f"COMP-{len(self.nodes)}"
            self.nodes[node_id] = {
                "id": node_id,
                "title": comp.get("name") or comp.get("title", node_id),
                "type": "component",
                "description": comp.get("description", ""),
                "data": comp
            }

        print(f"[LinkGraph] Loaded UI spec: {len(data.get('components', []))} components")

    def _load_json_artifacts(self, file_path: Path, node_type: str, id_prefix: str):
        """Load artifacts from a JSON array file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[LinkGraph] Failed to load {file_path}: {e}")
            return

        # Handle both array and object formats
        items = data if isinstance(data, list) else data.get("items", data.get("personas", data.get("flows", data.get("screens", data.get("components", data.get("endpoints", []))))))

        if not isinstance(items, list):
            items = [items] if items else []

        for item in items:
            if not isinstance(item, dict):
                continue

            node_id = item.get("id") or f"{id_prefix}-{len(self.nodes)}"
            title = item.get("name") or item.get("title") or item.get("role") or node_id

            self.nodes[node_id] = {
                "id": node_id,
                "title": title,
                "type": node_type,
                "description": item.get("description", ""),
                "data": item
            }

            # Extract links based on item fields
            self._extract_artifact_links(node_id, item, node_type)

    def _extract_artifact_links(self, node_id: str, item: dict, node_type: str):
        """Extract links from artifact item fields."""
        # Common link fields
        if "parent_user_story" in item or "user_story_id" in item:
            story_id = item.get("parent_user_story") or item.get("user_story_id")
            if story_id:
                self._add_edge(node_id, story_id, f"{node_type}_story")

        if "parent_epic" in item or "epic_id" in item:
            epic_id = item.get("parent_epic") or item.get("epic_id")
            if epic_id:
                self._add_edge(node_id, epic_id, f"{node_type}_epic")

        if "requirement_id" in item or "parent_requirement" in item:
            req_id = item.get("requirement_id") or item.get("parent_requirement")
            if req_id:
                self._add_edge(node_id, req_id, f"{node_type}_requirement")

        if "feature_id" in item or "parent_feature" in item:
            feature_id = item.get("feature_id") or item.get("parent_feature")
            if feature_id:
                self._add_edge(node_id, feature_id, f"{node_type}_feature")

        # Screen-specific links
        if "components" in item and isinstance(item["components"], list):
            for comp in item["components"]:
                comp_id = comp if isinstance(comp, str) else comp.get("id")
                if comp_id:
                    self._add_edge(node_id, comp_id, "screen_component")

        # User flow steps
        if "steps" in item and isinstance(item["steps"], list):
            for step in item["steps"]:
                screen_id = step.get("screen_id") if isinstance(step, dict) else None
                if screen_id:
                    self._add_edge(node_id, screen_id, "flow_screen")

    def _load_data_dictionary(self, file_path: Path):
        """Load data dictionary entities."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[LinkGraph] Failed to load data dictionary: {e}")
            return

        entities = data.get("entities", [])
        for entity in entities:
            if not isinstance(entity, dict):
                continue

            node_id = entity.get("id") or f"ENTITY-{len(self.nodes)}"
            self.nodes[node_id] = {
                "id": node_id,
                "title": entity.get("name", node_id),
                "type": "entity",
                "description": entity.get("description", ""),
                "data": entity
            }

    def _load_work_breakdown(self, file_path: Path):
        """Load features from work breakdown."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[LinkGraph] Failed to load work breakdown: {e}")
            return

        features = data.get("features", [])
        for feature in features:
            if not isinstance(feature, dict):
                continue

            node_id = feature.get("id") or f"FEAT-{len(self.nodes)}"
            self.nodes[node_id] = {
                "id": node_id,
                "title": feature.get("name") or feature.get("title", node_id),
                "type": "feature",
                "description": feature.get("description", ""),
                "data": feature
            }

            # Link to user stories
            for story_id in feature.get("user_stories", []):
                self._add_edge(node_id, story_id, "feature_story")

            # Link to requirements
            for req_id in feature.get("requirements", []):
                self._add_edge(node_id, req_id, "feature_requirement")

    def _load_tech_stack(self, file_path: Path):
        """Load tech stack."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[LinkGraph] Failed to load tech stack: {e}")
            return

        # Tech stack is usually a single object
        node_id = "TECH-STACK"
        self.nodes[node_id] = {
            "id": node_id,
            "title": "Tech Stack",
            "type": "tech-stack",
            "data": data
        }

    def _load_discovered_links(self, project_path: Path):
        """Load links from discovered_links.json (auto-linked by user approval)."""
        links_file = project_path / "discovered_links.json"
        if not links_file.exists():
            return

        try:
            with open(links_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            count = 0
            for link in data.get("links", []):
                source_id = link.get("source_id")
                target_id = link.get("target_id")
                link_type = link.get("link_type", "discovered")

                if source_id and target_id:
                    self._add_edge(source_id, target_id, link_type)
                    count += 1

            print(f"[LinkGraph] Loaded {count} discovered links from {links_file.name}")

        except (json.JSONDecodeError, IOError) as e:
            print(f"[LinkGraph] Failed to load discovered links: {e}")

    def to_json(self) -> str:
        """Serialize graph to JSON."""
        return json.dumps({
            "nodes": self.nodes,
            "edges": [e.to_dict() for e in self.edges]
        }, indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "LinkGraph":
        """Deserialize graph from JSON."""
        data = json.loads(json_str)
        graph = cls()
        graph.nodes = data.get("nodes", {})

        for edge_data in data.get("edges", []):
            graph._add_edge(
                edge_data["source"],
                edge_data["target"],
                edge_data["edge_type"]
            )

        return graph
