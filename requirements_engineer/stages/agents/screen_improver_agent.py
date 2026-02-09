"""
Screen Improver Agent for Multi-Agent Screen Design.

Fixes issues identified by ScreenReviewerAgent. Uses LLM for wireframe
regeneration and data_requirements, programmatic fixes for the rest.

Dimension fixers:
- wireframe_quality: LLM call to regenerate wireframe
- component_coverage: Remove/map invalid COMP-IDs
- story_coverage: Set parent_user_story field
- layout_coherence: Programmatically adjust x,y,w,h (resolve overlaps)
- data_completeness: LLM call for missing API endpoints
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .base_presentation_agent import (
    AgentCapability,
    AgentResult,
    AgentRole,
    BasePresentationAgent,
    PresentationContext,
)

logger = logging.getLogger(__name__)


class ScreenImproverAgent(BasePresentationAgent):
    """
    Fixes screen design issues based on reviewer feedback.

    Uses LLM for wireframe regeneration and data endpoint generation.
    Uses programmatic fixes for component coverage, story coverage,
    and layout coherence.
    """

    WIREFRAME_REGEN_PROMPT = """You are a UI designer. Fix and regenerate the ASCII wireframe for this screen.

## Screen: {screen_name}
Route: {route}
Layout: {layout}
Description: {description}

## Components:
{components_text}

## Issues Found:
{issues_text}

## Current Wireframe (if any):
{current_wireframe}

Generate an improved ASCII-art wireframe that:
- Has a coordinate grid (X on top, Y on left)
- Shows all components with [ComponentName] and COMP-ID labels
- Uses +, |, - for structure
- Is 60 characters wide
- Fixes the issues listed above

Reply ONLY with the ASCII wireframe text (no markdown fences, no explanation)."""

    DATA_ENDPOINT_PROMPT = """You are a backend API designer. Generate data requirements for this screen.

## Screen: {screen_name}
Route: {route}
Description: {description}
Components: {components_text}

Generate a JSON array of API endpoints needed for this screen.
Format: ["GET /api/resource", "POST /api/resource"]

