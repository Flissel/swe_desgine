"""
Scaffold Improver Agent for Multi-Agent Presentation System.

Takes quality issues from ScaffoldReviewerAgent and applies fixes:
- Creates missing epic directories with README
- Places missing documents into the structure
- Generates missing config files (README.md, .gitignore, Dockerfile)
- Fixes naming inconsistencies
- Removes empty orphan directories or populates them
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


class ScaffoldImproverAgent(BasePresentationAgent):
    """
    Applies improvements to a project scaffold based on reviewer feedback.

    Handles:
    - epic_coverage: create missing epic directories
    - doc_placement: copy missing documents
    - structure_sanity: fix depth issues, populate empty dirs
    - config_completeness: generate missing config files
    - naming_consistency: rename directories to consistent convention
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(
            name="ScaffoldImprover",
            role=AgentRole.SCAFFOLD_IMPROVER,
            description="Applies improvements to scaffold based on reviewer feedback",
            capabilities=[
                AgentCapability.SCAFFOLD_GENERATION,
                AgentCapability.FILE_PLACEMENT,
                AgentCapability.STRUCTURE_FIXING,
            ],
            config=config,
        )

    async def execute(self, context: PresentationContext) -> AgentResult:
        """Apply improvements based on quality issues in context."""
        self._is_running = True
        start_time = time.time()

        try:
            output_dir = Path(context.output_dir)
            scaffold_config = context.config.get("scaffold", {}) if context.config else {}
            scaffold_dir = output_dir / scaffold_config.get("output_dir", "project_scaffold")

            if not scaffold_dir.exists():
                return AgentResult(
                    success=False,
                    error_message=f"Scaffold directory not found: {scaffold_dir}",
                    action_type="IMPROVE_SCAFFOLD",
                    duration_seconds=time.time() - start_time,
                )

            # Get issues from context
            issues = context.quality_issues or []
            if not issues:
                # Try loading review report
                report_path = scaffold_dir / "scaffold_review_report.json"
                if report_path.exists():
                    with open(report_path, "r", encoding="utf-8") as f:
                        report = json.load(f)
                    issues = report.get("issues", [])

            if not issues:
                return AgentResult(
                    success=True,
                    action_type="IMPROVE_SCAFFOLD",
                    duration_seconds=time.time() - start_time,
                    notes="No issues to fix",
                )

            self._log_progress(f"Applying fixes for {len(issues)} issues")

            # Group issues by dimension
            by_dimension: Dict[str, List[Dict]] = {}
            for issue in issues:
                dim = issue.get("dimension", "unknown")
                by_dimension.setdefault(dim, []).append(issue)

            applied = []
            failed = []

            # Fix each dimension
            for dim, dim_issues in by_dimension.items():
                fixer = {
                    "epic_coverage": self._fix_epic_coverage,
                    "doc_placement": self._fix_doc_placement,
                    "structure_sanity": self._fix_structure_sanity,
                    "config_completeness": self._fix_config_completeness,
                    "naming_consistency": self._fix_naming_consistency,
                }.get(dim)

                if fixer:
                    results = fixer(scaffold_dir, output_dir, dim_issues)
                    applied.extend(results)
                else:
                    log.warning(f"No fixer for dimension: {dim}")

            # Update manifest
            self._update_manifest(scaffold_dir, applied)

            duration = time.time() - start_time
            self._log_progress(
                f"Applied {len(applied)} fixes ({duration:.1f}s)"
            )

            return AgentResult(
                success=True,
                generated_files=[f["path"] for f in applied if "path" in f],
                improvements_applied=[
                    {"type": f["type"], "description": f["description"]}
                    for f in applied
                ],
                action_type="IMPROVE_SCAFFOLD",
                duration_seconds=duration,
                notes=f"Applied {len(applied)} improvements across {len(by_dimension)} dimensions",
                suggested_next_agent="ScaffoldReviewer",
                confidence=0.85,
                needs_review=True,
            )

        except Exception as e:
            self._log_error(f"Scaffold improvement failed: {e}")
            return AgentResult(
                success=False,
                error_message=str(e),
                action_type="IMPROVE_SCAFFOLD",
                duration_seconds=time.time() - start_time,
            )
        finally:
            self._is_running = False

    # ------------------------------------------------------------------
    # Fixers per dimension
    # ------------------------------------------------------------------

    def _fix_epic_coverage(
        self, scaffold_dir: Path, output_dir: Path, issues: List[Dict]
    ) -> List[Dict]:
        """Create missing epic directories."""
        applied = []

        for issue in issues:
            hint = issue.get("fix_hint", "")
            desc = issue.get("description", "")

            # Extract epic info from description
            epic_match = re.search(r'Epic (\S+)', desc)
            epic_id = epic_match.group(1) if epic_match else "unknown"

            # Determine target directory
            if "Create directory:" in hint:
                dir_path = hint.split("Create directory:")[1].strip()
                target = scaffold_dir / dir_path
            else:
                # Create under docs/epics/
                slug = re.sub(r'[^\w-]', '', epic_id.lower().replace(" ", "-"))
                target = scaffold_dir / "docs" / "epics" / slug

            target.mkdir(parents=True, exist_ok=True)

            # Add README
            readme = target / "README.md"
            if not readme.exists():
                readme.write_text(
                    f"# {epic_id}\n\nEpic directory created by scaffold improver.\n\n"
                    f"## Status\nTODO: Add epic details.\n",
                    encoding="utf-8",
                )

            applied.append({
                "type": "create_epic_directory",
                "description": f"Created directory for {epic_id}: {target.relative_to(scaffold_dir)}",
                "path": str(readme),
            })

        return applied

    def _fix_doc_placement(
        self, scaffold_dir: Path, output_dir: Path, issues: List[Dict]
    ) -> List[Dict]:
        """Copy missing documents into scaffold."""
        applied = []

        for issue in issues:
            hint = issue.get("fix_hint", "")
            desc = issue.get("description", "")

            # Extract source filename from description
            name_match = re.search(r'(?:Diagram|Document|File) (\S+)', desc)
            if not name_match:
                continue

            filename = name_match.group(1)

            # Find source file
            source_files = list(output_dir.rglob(filename))
            if not source_files:
                continue

            source = source_files[0]

            # Determine target from hint or default
            if "Copy to" in hint:
                target_rel = hint.split("Copy to")[1].strip()
                target = scaffold_dir / target_rel
            else:
                # Default: docs/diagrams/ for .mmd, docs/ for others
                if source.suffix == ".mmd":
                    target = scaffold_dir / "docs" / "diagrams" / source.name
                else:
                    target = scaffold_dir / "docs" / source.name

            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(str(source), str(target))
                applied.append({
                    "type": "place_document",
                    "description": f"Placed {source.name} -> {target.relative_to(scaffold_dir)}",
                    "path": str(target),
                })

        return applied

    def _fix_structure_sanity(
        self, scaffold_dir: Path, output_dir: Path, issues: List[Dict]
    ) -> List[Dict]:
        """Fix structural issues: populate empty dirs, etc."""
        applied = []

        for issue in issues:
            desc = issue.get("description", "")

            if "Empty directory" in desc:
                # Extract directory path
                dir_match = re.search(r'Empty directory: (.+)', desc)
                if dir_match:
                    rel_path = dir_match.group(1)
                    target = scaffold_dir / rel_path
                    if target.exists() and target.is_dir():
                        readme = target / "README.md"
                        if not readme.exists():
                            dir_name = target.name.replace("-", " ").replace("_", " ").title()
                            readme.write_text(
                                f"# {dir_name}\n\nTODO: Add content.\n",
                                encoding="utf-8",
                            )
                            applied.append({
                                "type": "populate_empty_dir",
                                "description": f"Added README.md to empty directory: {rel_path}",
                                "path": str(readme),
                            })

        return applied

    def _fix_config_completeness(
        self, scaffold_dir: Path, output_dir: Path, issues: List[Dict]
    ) -> List[Dict]:
        """Generate missing config files."""
        applied = []

        config_generators = {
            "README.md": lambda: (
                "# Project\n\n"
                "Generated project scaffold from requirements engineering.\n\n"
                "## Getting Started\nTODO: Add setup instructions.\n\n"
                "## Structure\nSee `scaffold_manifest.json` for project layout details.\n"
            ),
            ".gitignore": lambda: (
                "__pycache__/\n*.pyc\n.env\n.venv/\nnode_modules/\n"
                "dist/\nbuild/\n*.egg-info/\n.pytest_cache/\n"
                ".coverage\nhtmlcov/\n*.log\n"
            ),
            "Dockerfile": lambda: (
                "FROM python:3.12-slim\nWORKDIR /app\n"
                "COPY requirements.txt .\n"
                "RUN pip install --no-cache-dir -r requirements.txt\n"
                "COPY . .\nCMD [\"python\", \"main.py\"]\n"
            ),
            "docker-compose.yml": lambda: (
                "version: '3.8'\nservices:\n  app:\n    build: .\n"
                "    ports:\n      - '8000:8000'\n"
            ),
            "Makefile": lambda: (
                ".PHONY: help install test\n\n"
                "help:\n\t@echo 'Targets: install, test'\n\n"
                "install:\n\tpip install -r requirements.txt\n\n"
                "test:\n\tpytest\n"
            ),
        }

        for issue in issues:
            desc = issue.get("description", "")
            hint = issue.get("fix_hint", "")

            # Extract filename
            for config_name, generator in config_generators.items():
                if config_name in desc or config_name in hint:
                    target = scaffold_dir / config_name
                    if not target.exists():
                        target.write_text(generator(), encoding="utf-8")
                        applied.append({
                            "type": "generate_config",
                            "description": f"Generated {config_name}",
                            "path": str(target),
                        })
                    break

        return applied

    def _fix_naming_consistency(
        self, scaffold_dir: Path, output_dir: Path, issues: List[Dict]
    ) -> List[Dict]:
        """Fix naming inconsistencies (log only, renaming is risky)."""
        applied = []

        for issue in issues:
            desc = issue.get("description", "")
            # Renaming directories is risky (breaks references), so just log
            applied.append({
                "type": "naming_warning",
                "description": f"Naming issue noted (not auto-fixed): {desc}",
            })

        return applied

    # ------------------------------------------------------------------
    # Manifest Update
    # ------------------------------------------------------------------

    def _update_manifest(self, scaffold_dir: Path, applied: List[Dict]) -> None:
        """Update scaffold_manifest.json with improvement info."""
        manifest_path = scaffold_dir / "scaffold_manifest.json"
        try:
            if manifest_path.exists():
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
            else:
                manifest = {}

            improvements = manifest.get("improvements_applied", [])
            improvements.extend([
                {"type": a["type"], "description": a["description"]}
                for a in applied
            ])
            manifest["improvements_applied"] = improvements

            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)

        except Exception as e:
            log.warning(f"Failed to update manifest: {e}")
