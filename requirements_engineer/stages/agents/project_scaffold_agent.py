"""
Project Scaffold Agent for Multi-Agent Presentation System.

Generates a real project filesystem structure from epics, tech stack,
and other RE artifacts. Places planning docs into the structure.

Uses LLM to determine optimal directory layout based on:
- Epic decomposition
- Tech stack choices (architecture pattern, CI/CD, etc.)
- Work breakdown mode (per_feature, per_service, per_application)
"""

import json
import logging
import re
import shutil
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from .base_presentation_agent import (
    BasePresentationAgent,
    AgentRole,
    AgentCapability,
    PresentationContext,
    AgentResult,
)

log = logging.getLogger(__name__)


SCAFFOLD_SYSTEM_PROMPT = """You are a Project Scaffold Architect. Given requirements engineering artifacts
(epics, tech stack, features, API specs), you generate an optimal project directory structure.

Rules:
- Map each epic to a concrete directory (service, feature module, or application)
- Include docs/ directory with planning artifacts organized by epic
- Generate appropriate config files based on tech stack (Dockerfile, CI, .gitignore)
- Keep directory depth <= 6 levels
- Use kebab-case for directory names
- Include README.md at each significant directory level

You MUST respond with valid JSON only, no markdown fences."""


SCAFFOLD_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "project_name": {"type": "string"},
        "structure_strategy": {
            "type": "string",
            "enum": ["feature_based", "service_based", "application_based", "layer_based"]
        },
        "strategy_rationale": {"type": "string"},
        "directories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "purpose": {"type": "string"},
                    "epic_id": {"type": "string"}
                },
                "required": ["path", "purpose"]
            }
        },
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content_type": {
                        "type": "string",
                        "enum": [
                            "readme", "dockerfile", "gitignore", "ci_config",
                            "docker_compose", "makefile", "adr", "placeholder",
                            "service_readme", "epic_readme", "project_overview"
                        ]
                    },
                    "content": {"type": "string"},
                    "epic_id": {"type": "string"}
                },
                "required": ["path", "content_type"]
            }
        },
        "doc_placement": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_pattern": {"type": "string"},
                    "target_dir": {"type": "string"},
                    "description": {"type": "string"}
                },
                "required": ["source_pattern", "target_dir"]
            }
        },
        "epic_mapping": {
            "type": "object",
            "additionalProperties": {"type": "string"}
        }
    },
    "required": ["project_name", "structure_strategy", "directories", "files", "doc_placement"]
}


