"""
Scaffold Reviewer Agent for Multi-Agent Presentation System.

Reviews the generated project scaffold for quality across 5 dimensions:
- Epic coverage: every epic maps to at least one directory
- Doc placement: all RE artifacts are placed in the structure
- Structure sanity: no excessive depth, no orphan directories
- Config completeness: expected config files present
- Naming consistency: consistent naming convention throughout
"""

import json
import logging
import re
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

MAX_DEPTH = 10
EXPECTED_CONFIG_FILES = [
    "README.md", ".gitignore",
]
OPTIONAL_CONFIG_FILES = [
    "Dockerfile", "docker-compose.yml", "Makefile",
    ".github/workflows/ci.yml", ".gitlab-ci.yml",
]


class ScaffoldReviewerAgent(BasePresentationAgent):
    """
    Reviews a generated project scaffold for quality.

    Computes scores across 5 dimensions and returns quality issues
    that the ScaffoldImproverAgent can fix.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(
            name="ScaffoldReviewer",
            role=AgentRole.SCAFFOLD_REVIEWER,
            description="Reviews scaffold quality across 5 dimensions",
            capabilities=[
                AgentCapability.QUALITY_EVALUATION,
                AgentCapability.ARTIFACT_PARSING,
            ],
            config=config,
        )
        quality_cfg = config.get("quality_targets", {}) if config else {}
        self.targets = {
            "epic_coverage": quality_cfg.get("epic_coverage", 0.95),
            "doc_placement": quality_cfg.get("doc_placement", 0.90),
            "structure_sanity": quality_cfg.get("structure_sanity", 0.85),
            "config_completeness": quality_cfg.get("config_completeness", 0.80),
            "naming_consistency": quality_cfg.get("naming_consistency", 0.90),
        }

    async def execute(self, context: PresentationContext) -> AgentResult:
        """Review the scaffold and return quality scores + issues."""
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
                    action_type="REVIEW_SCAFFOLD",
                    duration_seconds=time.time() - start_time,
                )

            # Load manifest
            manifest = self._load_manifest(scaffold_dir)
            if not manifest:
                return AgentResult(
                    success=False,
                    error_message="scaffold_manifest.json not found or invalid",
                    action_type="REVIEW_SCAFFOLD",
                    duration_seconds=time.time() - start_time,
                )

            # Load epics for coverage check
            epics = self._load_epics(output_dir)

            # Run all quality checks
            scores = {}
            all_issues = []

            # 1. Epic coverage
            score, issues = self._check_epic_coverage(scaffold_dir, manifest, epics)
            scores["epic_coverage"] = score
            all_issues.extend(issues)

            # 2. Doc placement
            score, issues = self._check_doc_placement(scaffold_dir, output_dir)
            scores["doc_placement"] = score
            all_issues.extend(issues)

            # 3. Structure sanity
            score, issues = self._check_structure_sanity(scaffold_dir)
            scores["structure_sanity"] = score
            all_issues.extend(issues)

            # 4. Config completeness
            score, issues = self._check_config_completeness(scaffold_dir)
            scores["config_completeness"] = score
            all_issues.extend(issues)

            # 5. Naming consistency
            score, issues = self._check_naming_consistency(scaffold_dir)
            scores["naming_consistency"] = score
            all_issues.extend(issues)

            # Overall score (weighted average)
            overall = sum(scores.values()) / len(scores) if scores else 0.0
            scores["overall"] = overall

            # Determine if improvement is needed
            target = context.quality_threshold or 0.85
            needs_improvement = overall < target

            # Save review report
            report = {
                "scores": scores,
                "targets": self.targets,
                "issues": [
                    {"severity": i["severity"], "dimension": i["dimension"],
                     "description": i["description"], "fix_hint": i.get("fix_hint", "")}
                    for i in all_issues
                ],
                "overall_score": overall,
                "target_quality": target,
                "passed": not needs_improvement,
            }
            report_path = scaffold_dir / "scaffold_review_report.json"
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

            duration = time.time() - start_time
            self._log_progress(
                f"Review complete: overall={overall:.2f}, "
                f"issues={len(all_issues)}, passed={not needs_improvement} "
                f"({duration:.1f}s)"
            )

            return AgentResult(
                success=True,
                generated_files=[str(report_path)],
                generated_content=json.dumps(report, indent=2),
                quality_score=overall,
                quality_issues=[
                    {"severity": i["severity"], "description": i["description"],
                     "dimension": i["dimension"]}
                    for i in all_issues
                ],
                action_type="REVIEW_SCAFFOLD",
                duration_seconds=duration,
                notes=f"Scaffold quality: {overall:.1%} ({len(all_issues)} issues)",
                needs_improvement=needs_improvement,
                confidence=0.9,
            )

        except Exception as e:
            self._log_error(f"Scaffold review failed: {e}")
            return AgentResult(
                success=False,
                error_message=str(e),
                action_type="REVIEW_SCAFFOLD",
                duration_seconds=time.time() - start_time,
            )
        finally:
            self._is_running = False

    # ------------------------------------------------------------------
    # Quality Checks
    # ------------------------------------------------------------------

    def _check_epic_coverage(
        self, scaffold_dir: Path, manifest: Dict, epics: List[Dict]
    ) -> tuple[float, List[Dict]]:
        """Check that every epic has at least one directory."""
        issues = []

        if not epics:
            return 1.0, []

        epic_mapping = manifest.get("epic_mapping", {})
        covered = 0

        for epic in epics:
            epic_id = epic.get("id", epic.get("epic_id", ""))
            epic_name = epic.get("name", epic.get("title", ""))

            if epic_id in epic_mapping:
                mapped_path = scaffold_dir / epic_mapping[epic_id]
                if mapped_path.exists():
                    covered += 1
                else:
                    issues.append({
                        "severity": "major",
                        "dimension": "epic_coverage",
                        "description": f"Epic {epic_id} ({epic_name}) mapped to {epic_mapping[epic_id]} but directory does not exist",
                        "fix_hint": f"Create directory: {epic_mapping[epic_id]}",
                    })
            else:
                # Check if any directory name matches the epic
                slug = self._slugify(epic_name) if epic_name else ""
                found = False
                if slug:
                    for d in scaffold_dir.rglob("*"):
                        if d.is_dir() and slug in d.name.lower():
                            found = True
                            break
                if found:
                    covered += 1
                else:
                    issues.append({
                        "severity": "major",
                        "dimension": "epic_coverage",
                        "description": f"Epic {epic_id} ({epic_name}) has no mapped directory",
                        "fix_hint": f"Add epic to mapping and create directory",
                    })

        score = covered / len(epics) if epics else 1.0
        return score, issues

    def _check_doc_placement(
        self, scaffold_dir: Path, source_dir: Path
    ) -> tuple[float, List[Dict]]:
        """Check that RE artifacts are placed in the scaffold."""
        issues = []
        total_artifacts = 0
        placed_artifacts = 0

        # Check diagrams
        source_diagrams = list((source_dir / "diagrams").glob("*.mmd")) if (source_dir / "diagrams").exists() else []
        total_artifacts += len(source_diagrams)

        scaffold_docs = scaffold_dir / "docs"
        for diagram in source_diagrams:
            # Check if placed anywhere in scaffold
            found = any(scaffold_dir.rglob(diagram.name))
            if found:
                placed_artifacts += 1
            else:
                issues.append({
                    "severity": "minor",
                    "dimension": "doc_placement",
                    "description": f"Diagram {diagram.name} not found in scaffold",
                    "fix_hint": f"Copy to docs/diagrams/{diagram.name}",
                })

        # Check key doc files
        key_docs = [
            "requirements.json", "requirements.md",
            "user_stories.json", "api_spec.json",
        ]
        for doc_name in key_docs:
            if (source_dir / doc_name).exists():
                total_artifacts += 1
                if any(scaffold_dir.rglob(doc_name)):
                    placed_artifacts += 1
                elif any(scaffold_dir.rglob(f"*.md")):
                    # May have been converted to markdown
                    placed_artifacts += 1

        score = placed_artifacts / total_artifacts if total_artifacts > 0 else 1.0
        return score, issues

    def _check_structure_sanity(self, scaffold_dir: Path) -> tuple[float, List[Dict]]:
        """Check directory depth and orphan directories."""
        issues = []
        total_checks = 0
        passed_checks = 0

        all_dirs = [d for d in scaffold_dir.rglob("*") if d.is_dir()]

        for d in all_dirs:
            total_checks += 1
            rel = d.relative_to(scaffold_dir)
            depth = len(rel.parts)

            if depth > MAX_DEPTH:
                issues.append({
                    "severity": "major",
                    "dimension": "structure_sanity",
                    "description": f"Directory too deep ({depth} levels): {rel}",
                    "fix_hint": "Flatten directory structure",
                })
            else:
                passed_checks += 1

        # Check for empty directories (orphans) - only leaf dirs
        for d in all_dirs:
            children = list(d.iterdir())
            if not children:
                issues.append({
                    "severity": "minor",
                    "dimension": "structure_sanity",
                    "description": f"Empty directory: {d.relative_to(scaffold_dir)}",
                    "fix_hint": "Add README.md or remove directory",
                })

        # Check total directory count is reasonable
        total_checks += 1
        if len(all_dirs) > 200:
            issues.append({
                "severity": "major",
                "dimension": "structure_sanity",
                "description": f"Too many directories ({len(all_dirs)})",
                "fix_hint": "Simplify structure",
            })
        else:
            passed_checks += 1

        score = passed_checks / total_checks if total_checks > 0 else 1.0
        return score, issues

    def _check_config_completeness(self, scaffold_dir: Path) -> tuple[float, List[Dict]]:
        """Check that expected config files exist."""
        issues = []
        total = len(EXPECTED_CONFIG_FILES) + len(OPTIONAL_CONFIG_FILES)
        found = 0

        for cfg_file in EXPECTED_CONFIG_FILES:
            if (scaffold_dir / cfg_file).exists():
                found += 1
            else:
                issues.append({
                    "severity": "major",
                    "dimension": "config_completeness",
                    "description": f"Missing required config: {cfg_file}",
                    "fix_hint": f"Generate {cfg_file}",
                })

        for cfg_file in OPTIONAL_CONFIG_FILES:
            if (scaffold_dir / cfg_file).exists():
                found += 1

        score = found / total if total > 0 else 1.0
        return score, issues

    def _check_naming_consistency(self, scaffold_dir: Path) -> tuple[float, List[Dict]]:
        """Check naming convention consistency (kebab-case vs snake_case)."""
        issues = []
        all_dirs = [d for d in scaffold_dir.rglob("*") if d.is_dir()]

        if not all_dirs:
            return 1.0, []

        kebab_count = 0
        snake_count = 0
        other_count = 0

        for d in all_dirs:
            name = d.name
            if not name or name.startswith("."):
                continue
            if "-" in name and "_" not in name:
                kebab_count += 1
            elif "_" in name and "-" not in name:
                snake_count += 1
            elif "-" in name and "_" in name:
                other_count += 1
                issues.append({
                    "severity": "minor",
                    "dimension": "naming_consistency",
                    "description": f"Mixed naming convention: {d.relative_to(scaffold_dir)}",
                    "fix_hint": "Use consistent kebab-case or snake_case",
                })

        total_named = kebab_count + snake_count + other_count
        if total_named == 0:
            return 1.0, []

        # Dominant convention should be >80% of named dirs
        dominant = max(kebab_count, snake_count)
        score = dominant / total_named if total_named > 0 else 1.0

        return score, issues

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_manifest(self, scaffold_dir: Path) -> Optional[Dict]:
        """Load scaffold_manifest.json."""
        manifest_path = scaffold_dir / "scaffold_manifest.json"
        try:
            if manifest_path.exists():
                with open(manifest_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            log.warning(f"Failed to load manifest: {e}")
        return None

    def _load_epics(self, output_dir: Path) -> List[Dict]:
        """Load epics from the output directory."""
        for name in ["epics.json", "epics/epics.json"]:
            path = output_dir / name
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        return data
                    return data.get("epics", [])
                except Exception:
                    pass
        return []

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert text to lowercase slug for matching."""
        return re.sub(r'[^\w]', '', text.lower().replace(" ", "").replace("-", ""))
