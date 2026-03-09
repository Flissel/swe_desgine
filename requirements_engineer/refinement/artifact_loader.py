"""
Artifact Loader — loads all RE pipeline output artifacts from any output directory.

Strategy:
  1. Primary: _checkpoints/stage_N.json (structured JSON, most reliable)
  2. Fallback: Standalone JSON files (epics.json, openapi_spec.json, etc.)
  3. Last resort: Markdown parsing or glob-based discovery

Missing files are recorded as LoadStatus.MISSING — no exceptions raised.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import ArtifactBundle, FileLoadResult, LoadStatus

logger = logging.getLogger(__name__)


class ArtifactLoader:
    """Unified loader for all RE pipeline output artifacts."""

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        if not self.output_dir.exists():
            raise FileNotFoundError(f"Output directory does not exist: {output_dir}")

    def load_all(self) -> ArtifactBundle:
        """Load all artifacts from the output directory into an ArtifactBundle."""
        bundle = ArtifactBundle(output_dir=self.output_dir)

        self._load_requirements(bundle)
        self._load_user_stories(bundle)
        self._load_epics(bundle)
        self._load_api_endpoints(bundle)
        self._load_data_dictionary(bundle)
        self._load_test_cases(bundle)
        self._load_tech_stack(bundle)
        self._load_arch_spec(bundle)
        self._load_ux_design(bundle)
        self._load_ui_design(bundle)
        self._load_screen_compositions(bundle)
        self._load_tasks(bundle)
        self._load_state_machines(bundle)
        self._load_diagrams(bundle)

        self._build_indices(bundle)
        return bundle

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _record(self, bundle: ArtifactBundle, path: str, status: LoadStatus,
                count: int = 0, error: str = ""):
        bundle.file_results.append(FileLoadResult(
            path=path, status=status, item_count=count, error=error,
        ))

    def _load_json(self, relative_path: str) -> Optional[Any]:
        full_path = self.output_dir / relative_path
        if not full_path.exists():
            return None
        try:
            with open(full_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning("Failed to parse %s: %s", relative_path, e)
            return None

    def _load_text(self, relative_path: str) -> Optional[str]:
        full_path = self.output_dir / relative_path
        if not full_path.exists():
            return None
        try:
            return full_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to read %s: %s", relative_path, e)
            return None

    # ------------------------------------------------------------------
    # Individual loaders
    # ------------------------------------------------------------------

    def _load_requirements(self, bundle: ArtifactBundle):
        """Load requirements from journal.json or stage_3 checkpoint."""
        # Try journal.json first (has all RequirementNodes)
        data = self._load_json("journal.json")
        if data and "nodes" in data:
            try:
                from requirements_engineer.core.re_journal import RequirementNode
                nodes = data["nodes"]
                bundle.requirements = [
                    RequirementNode.from_dict(v) if isinstance(v, dict) else v
                    for v in nodes.values()
                ]
                self._record(bundle, "journal.json", LoadStatus.LOADED,
                             count=len(bundle.requirements))
                return
            except Exception as e:
                logger.warning("journal.json parse failed: %s", e)

        # Fallback: stage_3 checkpoint
        cp = self._load_json("_checkpoints/stage_3.json")
        if cp and "requirements" in cp:
            try:
                from requirements_engineer.core.re_journal import RequirementNode
                bundle.requirements = [
                    RequirementNode.from_dict(r) for r in cp["requirements"]
                ]
                self._record(bundle, "_checkpoints/stage_3.json", LoadStatus.LOADED,
                             count=len(bundle.requirements))
                return
            except Exception as e:
                self._record(bundle, "requirements", LoadStatus.PARSE_ERROR, error=str(e))
                return

        self._record(bundle, "journal.json", LoadStatus.MISSING)

    def _load_user_stories(self, bundle: ArtifactBundle):
        """Load user stories from user_stories.json or stage_4 checkpoint."""
        # Try stage_4 checkpoint first
        cp = self._load_json("_checkpoints/stage_4.json")
        if cp and "user_stories" in cp:
            try:
                from requirements_engineer.generators.user_story_generator import UserStory
                bundle.user_stories = [
                    UserStory.from_dict(s) for s in cp["user_stories"]
                ]
                self._record(bundle, "_checkpoints/stage_4.json[user_stories]",
                             LoadStatus.LOADED, count=len(bundle.user_stories))
                return
            except Exception as e:
                logger.warning("stage_4 user_stories parse failed: %s", e)

        # Fallback: user_stories.json
        data = self._load_json("user_stories.json")
        if data:
            try:
                from requirements_engineer.generators.user_story_generator import UserStory
                stories = data.get("user_stories", data if isinstance(data, list) else [])
                bundle.user_stories = [UserStory.from_dict(s) for s in stories]
                self._record(bundle, "user_stories.json", LoadStatus.LOADED,
                             count=len(bundle.user_stories))
                return
            except Exception as e:
                self._record(bundle, "user_stories.json", LoadStatus.PARSE_ERROR, error=str(e))
                return

        self._record(bundle, "user_stories", LoadStatus.MISSING)

    def _load_epics(self, bundle: ArtifactBundle):
        """Load epics from epics.json or stage_4 checkpoint."""
        # Try dedicated epics file
        data = self._load_json("user_stories/epics/epics.json")
        if data:
            try:
                from requirements_engineer.generators.user_story_generator import Epic
                items = data if isinstance(data, list) else data.get("epics", [])
                bundle.epics = [Epic.from_dict(e) for e in items]
                self._record(bundle, "user_stories/epics/epics.json",
                             LoadStatus.LOADED, count=len(bundle.epics))
                return
            except Exception as e:
                logger.warning("epics.json parse failed: %s", e)

        # Fallback: stage_4 checkpoint
        cp = self._load_json("_checkpoints/stage_4.json")
        if cp and "epics" in cp:
            try:
                from requirements_engineer.generators.user_story_generator import Epic
                bundle.epics = [Epic.from_dict(e) for e in cp["epics"]]
                self._record(bundle, "_checkpoints/stage_4.json[epics]",
                             LoadStatus.LOADED, count=len(bundle.epics))
                return
            except Exception as e:
                logger.warning("stage_4 epics parse failed: %s", e)

        # Fallback: user_stories.json may contain epics
        data = self._load_json("user_stories.json")
        if data and "epics" in data:
            try:
                from requirements_engineer.generators.user_story_generator import Epic
                bundle.epics = [Epic.from_dict(e) for e in data["epics"]]
                self._record(bundle, "user_stories.json[epics]",
                             LoadStatus.LOADED, count=len(bundle.epics))
                return
            except Exception as e:
                pass

        self._record(bundle, "epics", LoadStatus.MISSING)

    def _load_api_endpoints(self, bundle: ArtifactBundle):
        """Load API endpoints from stage_5 checkpoint or openapi_spec."""
        # Checkpoint (has structured APIEndpoint dicts)
        cp = self._load_json("_checkpoints/stage_5.json")
        if cp and "api_endpoints" in cp:
            try:
                from requirements_engineer.generators.api_spec_generator import APIEndpoint
                bundle.api_endpoints = [
                    APIEndpoint.from_dict(ep) for ep in cp["api_endpoints"]
                ]
                self._record(bundle, "_checkpoints/stage_5.json",
                             LoadStatus.LOADED, count=len(bundle.api_endpoints))
                return
            except Exception as e:
                logger.warning("stage_5 API parse failed: %s", e)

        # Fallback: parse OpenAPI spec JSON
        spec = self._load_json("api/openapi_spec.json")
        if spec and "paths" in spec:
            try:
                from requirements_engineer.generators.api_spec_generator import APIEndpoint
                endpoints = []
                for route, methods in spec["paths"].items():
                    for method, details in methods.items():
                        if method.lower() in ("get", "post", "put", "delete", "patch"):
                            endpoints.append(APIEndpoint(
                                path=route,
                                method=method.upper(),
                                summary=details.get("summary", ""),
                                description=details.get("description", ""),
                                operation_id=details.get("operationId", ""),
                                tags=details.get("tags", []),
                            ))
                bundle.api_endpoints = endpoints
                self._record(bundle, "api/openapi_spec.json",
                             LoadStatus.LOADED, count=len(endpoints))
                return
            except Exception as e:
                self._record(bundle, "api/openapi_spec.json",
                             LoadStatus.PARSE_ERROR, error=str(e))
                return

        self._record(bundle, "api_endpoints", LoadStatus.MISSING)

    def _load_data_dictionary(self, bundle: ArtifactBundle):
        """Load entities and relationships from stage_6 checkpoint or JSON."""
        cp = self._load_json("_checkpoints/stage_6.json")
        if cp:
            try:
                from requirements_engineer.generators.data_dictionary_generator import (
                    Entity, Relationship,
                )
                entities = [Entity.from_dict(e) for e in cp.get("entities", [])]
                bundle.entities = {e.name: e for e in entities}
                bundle.relationships = [
                    Relationship.from_dict(r) for r in cp.get("relationships", [])
                ]
                total = len(bundle.entities) + len(bundle.relationships)
                self._record(bundle, "_checkpoints/stage_6.json",
                             LoadStatus.LOADED, count=total)
                return
            except Exception as e:
                logger.warning("stage_6 data dict parse failed: %s", e)

        # Fallback: data_dictionary.json
        data = self._load_json("data/data_dictionary.json")
        if data:
            try:
                from requirements_engineer.generators.data_dictionary_generator import (
                    Entity, Relationship,
                )
                entities = [Entity.from_dict(e) for e in data.get("entities", [])]
                bundle.entities = {e.name: e for e in entities}
                bundle.relationships = [
                    Relationship.from_dict(r) for r in data.get("relationships", [])
                ]
                total = len(bundle.entities) + len(bundle.relationships)
                self._record(bundle, "data/data_dictionary.json",
                             LoadStatus.LOADED, count=total)
                return
            except Exception as e:
                self._record(bundle, "data/data_dictionary.json",
                             LoadStatus.PARSE_ERROR, error=str(e))
                return

        self._record(bundle, "data_dictionary", LoadStatus.MISSING)

    def _load_test_cases(self, bundle: ArtifactBundle):
        """Load test cases from stage_8 checkpoint."""
        cp = self._load_json("_checkpoints/stage_8.json")
        if cp and "test_cases" in cp:
            try:
                from requirements_engineer.generators.test_case_generator import TestCase
                bundle.test_cases = [
                    TestCase.from_dict(tc) for tc in cp["test_cases"]
                ]
                self._record(bundle, "_checkpoints/stage_8.json",
                             LoadStatus.LOADED, count=len(bundle.test_cases))
                return
            except Exception as e:
                logger.warning("stage_8 test cases parse failed: %s", e)

        # Fallback: check if test_documentation.md exists
        path = "testing/test_documentation.md"
        if (self.output_dir / path).exists():
            self._record(bundle, path, LoadStatus.LOADED, count=0)
        else:
            self._record(bundle, "test_cases", LoadStatus.MISSING)

    def _load_tech_stack(self, bundle: ArtifactBundle):
        """Load tech stack from stage_7 checkpoint."""
        cp = self._load_json("_checkpoints/stage_7.json")
        if cp and "tech_stack" in cp:
            try:
                from requirements_engineer.generators.tech_stack_generator import TechStack
                bundle.tech_stack = TechStack.from_dict(cp["tech_stack"])
                self._record(bundle, "_checkpoints/stage_7.json",
                             LoadStatus.LOADED, count=1)
                return
            except Exception as e:
                logger.warning("stage_7 tech stack parse failed: %s", e)

        self._record(bundle, "tech_stack", LoadStatus.MISSING)

    def _load_arch_spec(self, bundle: ArtifactBundle):
        """Load architecture spec from stage_7.5 checkpoint."""
        cp = self._load_json("_checkpoints/stage_7.5.json")
        if cp and "arch_spec" in cp:
            try:
                from requirements_engineer.generators.architecture_generator import ArchitectureSpec
                bundle.arch_spec = ArchitectureSpec.from_dict(cp["arch_spec"])
                self._record(bundle, "_checkpoints/stage_7.5.json",
                             LoadStatus.LOADED, count=1)
                return
            except Exception as e:
                logger.warning("stage_7.5 arch spec parse failed: %s", e)

        # Check for markdown fallback
        path = "architecture/architecture_overview.md"
        if (self.output_dir / path).exists():
            self._record(bundle, path, LoadStatus.LOADED, count=1)
        else:
            self._record(bundle, "architecture", LoadStatus.MISSING)

    def _load_ux_design(self, bundle: ArtifactBundle):
        """Load UX design (personas, user flows) from stage_9 or JSON."""
        cp = self._load_json("_checkpoints/stage_9.json")
        if cp and "ux_spec" in cp:
            try:
                from requirements_engineer.generators.ux_design_generator import (
                    UXDesignSpec,
                )
                bundle.ux_spec = UXDesignSpec.from_dict(cp["ux_spec"])
                bundle.personas = list(bundle.ux_spec.personas)
                bundle.user_flows = list(bundle.ux_spec.user_flows)
                self._record(bundle, "_checkpoints/stage_9.json",
                             LoadStatus.LOADED,
                             count=len(bundle.personas) + len(bundle.user_flows))
                return
            except Exception as e:
                logger.warning("stage_9 UX parse failed: %s", e)

        # Fallback: ux_spec.json
        data = self._load_json("ux_design/ux_spec.json")
        if data:
            try:
                from requirements_engineer.generators.ux_design_generator import UXDesignSpec
                bundle.ux_spec = UXDesignSpec.from_dict(data)
                bundle.personas = list(bundle.ux_spec.personas)
                bundle.user_flows = list(bundle.ux_spec.user_flows)
                self._record(bundle, "ux_design/ux_spec.json",
                             LoadStatus.LOADED,
                             count=len(bundle.personas) + len(bundle.user_flows))
                return
            except Exception as e:
                pass

        self._record(bundle, "ux_design", LoadStatus.MISSING)

    def _load_ui_design(self, bundle: ArtifactBundle):
        """Load UI screens from ui_design/screens/*.json or ui_spec.json."""
        screens_dir = self.output_dir / "ui_design" / "screens"
        if screens_dir.exists():
            try:
                from requirements_engineer.generators.ui_design_generator import Screen
                for jf in sorted(screens_dir.glob("*.json")):
                    data = self._load_json(f"ui_design/screens/{jf.name}")
                    if data:
                        bundle.screens.append(Screen.from_dict(data))
            except Exception as e:
                logger.warning("Screen loading failed: %s", e)

        # Also try ui_spec.json for screens
        if not bundle.screens:
            data = self._load_json("ui_design/ui_spec.json")
            if data:
                try:
                    from requirements_engineer.generators.ui_design_generator import (
                        UIDesignSpec, Screen,
                    )
                    bundle.ui_spec = UIDesignSpec.from_dict(data)
                    bundle.screens = list(bundle.ui_spec.screens)
                except Exception:
                    pass

        if bundle.screens:
            self._record(bundle, "ui_design/screens/", LoadStatus.LOADED,
                         count=len(bundle.screens))
        else:
            self._record(bundle, "ui_design/screens/", LoadStatus.MISSING)

    def _load_screen_compositions(self, bundle: ArtifactBundle):
        """Load component compositions from ui_design/compositions/*.json."""
        comp_dir = self.output_dir / "ui_design" / "compositions"
        if not comp_dir.exists():
            return

        skip_files = {"component_matrix.json", "index.json"}
        for jf in sorted(comp_dir.glob("*.json")):
            if jf.name in skip_files:
                continue
            data = self._load_json(f"ui_design/compositions/{jf.name}")
            if data:
                bundle.screen_compositions.append(data)

    def _load_tasks(self, bundle: ArtifactBundle):
        """Load tasks from tasks/task_list.json."""
        data = self._load_json("tasks/task_list.json")
        if data:
            try:
                from requirements_engineer.generators.task_generator import (
                    Task, TaskBreakdown,
                )
                if isinstance(data, dict) and "features" in data:
                    bundle.task_breakdown = TaskBreakdown.from_dict(data)
                    bundle.tasks = bundle.task_breakdown.tasks
                elif isinstance(data, list):
                    bundle.tasks = [Task.from_dict(t) for t in data]
                self._record(bundle, "tasks/task_list.json", LoadStatus.LOADED,
                             count=len(bundle.tasks))
                return
            except Exception as e:
                self._record(bundle, "tasks/task_list.json",
                             LoadStatus.PARSE_ERROR, error=str(e))
                return

        self._record(bundle, "tasks", LoadStatus.MISSING)

    def _load_state_machines(self, bundle: ArtifactBundle):
        """Load state machines from state_machines/state_machines.json or individual files."""
        # Try consolidated file first
        data = self._load_json("state_machines/state_machines.json")
        if data:
            try:
                from requirements_engineer.generators.state_machine_generator import StateMachine
                items = data if isinstance(data, list) else data.get("state_machines", [])
                bundle.state_machines = [StateMachine.from_dict(sm) for sm in items]
                self._record(bundle, "state_machines/state_machines.json",
                             LoadStatus.LOADED, count=len(bundle.state_machines))
                return
            except Exception as e:
                logger.warning("state_machines.json parse failed: %s", e)

        # Fallback: individual JSON files in state_machines/
        sm_dir = self.output_dir / "state_machines"
        if sm_dir.exists():
            try:
                from requirements_engineer.generators.state_machine_generator import StateMachine
                for jf in sorted(sm_dir.glob("*.json")):
                    if jf.name == "state_machines.json":
                        continue
                    sm_data = self._load_json(f"state_machines/{jf.name}")
                    if sm_data:
                        bundle.state_machines.append(StateMachine.from_dict(sm_data))
            except Exception:
                pass

        if bundle.state_machines:
            self._record(bundle, "state_machines/", LoadStatus.LOADED,
                         count=len(bundle.state_machines))
        else:
            self._record(bundle, "state_machines/", LoadStatus.MISSING)

    def _load_diagrams(self, bundle: ArtifactBundle):
        """Load .mmd diagram files from diagrams/ and other directories."""
        for search_dir in ["diagrams", "architecture", "state_machines"]:
            dir_path = self.output_dir / search_dir
            if not dir_path.exists():
                continue
            for mmd_file in sorted(dir_path.glob("*.mmd")):
                try:
                    content = mmd_file.read_text(encoding="utf-8")
                    bundle.diagrams[f"{search_dir}/{mmd_file.name}"] = content
                except Exception:
                    pass

        # Also check tasks/ for mermaid diagrams
        tasks_dir = self.output_dir / "tasks"
        if tasks_dir.exists():
            for mmd_file in sorted(tasks_dir.glob("*.mmd")):
                try:
                    content = mmd_file.read_text(encoding="utf-8")
                    bundle.diagrams[f"tasks/{mmd_file.name}"] = content
                except Exception:
                    pass

        self._record(bundle, "diagrams/",
                     LoadStatus.LOADED if bundle.diagrams else LoadStatus.EMPTY,
                     count=len(bundle.diagrams))

    # ------------------------------------------------------------------
    # Index builder
    # ------------------------------------------------------------------

    def _build_indices(self, bundle: ArtifactBundle):
        """Build convenience lookup dictionaries from loaded artifacts."""
        for req in bundle.requirements:
            rid = getattr(req, "requirement_id", None) or getattr(req, "id", "")
            if rid:
                bundle.req_by_id[rid] = req

        for story in bundle.user_stories:
            sid = getattr(story, "id", "")
            if sid:
                bundle.story_by_id[sid] = story

        for epic in bundle.epics:
            eid = getattr(epic, "id", "")
            if eid:
                bundle.epic_by_id[eid] = epic

        for tc in bundle.test_cases:
            tid = getattr(tc, "id", "")
            if tid:
                bundle.test_by_id[tid] = tc

        for screen in bundle.screens:
            sid = getattr(screen, "id", "")
            if sid:
                bundle.screen_by_id[sid] = screen

        for task in bundle.tasks:
            tid = getattr(task, "id", "")
            if tid:
                bundle.task_by_id[tid] = task

        for ep in bundle.api_endpoints:
            key = f"{getattr(ep, 'method', 'GET')} {getattr(ep, 'path', '')}"
            bundle.endpoint_by_key[key] = ep
