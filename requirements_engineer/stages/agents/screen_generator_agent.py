"""
Screen Generator Agent for Multi-Agent Screen Design.

Generates screen specifications with ASCII wireframes from user stories,
component library, and information architecture nodes.

Uses robust 4-strategy JSON parsing to handle LLM output variations.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_presentation_agent import (
    AgentCapability,
    AgentResult,
    AgentRole,
    BasePresentationAgent,
    PresentationContext,
)

logger = logging.getLogger(__name__)


class ScreenGeneratorAgent(BasePresentationAgent):
    """
    Generates screen designs with ASCII wireframes from user stories.

    Reads user_stories.json, ui_spec.json (components), ux_spec.json (IA nodes)
    from the project directory. For each user story (up to max_screens),
    calls the LLM to produce a Screen JSON, then saves .md files and
    updates ui_spec.json.
    """

    SCREEN_PROMPT = """You are a UI designer. Create a screen specification based on the user story and available components.

## Project: {project_name}

## User Story:
{user_story_text}

## Information Architecture:
{ia_node_text}

## Available Components:
{components_text}

Create a screen specification in the following JSON format.
IMPORTANT: The "wireframe_ascii" field MUST contain a detailed ASCII-art wireframe of the screen!
The wireframe shows where each component is placed - with a coordinate grid.

{{
    "name": "Invoice List",
    "route": "/invoices",
    "layout": "sidebar",
    "description": "Overview of all invoices with filter and search",
    "components": ["COMP-001", "COMP-002", "COMP-005"],
    "component_layout": [
        {{"id": "COMP-001", "name": "NavBar", "x": 0, "y": 0, "w": 60, "h": 4}},
        {{"id": "COMP-002", "name": "SideFilter", "x": 0, "y": 4, "w": 15, "h": 20}},
        {{"id": "COMP-005", "name": "DataTable", "x": 16, "y": 4, "w": 44, "h": 20}}
    ],
    "data_requirements": [
        "GET /api/invoices",
        "GET /api/invoices/{{id}}"
    ],
    "wireframe_ascii": "     0    5   10   15   20   25   30   35   40   45   50   55   60\\n   0 +------------------------------------------------------------+\\n     |  [Logo]        [NavBar: Home | Invoices | Settings]     |\\n   2 |  COMP-001                                                |\\n     +------------------------------------------------------------+\\n   4 | [SideFilter] |  [SearchInput]              [+NewBtn]     |\\n     | COMP-002     |                                           |\\n   6 | [x] Status   |  +---------------------------------------+|\\n     | [x] Date     |  | ID  | Customer | Amount | Status| Act ||\\n   8 | [x] Amount   |  |-----|----------|--------|-------|-----||\\n     |              |  | 001 | Acme Inc | 1,200  | Open  | ... ||\\n  10 | [DateRange]  |  | 002 | Beta Ltd | 3,400  | Paid  | ... ||\\n     |              |  | 003 | Gamma Co |   890  | Open  | ... ||\\n  12 |              |  |     COMP-005 (DataTable)          | ... ||\\n     |              |  +---------------------------------------+|\\n  14 +--------------+-------------------------------------------+\\n     |                    [Pagination: < 1 2 3 >]               |\\n  16 +------------------------------------------------------------+"
}}

The ASCII wireframe MUST:
- Show a coordinate grid at the edges (X on top, Y on left) for reading positions
- Clearly mark each component with [ComponentName] and COMP-ID
- Show the page structure with +, |, - characters
- Show column layouts (sidebar, split) clearly
- Be 60 characters wide for desktop representation
- All component IDs referenced in "components" must appear in the wireframe

The "component_layout" array MUST:
- Include x, y position (in grid units) and w, h size for each component
- Values must match the ASCII wireframe

