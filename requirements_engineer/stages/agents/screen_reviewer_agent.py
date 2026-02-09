"""
Screen Reviewer Agent for Multi-Agent Screen Design.

Reviews screen quality across 5 dimensions, all programmatically (no LLM).
Produces a quality score and issue list for the ScreenImproverAgent.

Quality Dimensions:
- wireframe_quality: ASCII wireframe exists, has box chars, COMP-IDs visible
- component_coverage: All referenced COMP-IDs exist in the component library
- story_coverage: Screen references a real user story
- layout_coherence: component_layout has x,y,w,h, no overlaps
- data_completeness: data_requirements not empty, valid endpoints
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .base_presentation_agent import (
    AgentCapability,
    AgentResult,
    AgentRole,
    BasePresentationAgent,
    PresentationContext,
)

logger = logging.getLogger(__name__)

# Default quality targets per dimension
DEFAULT_TARGETS = {
    "wireframe_quality": 0.80,
    "component_coverage": 0.90,
    "story_coverage": 0.85,
    "layout_coherence": 0.80,
    "data_completeness": 0.75,
}


class ScreenReviewerAgent(BasePresentationAgent):
    """
    Reviews screen designs across 5 quality dimensions.

    All checks are programmatic (no LLM calls). Outputs a quality
    score and a list of issues for ScreenImproverAgent to fix.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.targets = {**DEFAULT_TARGETS, **cfg.get("quality_targets", {})}
        super().__init__(
            name="ScreenReviewer",
            role=AgentRole.SCREEN_REVIEWER,
            description="Reviews screen quality across 5 dimensions (programmatic)",
            capabilities=[
                AgentCapability.SCREEN_REVIEW,
                AgentCapability.QUALITY_EVALUATION,
            ],
            config=cfg,
        )

    async def execute(self, context: PresentationContext) -> AgentResult:
        """Review all screens in ui_spec.json."""
        start_time = time.time()
        self._log_progress("Starting screen review")

        output_dir = Path(context.output_dir)

        # Load ui_spec
        ui_spec = self._load_json(output_dir / "ui_design" / "ui_spec.json")
        if not ui_spec:
            return AgentResult(
                success=False,
                error_message="ui_spec.json not found or empty",
                duration_seconds=time.time() - start_time,
            )

        screens = ui_spec.get("screens", [])
        if not screens:
            return AgentResult(
                success=False,
                error_message="No screens found in ui_spec.json",
                duration_seconds=time.time() - start_time,
            )

        components = ui_spec.get("components", [])
        comp_ids = {c.get("id", "") for c in components if isinstance(c, dict)}

        # Load user stories for story_coverage check
        user_stories = self._load_json(output_dir / "user_stories.json", default=[])
        if isinstance(user_stories, dict):
            user_stories = user_stories.get("user_stories", user_stories.get("stories", []))
        story_ids = {s.get("id", "") for s in user_stories if isinstance(s, dict)}

        # Review each screen
        all_issues: List[Dict[str, Any]] = []
        dimension_scores: Dict[str, List[float]] = {dim: [] for dim in DEFAULT_TARGETS}

        for screen in screens:
            if not isinstance(screen, dict):
                continue
            screen_id = screen.get("id", "UNKNOWN")

            # Dimension 1: wireframe_quality
            wf_score, wf_issues = self._check_wireframe_quality(screen, screen_id)
            dimension_scores["wireframe_quality"].append(wf_score)
            all_issues.extend(wf_issues)

            # Dimension 2: component_coverage
            cc_score, cc_issues = self._check_component_coverage(screen, screen_id, comp_ids)
            dimension_scores["component_coverage"].append(cc_score)
            all_issues.extend(cc_issues)

            # Dimension 3: story_coverage
            sc_score, sc_issues = self._check_story_coverage(screen, screen_id, story_ids)
            dimension_scores["story_coverage"].append(sc_score)
            all_issues.extend(sc_issues)

            # Dimension 4: layout_coherence
            lc_score, lc_issues = self._check_layout_coherence(screen, screen_id)
            dimension_scores["layout_coherence"].append(lc_score)
            all_issues.extend(lc_issues)

            # Dimension 5: data_completeness
            dc_score, dc_issues = self._check_data_completeness(screen, screen_id)
            dimension_scores["data_completeness"].append(dc_score)
            all_issues.extend(dc_issues)

        # Calculate aggregate scores
        dim_averages: Dict[str, float] = {}
        for dim, scores in dimension_scores.items():
            dim_averages[dim] = sum(scores) / len(scores) if scores else 0.0

        # Weighted overall score (equal weights)
        overall = sum(dim_averages.values()) / len(dim_averages) if dim_averages else 0.0

        # Check if improvement is needed
        needs_improvement = False
        for dim, avg in dim_averages.items():
            target = self.targets.get(dim, 0.8)
            if avg < target:
                needs_improvement = True
                break

        # Save review report
        report = {
            "screens_reviewed": len(screens),
            "dimension_scores": dim_averages,
            "overall_score": overall,
            "targets": self.targets,
            "issues_count": len(all_issues),
            "issues": all_issues,
            "needs_improvement": needs_improvement,
        }
        report_path = output_dir / "ui_design" / "screen_review_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

        duration = time.time() - start_time
        self._log_progress(
            f"Review complete: overall={overall:.1%}, issues={len(all_issues)}, "
            f"needs_improvement={needs_improvement}"
        )

        return AgentResult(
            success=True,
            generated_files=[str(report_path)],
            quality_score=overall,
            quality_issues=all_issues,
            action_type="review_screen",
            duration_seconds=duration,
            notes=f"Reviewed {len(screens)} screens: {', '.join(f'{d}={s:.0%}' for d, s in dim_averages.items())}",
            needs_improvement=needs_improvement,
        )

    # ================================================================
    # Dimension Checkers
    # ================================================================

    def _check_wireframe_quality(
        self, screen: Dict, screen_id: str
    ) -> Tuple[float, List[Dict]]:
        """Check wireframe quality: ASCII art exists, has structure chars, COMP-IDs."""
        issues = []
        checks_passed = 0
        total_checks = 4

        wireframe = screen.get("wireframe_ascii", "")

        # Check 1: Wireframe exists and has content
        if wireframe and len(wireframe) > 50:
            checks_passed += 1
        else:
            issues.append({
                "severity": "major",
                "dimension": "wireframe_quality",
                "screen_id": screen_id,
                "description": f"Missing or too short wireframe for {screen_id}",
                "fix_hint": "Regenerate wireframe via LLM",
            })

        # Check 2: Has box-drawing characters (+, |, -)
        box_chars = set("+-|")
        if wireframe and box_chars.intersection(set(wireframe)):
            checks_passed += 1
        else:
            issues.append({
                "severity": "minor",
                "dimension": "wireframe_quality",
                "screen_id": screen_id,
                "description": f"Wireframe lacks box-drawing characters in {screen_id}",
                "fix_hint": "Regenerate wireframe with proper ASCII structure",
            })

        # Check 3: Has coordinate markers (numbers at edges)
        if wireframe and re.search(r"\d+", wireframe):
            checks_passed += 1
        else:
            issues.append({
                "severity": "minor",
                "dimension": "wireframe_quality",
                "screen_id": screen_id,
                "description": f"Wireframe lacks coordinate markers in {screen_id}",
                "fix_hint": "Add coordinate grid to wireframe edges",
            })

        # Check 4: COMP-IDs visible in wireframe
        comp_ids_in_screen = screen.get("components", [])
        comps_in_wireframe = sum(
            1 for cid in comp_ids_in_screen if cid in wireframe
        ) if wireframe else 0
        if comp_ids_in_screen and comps_in_wireframe >= len(comp_ids_in_screen) * 0.5:
            checks_passed += 1
        elif not comp_ids_in_screen:
            checks_passed += 1  # No components to check
        else:
            issues.append({
                "severity": "major",
                "dimension": "wireframe_quality",
                "screen_id": screen_id,
                "description": f"Only {comps_in_wireframe}/{len(comp_ids_in_screen)} COMP-IDs visible in wireframe of {screen_id}",
                "fix_hint": "Ensure all component IDs appear in the wireframe",
            })

        return checks_passed / total_checks, issues

    def _check_component_coverage(
        self, screen: Dict, screen_id: str, library_ids: Set[str]
    ) -> Tuple[float, List[Dict]]:
        """Check that all referenced component IDs exist in the library."""
        issues = []
        comp_ids = screen.get("components", [])

        if not comp_ids:
            issues.append({
                "severity": "major",
                "dimension": "component_coverage",
                "screen_id": screen_id,
                "description": f"No components referenced in {screen_id}",
                "fix_hint": "Add component references from library",
            })
            return 0.0, issues

        if not library_ids:
            # No library to compare against - pass by default
            return 1.0, issues

        valid = sum(1 for cid in comp_ids if cid in library_ids)
        invalid_ids = [cid for cid in comp_ids if cid not in library_ids]

        if invalid_ids:
            issues.append({
                "severity": "major",
                "dimension": "component_coverage",
                "screen_id": screen_id,
                "description": f"Invalid COMP-IDs in {screen_id}: {', '.join(invalid_ids)}",
                "fix_hint": f"Remove or map invalid IDs. Valid: {', '.join(sorted(library_ids)[:10])}",
            })

        return valid / len(comp_ids) if comp_ids else 0.0, issues

    def _check_story_coverage(
        self, screen: Dict, screen_id: str, story_ids: Set[str]
    ) -> Tuple[float, List[Dict]]:
        """Check that screen references a real user story."""
        issues = []
        parent_story = screen.get("parent_user_story", "")

        if not parent_story:
            issues.append({
                "severity": "minor",
                "dimension": "story_coverage",
                "screen_id": screen_id,
                "description": f"No parent_user_story set for {screen_id}",
                "fix_hint": "Set parent_user_story field",
            })
            return 0.0, issues

        if story_ids and parent_story not in story_ids:
            issues.append({
                "severity": "minor",
                "dimension": "story_coverage",
                "screen_id": screen_id,
                "description": f"parent_user_story '{parent_story}' not found in story list for {screen_id}",
                "fix_hint": f"Map to valid story ID. Available: {', '.join(sorted(story_ids)[:5])}",
            })
            return 0.5, issues  # Partial credit: field exists but wrong ID

        return 1.0, issues

    def _check_layout_coherence(
        self, screen: Dict, screen_id: str
    ) -> Tuple[float, List[Dict]]:
        """Check component_layout has x,y,w,h and no overlaps."""
        issues = []
        layout = screen.get("component_layout", [])

        if not layout:
            issues.append({
                "severity": "major",
                "dimension": "layout_coherence",
                "screen_id": screen_id,
                "description": f"Empty component_layout in {screen_id}",
                "fix_hint": "Generate component_layout with x,y,w,h for each component",
            })
            return 0.0, issues

        checks_passed = 0
        total_checks = 2

        # Check 1: All entries have x,y,w,h
        valid_entries = 0
        for entry in layout:
            if not isinstance(entry, dict):
                continue
            has_coords = all(
                key in entry and isinstance(entry[key], (int, float))
                for key in ("x", "y", "w", "h")
            )
            if has_coords:
                valid_entries += 1
            else:
                issues.append({
                    "severity": "minor",
                    "dimension": "layout_coherence",
                    "screen_id": screen_id,
                    "description": f"Missing x/y/w/h in layout entry: {entry.get('id', '?')} in {screen_id}",
                    "fix_hint": "Add missing coordinate fields",
                })

        if valid_entries == len(layout):
            checks_passed += 1
        elif valid_entries > 0:
            checks_passed += 0.5

        # Check 2: No overlaps (containment-aware)
        # If rect A fully contains rect B, it's a parent-child relationship, not an overlap
        rects = []
        for entry in layout:
            if not isinstance(entry, dict):
                continue
            try:
                x, y = float(entry.get("x", 0)), float(entry.get("y", 0))
                w, h = float(entry.get("w", 0)), float(entry.get("h", 0))
                if w > 0 and h > 0:
                    rects.append((entry.get("id", "?"), x, y, x + w, y + h))
            except (TypeError, ValueError):
                continue

        overlap_count = 0
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                _, x1a, y1a, x2a, y2a = rects[i]
                _, x1b, y1b, x2b, y2b = rects[j]
                # Check intersection
                if x1a < x2b and x2a > x1b and y1a < y2b and y2a > y1b:
                    # Check if one fully contains the other (parent-child)
                    a_contains_b = (x1a <= x1b and y1a <= y1b and x2a >= x2b and y2a >= y2b)
                    b_contains_a = (x1b <= x1a and y1b <= y1a and x2b >= x2a and y2b >= y2a)
                    if not a_contains_b and not b_contains_a:
                        overlap_count += 1

        if overlap_count == 0:
            checks_passed += 1
        else:
            issues.append({
                "severity": "minor",
                "dimension": "layout_coherence",
                "screen_id": screen_id,
                "description": f"{overlap_count} component overlap(s) in {screen_id}",
                "fix_hint": "Adjust x,y,w,h to resolve overlaps",
            })

        return checks_passed / total_checks, issues

    def _check_data_completeness(
        self, screen: Dict, screen_id: str
    ) -> Tuple[float, List[Dict]]:
        """Check that data_requirements is not empty and contains valid endpoints."""
        issues = []
        data_reqs = screen.get("data_requirements", [])

        if not data_reqs:
            issues.append({
                "severity": "minor",
                "dimension": "data_completeness",
                "screen_id": screen_id,
                "description": f"Empty data_requirements for {screen_id}",
                "fix_hint": "Add API endpoint references",
            })
            return 0.0, issues

        # Check that entries look like endpoints (have HTTP method or path)
        valid = 0
        for req in data_reqs:
            if isinstance(req, str) and (
                req.startswith("GET ")
                or req.startswith("POST ")
                or req.startswith("PUT ")
                or req.startswith("DELETE ")
                or req.startswith("PATCH ")
                or req.startswith("/")
            ):
                valid += 1

        if valid < len(data_reqs):
            issues.append({
                "severity": "minor",
                "dimension": "data_completeness",
                "screen_id": screen_id,
                "description": f"{len(data_reqs) - valid} non-standard endpoint(s) in {screen_id}",
                "fix_hint": "Use format: 'GET /api/resource' or '/api/resource'",
            })

        return valid / len(data_reqs) if data_reqs else 0.0, issues

    # ================================================================
    # Helpers
    # ================================================================

    def _load_json(self, path: Path, default: Any = None) -> Any:
        """Load a JSON file, returning default on failure."""
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            self._log_error(f"Failed to load {path}: {e}")
        return default if default is not None else {}