def slugify(text: str) -> str:
    """Convert text to kebab-case slug safe for directory names."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')


class ProjectScaffoldAgent(BasePresentationAgent):
    """
    Agent that generates project filesystem structure from epics and artifacts.

    Takes epics, tech stack, feature breakdown, and API specs as input.
    Produces a real directory tree with:
    - Source code directory structure (empty, no code generation)
    - Planning docs organized by epic
    - Config file placeholders (Dockerfile, CI, .gitignore)
    - README.md files with context from RE artifacts
    - scaffold_manifest.json recording all decisions
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(
            name="ProjectScaffold",
            role=AgentRole.PROJECT_SCAFFOLD,
            description="Generates project directory structure from epics and tech stack",
            capabilities=[
                AgentCapability.SCAFFOLD_GENERATION,
                AgentCapability.ARTIFACT_PARSING,
                AgentCapability.FILE_PLACEMENT,
            ],
            config=config,
        )
        self.scaffold_config = config.get("scaffold", {}) if config else {}

    async def execute(self, context: PresentationContext) -> AgentResult:
        """
        Generate project scaffold from RE artifacts.

        Steps:
        1. Load artifacts (content_analysis, tech_stack, epics, features)
        2. Build LLM prompt with all context
        3. Call LLM to get directory structure plan
        4. Create directories and files on disk
        5. Place existing docs into structure
        6. Generate manifest
        """
        self._is_running = True
        self._current_context = context
        start_time = time.time()

        try:
            output_dir = Path(context.output_dir)
            scaffold_dir = output_dir / self.scaffold_config.get("output_dir", "project_scaffold")

            self._log_progress(f"Starting scaffold generation -> {scaffold_dir}")

            # 1. Load all artifacts
            artifacts = self._load_all_artifacts(output_dir)
            self._log_progress(f"Loaded artifacts: {list(artifacts.keys())}")

            # 2. Build LLM prompt
            prompt = self._build_scaffold_prompt(artifacts, context)

            # 3. Call LLM for structure plan
            self._log_progress("Calling LLM for scaffold plan...")
            plan = await self._get_scaffold_plan(prompt)

            if not plan:
                return AgentResult(
                    success=False,
                    error_message="LLM returned empty or invalid scaffold plan",
                    action_type="GENERATE_SCAFFOLD",
                    duration_seconds=time.time() - start_time,
                    should_replan=True,
                )

            self._log_progress(
                f"Scaffold plan: strategy={plan.get('structure_strategy')}, "
                f"{len(plan.get('directories', []))} dirs, "
                f"{len(plan.get('files', []))} files"
            )

            # 4. Create directories and files
            created_dirs, created_files = self._create_scaffold(scaffold_dir, plan)

            # 5. Place existing docs
            placed_docs = self._place_documents(
                source_dir=output_dir,
                scaffold_dir=scaffold_dir,
                placements=plan.get("doc_placement", []),
                artifacts=artifacts,
            )

            # 6. Generate manifest
            manifest = self._generate_manifest(plan, created_dirs, created_files, placed_docs)
            manifest_path = scaffold_dir / "scaffold_manifest.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)

            all_files = created_files + placed_docs + [str(manifest_path)]
            duration = time.time() - start_time

            self._log_progress(
                f"Scaffold complete: {len(created_dirs)} dirs, "
                f"{len(created_files)} files, {len(placed_docs)} docs placed "
                f"({duration:.1f}s)"
            )

            return AgentResult(
                success=True,
                generated_files=all_files,
                generated_content=json.dumps(manifest, indent=2),
                action_type="GENERATE_SCAFFOLD",
                duration_seconds=duration,
                notes=(
                    f"Generated scaffold with strategy '{plan.get('structure_strategy')}': "
                    f"{len(created_dirs)} directories, {len(created_files)} files, "
                    f"{len(placed_docs)} docs placed"
                ),
                recommendations=[
                    f"Strategy: {plan.get('structure_strategy')} - {plan.get('strategy_rationale', '')}",
                    f"Epic mapping: {plan.get('epic_mapping', {})}",
                ],
                suggested_next_agent="ScaffoldReviewer",
                confidence=0.8,
                needs_review=True,
            )

        except Exception as e:
            self._log_error(f"Scaffold generation failed: {e}")
            return AgentResult(
                success=False,
                error_message=str(e),
                action_type="GENERATE_SCAFFOLD",
                duration_seconds=time.time() - start_time,
                should_replan=True,
            )
        finally:
            self._is_running = False

    # ------------------------------------------------------------------
    # Artifact Loading
    # ------------------------------------------------------------------

    def _load_all_artifacts(self, output_dir: Path) -> Dict[str, Any]:
        """Load all relevant artifacts from the project output directory."""
        artifacts = {}

        # Content analysis (from Stage 5 Phase 1)
        artifacts["content_analysis"] = self._load_json(output_dir / "content_analysis.json")

        # Tech stack
        for name in ["tech_stack.json", "tech_stack/tech_stack.json"]:
            data = self._load_json(output_dir / name)
            if data:
                artifacts["tech_stack"] = data
                break

        # Epics
        for name in ["epics.json", "epics/epics.json"]:
            data = self._load_json(output_dir / name)
            if data:
                artifacts["epics"] = data
                break

        # Feature breakdown
        for name in ["feature_breakdown.json", "work_breakdown/feature_breakdown.json"]:
            data = self._load_json(output_dir / name)
            if data:
                artifacts["feature_breakdown"] = data
                break

        # User stories
        for name in ["user_stories.json", "user_stories/user_stories.json"]:
            data = self._load_json(output_dir / name)
            if data:
                artifacts["user_stories"] = data
                break

        # API spec
        for name in ["api_spec.json", "api/api_spec.json", "api/openapi_spec.yaml"]:
            data = self._load_json(output_dir / name)
            if data:
                artifacts["api_spec"] = data
                break

        # Task breakdown
        for name in ["tasks.json", "tasks/task_list.json"]:
            data = self._load_json(output_dir / name)
            if data:
                artifacts["tasks"] = data
                break

        # Requirements
        for name in ["requirements.json", "requirements.md"]:
            p = output_dir / name
            if p.exists():
                if p.suffix == ".json":
                    artifacts["requirements"] = self._load_json(p)
                else:
                    artifacts["requirements_md"] = p.read_text(encoding="utf-8")
                break

        # Diagrams list
        diagrams_dir = output_dir / "diagrams"
        if diagrams_dir.exists():
            artifacts["diagrams"] = [
                str(f.relative_to(output_dir)) for f in diagrams_dir.rglob("*.mmd")
            ]

        return {k: v for k, v in artifacts.items() if v}

    def _load_json(self, path: Path) -> Optional[Any]:
        """Load JSON file, return None on failure."""
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            log.warning(f"Failed to load {path}: {e}")
        return None

    # ------------------------------------------------------------------
    # Prompt Building
    # ------------------------------------------------------------------

    def _build_scaffold_prompt(self, artifacts: Dict[str, Any], context: PresentationContext) -> str:
        """Build the LLM prompt from loaded artifacts."""
        parts = []

        parts.append("Generate a project directory structure based on the following RE artifacts.\n")

        # Epics
        epics = artifacts.get("epics")
        if epics:
            epic_list = epics if isinstance(epics, list) else epics.get("epics", [])
            parts.append("## Epics")
            for epic in epic_list[:20]:
                if isinstance(epic, dict):
                    eid = epic.get("id", epic.get("epic_id", ""))
                    name = epic.get("name", epic.get("title", ""))
                    desc = epic.get("description", "")[:200]
                    parts.append(f"- {eid}: {name} - {desc}")
            parts.append("")

        # Tech stack
        tech = artifacts.get("tech_stack")
        if tech:
            ts = tech if isinstance(tech, dict) else {}
            parts.append("## Tech Stack")
            for key in ["architecture_pattern", "backend_framework", "frontend_framework",
                         "database", "ci_cd", "containerization", "cloud_provider",
                         "programming_language"]:
                val = ts.get(key)
                if val:
                    parts.append(f"- {key}: {val}")
            parts.append("")

        # Feature breakdown
        features = artifacts.get("feature_breakdown")
        if features:
            feat_list = features if isinstance(features, list) else features.get("features", [])
            parts.append("## Features")
            for feat in feat_list[:15]:
                if isinstance(feat, dict):
                    parts.append(f"- {feat.get('name', feat.get('id', ''))}: {feat.get('description', '')[:100]}")
            parts.append("")

        # API endpoints
        api = artifacts.get("api_spec")
        if api:
            endpoints = api if isinstance(api, list) else api.get("endpoints", api.get("paths", []))
            if isinstance(endpoints, list):
                parts.append("## API Endpoints")
                for ep in endpoints[:15]:
                    if isinstance(ep, dict):
                        parts.append(f"- {ep.get('method', 'GET')} {ep.get('path', ep.get('endpoint', ''))}")
                parts.append("")

        # Available diagrams
        diagrams = artifacts.get("diagrams", [])
        if diagrams:
            parts.append(f"## Available Diagrams ({len(diagrams)} .mmd files)")
            for d in diagrams[:10]:
                parts.append(f"- {d}")
            parts.append("")

        # Work breakdown mode from config
        wb_mode = self.scaffold_config.get("structure_strategy", "auto")
        if wb_mode == "auto":
            parts.append("## Structure Strategy: AUTO - decide based on architecture pattern")
        else:
            parts.append(f"## Structure Strategy: {wb_mode}")
        parts.append("")

        # Ledger context
        if context.task_ledger_summary:
            parts.append(f"## Previous Context\n{context.task_ledger_summary}\n")

        parts.append(
            "Return a JSON object with: project_name, structure_strategy, strategy_rationale, "
            "directories (path + purpose + optional epic_id), "
            "files (path + content_type + content + optional epic_id), "
            "doc_placement (source_pattern + target_dir), "
            "epic_mapping (epic_id -> directory path)."
        )

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # LLM Call
    # ------------------------------------------------------------------

    async def _get_scaffold_plan(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Call LLM to get the scaffold plan as structured JSON."""
        try:
            response = await self._call_llm(
                system_prompt=SCAFFOLD_SYSTEM_PROMPT,
                user_prompt=prompt,
            )

            if not response:
                return None

            # Parse JSON from response - handle markdown fences
            text = response if isinstance(response, str) else str(response)
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            return json.loads(text.strip())

        except json.JSONDecodeError as e:
            log.error(f"Failed to parse LLM scaffold response as JSON: {e}")
            log.debug(f"Raw response: {response[:500] if response else 'None'}")
            return None
        except Exception as e:
            log.error(f"LLM call for scaffold plan failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Scaffold Creation
    # ------------------------------------------------------------------

    def _create_scaffold(
        self, scaffold_dir: Path, plan: Dict[str, Any]
    ) -> tuple[List[str], List[str]]:
        """Create directories and files on disk from the plan."""
        created_dirs = []
        created_files = []

        # Create base directory
        scaffold_dir.mkdir(parents=True, exist_ok=True)
        created_dirs.append(str(scaffold_dir))

        # Create directories
        for dir_spec in plan.get("directories", []):
            # Handle both dict format {"path": "src/"} and plain string "src/"
            if isinstance(dir_spec, str):
                dir_rel = dir_spec
            else:
                dir_rel = dir_spec.get("path", "") if isinstance(dir_spec, dict) else str(dir_spec)
            if not dir_rel:
                continue
            dir_path = scaffold_dir / self._sanitize_path(dir_rel)
            dir_path.mkdir(parents=True, exist_ok=True)
            created_dirs.append(str(dir_path))

        # Create files
        for file_spec in plan.get("files", []):
            # Handle both dict format {"path": "...", "content_type": "..."} and plain string
            if isinstance(file_spec, str):
                file_spec = {"path": file_spec, "content_type": "placeholder"}
            if not isinstance(file_spec, dict) or "path" not in file_spec:
                continue
            file_path = scaffold_dir / self._sanitize_path(file_spec["path"])
            file_path.parent.mkdir(parents=True, exist_ok=True)

            content = file_spec.get("content", "")
            content_type = file_spec.get("content_type", "placeholder")

            # Generate content based on type if not provided by LLM
            if not content:
                content = self._generate_file_content(file_spec, plan)

            try:
                file_path.write_text(content, encoding="utf-8")
                created_files.append(str(file_path))
            except Exception as e:
                log.warning(f"Failed to create {file_path}: {e}")

        # Ensure root README.md always exists
        root_readme = scaffold_dir / "README.md"
        if not root_readme.exists():
            project_name = plan.get("project_name", "project")
            strategy = plan.get("structure_strategy", "auto")
            rationale = plan.get("strategy_rationale", "")
            epic_lines = "\n".join(
                f"- **{eid}**: `{path}`"
                for eid, path in plan.get("epic_mapping", {}).items()
            )
            root_readme.write_text(
                f"# {project_name}\n\n"
                f"Generated project scaffold.\n\n"
                f"## Structure Strategy\n{strategy}: {rationale}\n\n"
                f"## Epics\n{epic_lines}\n\n"
                f"## Getting Started\nTODO: Add setup instructions.\n",
                encoding="utf-8",
            )
            created_files.append(str(root_readme))

        return created_dirs, created_files

    def _sanitize_path(self, path_str: str) -> str:
        """Sanitize a path string to prevent path traversal and invalid chars."""
        # Remove leading slashes and dots
        cleaned = path_str.lstrip("/\\.")
        # Remove any .. components
        parts = Path(cleaned).parts
        safe_parts = [p for p in parts if p != ".."]
        # Limit depth
        if len(safe_parts) > 10:
            safe_parts = safe_parts[:10]
        return str(Path(*safe_parts)) if safe_parts else "unnamed"

    def _generate_file_content(self, file_spec: Dict[str, Any], plan: Dict[str, Any]) -> str:
        """Generate placeholder content based on file type."""
        content_type = file_spec.get("content_type", "placeholder")
        project_name = plan.get("project_name", "project")
        epic_id = file_spec.get("epic_id", "")

        generators = {
            "project_overview": lambda: (
                f"# {project_name}\n\n"
                f"Generated project scaffold.\n\n"
                f"## Structure Strategy\n{plan.get('strategy_rationale', '')}\n\n"
                f"## Epics\n" +
                "\n".join(f"- {eid}: {path}" for eid, path in plan.get("epic_mapping", {}).items())
            ),
            "readme": lambda: f"# {Path(file_spec['path']).parent.name}\n\nTODO: Add description.\n",
            "service_readme": lambda: (
                f"# {Path(file_spec['path']).parent.name}\n\n"
                f"Service for epic: {epic_id}\n\n"
                f"## Overview\nTODO: Add service description.\n\n"
                f"## API\nSee `api/` directory.\n\n"
                f"## Development\n```bash\n# TODO: Add setup instructions\n```\n"
            ),
            "epic_readme": lambda: (
                f"# Epic: {epic_id}\n\n"
                f"## Description\nSee linked user stories and requirements.\n\n"
                f"## Artifacts\n- User Stories\n- Diagrams\n- Test Cases\n"
            ),
            "dockerfile": lambda: (
                "# Auto-generated Dockerfile placeholder\n"
                "FROM python:3.12-slim\n\n"
                "WORKDIR /app\n\n"
                "COPY requirements.txt .\n"
                "RUN pip install --no-cache-dir -r requirements.txt\n\n"
                "COPY . .\n\n"
                'CMD ["python", "main.py"]\n'
            ),
            "gitignore": lambda: (
                "# Auto-generated .gitignore\n"
                "__pycache__/\n*.pyc\n.env\n.venv/\nnode_modules/\n"
                "dist/\nbuild/\n*.egg-info/\n.pytest_cache/\n"
                ".coverage\nhtmlcov/\n*.log\n"
            ),
            "ci_config": lambda: (
                "# Auto-generated CI configuration\n"
                "name: CI\n\n"
                "on:\n  push:\n    branches: [main]\n  pull_request:\n    branches: [main]\n\n"
                "jobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n"
                "      - uses: actions/checkout@v4\n"
                "      - name: Set up Python\n        uses: actions/setup-python@v5\n"
                "        with:\n          python-version: '3.12'\n"
                "      - name: Install dependencies\n        run: pip install -r requirements.txt\n"
                "      - name: Run tests\n        run: pytest\n"
            ),
            "docker_compose": lambda: (
                f"# Auto-generated docker-compose.yml for {project_name}\n"
                "version: '3.8'\n\nservices:\n"
                "  # TODO: Add service definitions\n"
                "  app:\n    build: .\n    ports:\n      - '8000:8000'\n"
            ),
            "makefile": lambda: (
                f"# Makefile for {project_name}\n\n"
                ".PHONY: help install test lint run\n\n"
                "help:\n\t@echo 'Available targets: install, test, lint, run'\n\n"
                "install:\n\tpip install -r requirements.txt\n\n"
                "test:\n\tpytest\n\n"
                "lint:\n\tflake8 src/\n\n"
                "run:\n\tpython -m src.main\n"
            ),
            "adr": lambda: (
                f"# ADR: Architecture Decision\n\n"
                f"## Status\nAccepted\n\n"
                f"## Context\nBased on requirements engineering analysis.\n\n"
                f"## Decision\n{plan.get('strategy_rationale', 'See scaffold manifest.')}\n\n"
                f"## Consequences\nSee project structure.\n"
            ),
        }

        generator = generators.get(content_type, lambda: f"# {file_spec['path']}\n\nPlaceholder.\n")
        return generator()

    # ------------------------------------------------------------------
    # Document Placement
    # ------------------------------------------------------------------

    def _place_documents(
        self,
        source_dir: Path,
        scaffold_dir: Path,
        placements: List[Dict[str, Any]],
        artifacts: Dict[str, Any],
    ) -> List[str]:
        """Copy/place existing RE docs into the scaffold structure."""
        placed = []

        for placement in placements:
            if not isinstance(placement, dict):
                continue
            source_pattern = placement.get("source_pattern", "")
            target_dir_str = placement.get("target_dir", "")

            if not source_pattern or not target_dir_str:
                continue

            target_dir = scaffold_dir / self._sanitize_path(target_dir_str)
            target_dir.mkdir(parents=True, exist_ok=True)

            # Find matching source files
            try:
                matched_files = list(source_dir.glob(source_pattern))
                for src_file in matched_files:
                    if src_file.is_file():
                        dst = target_dir / src_file.name
                        shutil.copy2(str(src_file), str(dst))
                        placed.append(str(dst))
                        log.debug(f"Placed {src_file.name} -> {dst}")
            except Exception as e:
                log.warning(f"Failed to place docs for pattern '{source_pattern}': {e}")

        # Also place diagrams if not already covered
        diagrams_dir = source_dir / "diagrams"
        scaffold_diagrams = scaffold_dir / "docs" / "diagrams"
        if diagrams_dir.exists() and not scaffold_diagrams.exists():
            scaffold_diagrams.mkdir(parents=True, exist_ok=True)
            for mmd_file in diagrams_dir.glob("*.mmd"):
                dst = scaffold_diagrams / mmd_file.name
                if not dst.exists():
                    shutil.copy2(str(mmd_file), str(dst))
                    placed.append(str(dst))

        return placed

    # ------------------------------------------------------------------
    # Manifest
    # ------------------------------------------------------------------

    def _generate_manifest(
        self,
        plan: Dict[str, Any],
        created_dirs: List[str],
        created_files: List[str],
        placed_docs: List[str],
    ) -> Dict[str, Any]:
        """Generate scaffold_manifest.json with all decisions and results."""
        return {
            "project_name": plan.get("project_name", ""),
            "structure_strategy": plan.get("structure_strategy", ""),
            "strategy_rationale": plan.get("strategy_rationale", ""),
            "epic_mapping": plan.get("epic_mapping", {}),
            "statistics": {
                "directories_created": len(created_dirs),
                "files_created": len(created_files),
                "docs_placed": len(placed_docs),
            },
            "created_directories": created_dirs,
            "created_files": created_files,
            "placed_documents": placed_docs,
            "doc_placement_rules": plan.get("doc_placement", []),
        }