Reply ONLY with the JSON object."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.max_screens = cfg.get("max_screens", 8)
        super().__init__(
            name="ScreenGenerator",
            role=AgentRole.SCREEN_GENERATOR,
            description="Generates screen designs with ASCII wireframes from user stories",
            capabilities=[
                AgentCapability.SCREEN_GENERATION,
                AgentCapability.HTML_GENERATION,
            ],
            config=cfg,
        )

    async def execute(self, context: PresentationContext) -> AgentResult:
        """Generate screens from user stories + component library."""
        start_time = time.time()
        self._log_progress("Starting screen generation")

        output_dir = Path(context.output_dir)

        # Load artifacts
        user_stories = self._load_json(output_dir / "user_stories.json", default=[])
        if isinstance(user_stories, dict):
            user_stories = user_stories.get("user_stories", user_stories.get("stories", []))

        ui_spec = self._load_json(output_dir / "ui_design" / "ui_spec.json", default={})
        components = ui_spec.get("components", [])

        ux_spec = self._load_json(output_dir / "ux_design" / "ux_spec.json", default={})
        ia_nodes = ux_spec.get("information_architecture", [])

        if not user_stories:
            return AgentResult(
                success=False,
                error_message="No user_stories.json found or empty",
                duration_seconds=time.time() - start_time,
            )

        self._log_progress(
            f"Found {len(user_stories)} stories, {len(components)} components, {len(ia_nodes)} IA nodes"
        )

        # Determine project name
        project_name = ui_spec.get("project_name", context.project_id or "Project")

        # Generate screens
        screens = []
        generated_files = []
        screen_counter = len(ui_spec.get("screens", []))

        screens_dir = output_dir / "ui_design" / "screens"
        screens_dir.mkdir(parents=True, exist_ok=True)

        # Gap #10: Use diversity selection instead of sequential slice
        diverse_stories = self._select_diverse_stories(user_stories, self.max_screens)
        for i, story in enumerate(diverse_stories):
            ia_node = ia_nodes[i] if i < len(ia_nodes) else None
            story_title = story.get("title", story.get("name", f"Story {i+1}")) if isinstance(story, dict) else str(story)
            self._log_progress(f"[{i+1}/{len(diverse_stories)}] Screen for: {story_title}")

            screen_data = await self._generate_single_screen(
                project_name=project_name,
                user_story=story,
                ia_node=ia_node,
                components=components,
                screen_index=screen_counter + i + 1,
            )

            if screen_data:
                screens.append(screen_data)
                # Save screen markdown
                md_path = screens_dir / f"screen-{screen_data['id'].lower()}.md"
                md_content = self._generate_screen_markdown(screen_data)
                md_path.write_text(md_content, encoding="utf-8")
                generated_files.append(str(md_path))

        # Update ui_spec.json with new screens
        if screens:
            existing_screens = ui_spec.get("screens", [])
            ui_spec["screens"] = existing_screens + screens
            ui_spec_path = output_dir / "ui_design" / "ui_spec.json"
            ui_spec_path.write_text(
                json.dumps(ui_spec, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            generated_files.append(str(ui_spec_path))

        duration = time.time() - start_time
        self._log_progress(f"Generated {len(screens)} screens in {duration:.1f}s")

        return AgentResult(
            success=len(screens) > 0,
            error_message="" if screens else "No screens could be generated",
            generated_files=generated_files,
            quality_score=len(screens) / max(len(diverse_stories), 1),
            action_type="generate_screen",
            duration_seconds=duration,
            notes=f"Generated {len(screens)} screens from {len(user_stories)} stories",
            needs_review=True,
        )

    @staticmethod
    def _select_diverse_stories(stories: list, max_screens: int) -> list:
        """Select stories covering different functional areas (Gap #10)."""
        if len(stories) <= max_screens:
            return list(stories)

        CATEGORY_KEYWORDS = {
            "auth": ["login", "register", "password", "auth", "2fa", "passkey", "signup"],
            "messaging": ["message", "chat", "send", "receive", "group", "conversation"],
            "profile": ["profile", "status", "picture", "about", "avatar", "account"],
            "settings": ["setting", "preference", "config", "notification", "privacy"],
            "media": ["photo", "video", "image", "media", "upload", "gallery", "camera"],
            "contacts": ["contact", "friend", "block", "invite", "address"],
            "calls": ["call", "voice", "ring", "dial", "audio"],
            "search": ["search", "find", "discover", "filter", "browse"],
        }

        categories: dict = {k: [] for k in CATEGORY_KEYWORDS}
        categories["other"] = []

        for story in stories:
            title = (story.get("title", "") if isinstance(story, dict) else str(story)).lower()
            placed = False
            for cat, keywords in CATEGORY_KEYWORDS.items():
                if any(kw in title for kw in keywords):
                    categories[cat].append(story)
                    placed = True
                    break
            if not placed:
                categories["other"].append(story)

        result = []
        non_empty = {k: v for k, v in categories.items() if v}
        idx = {k: 0 for k in non_empty}

        while len(result) < max_screens:
            added = False
            for cat in list(non_empty.keys()):
                if len(result) >= max_screens:
                    break
                if idx[cat] < len(non_empty[cat]):
                    result.append(non_empty[cat][idx[cat]])
                    idx[cat] += 1
                    added = True
            if not added:
                break

        return result

    async def _generate_single_screen(
        self,
        project_name: str,
        user_story: Any,
        ia_node: Any,
        components: List[Dict],
        screen_index: int,
    ) -> Optional[Dict[str, Any]]:
        """Generate a single screen specification via LLM."""
        # Build user story text
        if isinstance(user_story, dict):
            us_text = f"{user_story.get('id', 'US')}: {user_story.get('title', 'Story')}"
            if user_story.get("description"):
                us_text += f"\n{user_story['description']}"
            if user_story.get("action"):
                us_text += f"\nAction: {user_story['action']}"
        else:
            us_text = str(user_story)

        # Build IA node text
        if isinstance(ia_node, dict):
            ia_text = f"{ia_node.get('name', 'Page')} ({ia_node.get('path', '/')})"
            if ia_node.get("content_types"):
                ia_text += f"\nContent: {', '.join(ia_node['content_types'])}"
        elif ia_node is not None:
            ia_text = str(ia_node)
        else:
            ia_text = "Dashboard / Main View"

        # Build components text
        comp_text = "\n".join(
            f"- {c.get('id', 'COMP')}: {c.get('name', 'Component')} ({c.get('component_type', 'custom')})"
            for c in components[:12]
        )

        prompt = self.SCREEN_PROMPT.format(
            project_name=project_name,
            user_story_text=us_text,
            ia_node_text=ia_text,
            components_text=comp_text or "No components defined yet",
        )

        for attempt in range(3):
            try:
                response = await self._call_llm(
                    system_prompt="You are a UI designer. Return ONLY valid JSON.",
                    user_prompt=prompt,
                )

                data = self._parse_json_robust(response)
                if data is None:
                    self._log_error(f"Attempt {attempt+1}: JSON parse failed")
                    continue

                # Build screen dict
                screen_id = f"SCREEN-{screen_index:03d}"
                story_id = ""
                if isinstance(user_story, dict):
                    story_id = user_story.get("id", "")

                ascii_wireframe = data.get("wireframe_ascii", "")
                if ascii_wireframe:
                    ascii_wireframe = ascii_wireframe.replace("\\n", "\n")

                screen = {
                    "id": screen_id,
                    "name": data.get("name", f"Screen {screen_index}"),
                    "route": data.get("route", f"/screen-{screen_index}"),
                    "layout": data.get("layout", "default"),
                    "description": data.get("description", ""),
                    "components": data.get("components", []),
                    "component_layout": data.get("component_layout", []),
                    "data_requirements": data.get("data_requirements", []),
                    "parent_user_story": story_id,
                    "wireframe_ascii": ascii_wireframe,
                    "wireframe_mermaid": "",
                }

                return screen

            except Exception as e:
                self._log_error(f"Attempt {attempt+1}: {type(e).__name__}: {e}")

        return None

    def _parse_json_robust(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Parse JSON from LLM response with 4 fallback strategies.

        1. Direct parse
        2. Markdown json fence extraction
        3. Generic fence extraction
        4. Bracket matching
        """
        if not text or not text.strip():
            return None

        text = text.strip()

        # Strategy 1: Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Strategy 2: ```json ... ``` fence
        match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Strategy 3: Generic ``` fence
        match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Strategy 4: Find outermost { ... }
        start = text.find("{")
        if start >= 0:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start : i + 1])
                        except json.JSONDecodeError:
                            break

        return None

    def _generate_screen_markdown(self, screen: Dict[str, Any]) -> str:
        """Generate markdown documentation for a screen."""
        md = f"""# {screen['name']}

**ID:** `{screen['id']}`
**Route:** `{screen['route']}`
**Layout:** {screen['layout']}

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