Reply ONLY with the JSON array."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        super().__init__(
            name="ScreenImprover",
            role=AgentRole.SCREEN_IMPROVER,
            description="Fixes screen design issues from reviewer feedback",
            capabilities=[
                AgentCapability.SCREEN_GENERATION,
                AgentCapability.CONTENT_ENHANCEMENT,
            ],
            config=cfg,
        )

    async def execute(self, context: PresentationContext) -> AgentResult:
        """Fix screen issues based on context.quality_issues."""
        start_time = time.time()
        self._log_progress("Starting screen improvements")

        output_dir = Path(context.output_dir)
        issues = context.quality_issues or []

        if not issues:
            return AgentResult(
                success=True,
                notes="No issues to fix",
                duration_seconds=time.time() - start_time,
            )

        # Load ui_spec
        ui_spec_path = output_dir / "ui_design" / "ui_spec.json"
        ui_spec = self._load_json(ui_spec_path)
        if not ui_spec:
            return AgentResult(
                success=False,
                error_message="ui_spec.json not found",
                duration_seconds=time.time() - start_time,
            )

        screens = ui_spec.get("screens", [])
        components = ui_spec.get("components", [])
        comp_ids = {c.get("id", "") for c in components if isinstance(c, dict)}

        # Load user stories
        user_stories = self._load_json(output_dir / "user_stories.json", default=[])
        if isinstance(user_stories, dict):
            user_stories = user_stories.get("user_stories", user_stories.get("stories", []))
        story_ids = [s.get("id", "") for s in user_stories if isinstance(s, dict)]

        # Group issues by dimension
        issues_by_dim: Dict[str, List[Dict]] = {}
        for issue in issues:
            dim = issue.get("dimension", "unknown")
            issues_by_dim.setdefault(dim, []).append(issue)

        improvements_applied = []
        modified = False

        # Fix wireframe_quality issues (LLM)
        if "wireframe_quality" in issues_by_dim:
            fixed = await self._fix_wireframe_quality(
                screens, issues_by_dim["wireframe_quality"]
            )
            improvements_applied.extend(fixed)
            if fixed:
                modified = True

        # Fix component_coverage issues (programmatic)
        if "component_coverage" in issues_by_dim:
            fixed = self._fix_component_coverage(
                screens, issues_by_dim["component_coverage"], comp_ids
            )
            improvements_applied.extend(fixed)
            if fixed:
                modified = True

        # Fix story_coverage issues (programmatic)
        if "story_coverage" in issues_by_dim:
            fixed = self._fix_story_coverage(
                screens, issues_by_dim["story_coverage"], story_ids
            )
            improvements_applied.extend(fixed)
            if fixed:
                modified = True

        # Fix layout_coherence issues (programmatic)
        if "layout_coherence" in issues_by_dim:
            fixed = self._fix_layout_coherence(
                screens, issues_by_dim["layout_coherence"]
            )
            improvements_applied.extend(fixed)
            if fixed:
                modified = True

        # Fix data_completeness issues (LLM)
        if "data_completeness" in issues_by_dim:
            fixed = await self._fix_data_completeness(
                screens, issues_by_dim["data_completeness"]
            )
            improvements_applied.extend(fixed)
            if fixed:
                modified = True

        # Save updated ui_spec
        modified_files = []
        if modified:
            ui_spec["screens"] = screens
            ui_spec_path.write_text(
                json.dumps(ui_spec, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            modified_files.append(str(ui_spec_path))

            # Re-save screen markdown files
            screens_dir = output_dir / "ui_design" / "screens"
            screens_dir.mkdir(parents=True, exist_ok=True)
            for screen in screens:
                if isinstance(screen, dict):
                    md_path = screens_dir / f"screen-{screen.get('id', 'unknown').lower()}.md"
                    md_content = self._generate_screen_markdown(screen)
                    md_path.write_text(md_content, encoding="utf-8")
                    modified_files.append(str(md_path))

        duration = time.time() - start_time
        self._log_progress(
            f"Applied {len(improvements_applied)} improvements in {duration:.1f}s"
        )

        return AgentResult(
            success=True,
            modified_files=modified_files,
            improvements_applied=[
                {"description": imp} for imp in improvements_applied
            ],
            action_type="improve_screen",
            duration_seconds=duration,
            notes=f"Applied {len(improvements_applied)} fixes across {len(issues_by_dim)} dimensions",
        )

    # ================================================================
    # Dimension Fixers
    # ================================================================

    async def _fix_wireframe_quality(
        self, screens: List[Dict], issues: List[Dict]
    ) -> List[str]:
        """Fix wireframe issues via LLM regeneration."""
        fixed = []
        affected_ids = {iss.get("screen_id") for iss in issues}

        for screen in screens:
            if not isinstance(screen, dict):
                continue
            sid = screen.get("id", "")
            if sid not in affected_ids:
                continue

            # Build issues text for this screen
            screen_issues = [i for i in issues if i.get("screen_id") == sid]
            issues_text = "\n".join(f"- {i['description']}" for i in screen_issues)
            comp_text = "\n".join(f"- {cid}" for cid in screen.get("components", []))

            prompt = self.WIREFRAME_REGEN_PROMPT.format(
                screen_name=screen.get("name", sid),
                route=screen.get("route", "/"),
                layout=screen.get("layout", "default"),
                description=screen.get("description", ""),
                components_text=comp_text or "None",
                issues_text=issues_text,
                current_wireframe=screen.get("wireframe_ascii", "None"),
            )

            try:
                response = await self._call_llm(
                    system_prompt="You are a UI wireframe designer. Return ONLY ASCII wireframe text.",
                    user_prompt=prompt,
                )
                # Clean up response
                wireframe = response.strip()
                if wireframe.startswith("```"):
                    wireframe = re.sub(r"^```\w*\n?", "", wireframe)
                    wireframe = re.sub(r"\n?```$", "", wireframe)

                if wireframe and len(wireframe) > 30:
                    screen["wireframe_ascii"] = wireframe
                    fixed.append(f"Regenerated wireframe for {sid}")
            except Exception as e:
                self._log_error(f"Wireframe regen failed for {sid}: {e}")

        return fixed

    def _fix_component_coverage(
        self, screens: List[Dict], issues: List[Dict], valid_ids: Set[str]
    ) -> List[str]:
        """Remove invalid COMP-IDs from screens."""
        fixed = []
        affected_ids = {iss.get("screen_id") for iss in issues}

        for screen in screens:
            if not isinstance(screen, dict):
                continue
            sid = screen.get("id", "")
            if sid not in affected_ids:
                continue

            old_comps = screen.get("components", [])
            new_comps = [c for c in old_comps if c in valid_ids]

            if len(new_comps) < len(old_comps):
                removed = set(old_comps) - set(new_comps)
                screen["components"] = new_comps
                # Also clean up component_layout
                layout = screen.get("component_layout", [])
                screen["component_layout"] = [
                    cl for cl in layout
                    if isinstance(cl, dict) and cl.get("id", "") in valid_ids
                ]
                fixed.append(f"Removed invalid COMP-IDs from {sid}: {', '.join(removed)}")

        return fixed

    def _fix_story_coverage(
        self, screens: List[Dict], issues: List[Dict], story_ids: List[str]
    ) -> List[str]:
        """Set parent_user_story for screens that are missing it."""
        fixed = []
        affected_ids = {iss.get("screen_id") for iss in issues}
        story_index = 0

        for screen in screens:
            if not isinstance(screen, dict):
                continue
            sid = screen.get("id", "")
            if sid not in affected_ids:
                continue

            if not screen.get("parent_user_story") and story_ids:
                # Assign next available story
                screen["parent_user_story"] = story_ids[story_index % len(story_ids)]
                fixed.append(f"Set parent_user_story={screen['parent_user_story']} for {sid}")
                story_index += 1

        return fixed

    def _fix_layout_coherence(
        self, screens: List[Dict], issues: List[Dict]
    ) -> List[str]:
        """Fix missing coordinates and overlaps in component_layout."""
        fixed = []
        affected_ids = {iss.get("screen_id") for iss in issues}

        for screen in screens:
            if not isinstance(screen, dict):
                continue
            sid = screen.get("id", "")
            if sid not in affected_ids:
                continue

            layout = screen.get("component_layout", [])

            # Fix missing x,y,w,h
            y_cursor = 0
            for entry in layout:
                if not isinstance(entry, dict):
                    continue
                changed = False
                if "x" not in entry or not isinstance(entry.get("x"), (int, float)):
                    entry["x"] = 0
                    changed = True
                if "y" not in entry or not isinstance(entry.get("y"), (int, float)):
                    entry["y"] = y_cursor
                    changed = True
                if "w" not in entry or not isinstance(entry.get("w"), (int, float)):
                    entry["w"] = 60
                    changed = True
                if "h" not in entry or not isinstance(entry.get("h"), (int, float)):
                    entry["h"] = 4
                    changed = True
                y_cursor = int(entry.get("y", 0)) + int(entry.get("h", 4))
                if changed:
                    fixed.append(f"Added missing coords to {entry.get('id','?')} in {sid}")

            # Resolve true overlaps by stacking vertically (skip containment)
            rects = []
            for entry in layout:
                if not isinstance(entry, dict):
                    continue
                x, y = float(entry.get("x", 0)), float(entry.get("y", 0))
                w, h = float(entry.get("w", 0)), float(entry.get("h", 0))
                if w > 0 and h > 0:
                    for rid, rx, ry, rx2, ry2 in rects:
                        if x < rx2 and x + w > rx and y < ry2 and y + h > ry:
                            # Check containment - skip if one contains the other
                            a_contains_b = (rx <= x and ry <= y and rx2 >= x + w and ry2 >= y + h)
                            b_contains_a = (x <= rx and y <= ry and x + w >= rx2 and y + h >= ry2)
                            if a_contains_b or b_contains_a:
                                continue  # Parent-child, not a true overlap
                            # True overlap detected - push down
                            entry["y"] = int(ry2)
                            y = ry2
                            fixed.append(f"Moved {entry.get('id','?')} to y={int(ry2)} to resolve overlap in {sid}")
                            break
                    rects.append((entry.get("id", "?"), x, y, x + w, y + h))

            screen["component_layout"] = layout

        return fixed

    async def _fix_data_completeness(
        self, screens: List[Dict], issues: List[Dict]
    ) -> List[str]:
        """Fix empty data_requirements via LLM."""
        fixed = []
        affected_ids = {iss.get("screen_id") for iss in issues}

        for screen in screens:
            if not isinstance(screen, dict):
                continue
            sid = screen.get("id", "")
            if sid not in affected_ids:
                continue

            if screen.get("data_requirements"):
                continue  # Already has data, skip

            comp_text = ", ".join(screen.get("components", []))
            prompt = self.DATA_ENDPOINT_PROMPT.format(
                screen_name=screen.get("name", sid),
                route=screen.get("route", "/"),
                description=screen.get("description", ""),
                components_text=comp_text or "None",
            )

            try:
                response = await self._call_llm(
                    system_prompt="You are a backend API designer. Return ONLY a JSON array.",
                    user_prompt=prompt,
                )
                endpoints = self._parse_json_array(response)
                if endpoints:
                    screen["data_requirements"] = endpoints
                    fixed.append(f"Generated {len(endpoints)} endpoints for {sid}")
            except Exception as e:
                self._log_error(f"Endpoint generation failed for {sid}: {e}")

        return fixed

    # ================================================================
    # Helpers
    # ================================================================

    def _parse_json_array(self, text: str) -> Optional[List[str]]:
        """Parse a JSON array from LLM response."""
        text = text.strip()

        # Try direct parse
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return [str(item) for item in result]
        except json.JSONDecodeError:
            pass

        # Try fence extraction
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(1))
                if isinstance(result, list):
                    return [str(item) for item in result]
            except json.JSONDecodeError:
                pass

        # Try bracket matching
        start = text.find("[")
        if start >= 0:
            end = text.rfind("]")
            if end > start:
                try:
                    result = json.loads(text[start : end + 1])
                    if isinstance(result, list):
                        return [str(item) for item in result]
                except json.JSONDecodeError:
                    pass

        return None

    def _generate_screen_markdown(self, screen: Dict[str, Any]) -> str:
        """Generate markdown documentation for a screen."""
        md = f"""# {screen.get('name', 'Screen')}

**ID:** `{screen.get('id', '')}`
**Route:** `{screen.get('route', '/')}`
**Layout:** {screen.get('layout', 'default')}

{screen.get('description', '')}

---

## Components Used

"""
        for comp_id in screen.get("components", []):
            md += f"- `{comp_id}`\n"

        md += "\n---\n\n## Data Requirements\n\n"
        for endpoint in screen.get("data_requirements", []):
            md += f"- `{endpoint}`\n"

        if screen.get("parent_user_story"):
            md += f"\n---\n\n## Related User Story\n\n`{screen['parent_user_story']}`\n"

        md += "\n---\n\n## Wireframe\n\n"
        if screen.get("wireframe_ascii"):
            md += "```\n"
            md += screen["wireframe_ascii"]
            md += "\n```\n"
        else:
            md += "No wireframe generated.\n"

        if screen.get("component_layout"):
            md += "\n---\n\n## Component Layout\n\n"
            md += "| ID | Name | X | Y | W | H |\n"
            md += "|-----|------|---|---|---|---|\n"
            for cl in screen["component_layout"]:
                if isinstance(cl, dict):
                    md += f"| {cl.get('id','')} | {cl.get('name','')} | {cl.get('x','')} | {cl.get('y','')} | {cl.get('w','')} | {cl.get('h','')} |\n"

        return md

    def _load_json(self, path: Path, default: Any = None) -> Any:
        """Load a JSON file, returning default on failure."""
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            self._log_error(f"Failed to load {path}: {e}")
        return default if default is not None else {}
