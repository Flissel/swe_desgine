"""
Component Composition Generator - Maps UI components to screens and generates layouts.

This module takes the UI design system (components) and UX specification (navigation map)
and generates per-screen compositions showing which components appear on each screen,
their positions, props, responsive behavior, data sources, and state shape.
"""

import json
import re
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from dataclasses_json import dataclass_json
from openai import AsyncOpenAI

# Import LLM logger
from requirements_engineer.core.llm_logger import get_llm_logger, log_llm_call


@dataclass_json
@dataclass
class ComponentUsage:
    """A single component placement on a screen."""
    component_id: str  # COMP-001, etc.
    component_name: str
    props: Dict[str, Any] = field(default_factory=dict)
    position: str = ""  # header, main, footer, modal, sidebar
    responsive: Dict[str, str] = field(default_factory=dict)  # {mobile: "hidden", desktop: "visible"}


@dataclass_json
@dataclass
class ScreenComposition:
    """Composition of components for a single screen/route."""
    route: str  # /login, /chats/:id
    screen_name: str
    description: str = ""
    user_stories: List[str] = field(default_factory=list)  # linked US-* IDs
    components: List[ComponentUsage] = field(default_factory=list)
    layout: str = ""  # flexbox/grid description
    data_sources: List[str] = field(default_factory=list)  # API endpoints called
    state_shape: Dict[str, Any] = field(default_factory=dict)  # store slice shape


@dataclass_json
@dataclass
class ComponentMatrix:
    """Complete component-to-screen mapping matrix."""
    project_name: str
    screens: List[ScreenComposition] = field(default_factory=list)
    missing_components: List[str] = field(default_factory=list)
    component_usage_count: Dict[str, int] = field(default_factory=dict)


class ComponentCompositionGenerator:
    """Generates component-to-screen compositions using LLM."""

    COMPOSITION_PROMPT = """Du bist ein Senior Frontend Architect. Fuer den folgenden Screen musst du bestimmen, welche Komponenten verwendet werden, wo sie platziert werden, und wie der Layout aufgebaut ist.

## Screen: {screen_name}
## Route: {route}
## Beschreibung: {screen_description}

## Verfuegbare Komponenten (Design System):
{components_text}

## Zugehoerige User Stories:
{user_stories_text}

## Verfuegbare API Endpoints:
{api_endpoints_text}

Generiere eine Screen-Composition im folgenden JSON-Format:

{{
    "screen_name": "{screen_name}",
    "route": "{route}",
    "components": [
        {{
            "component_id": "COMP-001",
            "component_name": "ComponentName",
            "position": "header|main|footer|modal|sidebar",
            "props": {{"key": "value"}},
            "responsive": {{"mobile": "hidden|visible|stacked", "desktop": "visible"}}
        }}
    ],
    "layout": "flex column, centered, max-width 400px",
    "data_sources": ["GET /api/v1/resource", "POST /api/v1/resource"],
    "state_shape": {{"fieldName": "type"}},
    "missing_components": ["ComponentName die nicht im Design System existiert"]
}}

Beachte:
- Verwende NUR component_ids aus der verfuegbaren Komponenten-Liste
- Wenn eine Komponente benoetigt wird die nicht existiert, fuege sie zu "missing_components" hinzu
- Jede Komponente braucht eine klare Position (header, main, footer, modal, sidebar)
- Props muessen zum Komponenten-Typ passen
- data_sources: Welche API Endpoints ruft dieser Screen auf?
- state_shape: Welche Daten haelt dieser Screen im State?
- responsive: Wie verhält sich die Komponente auf verschiedenen Bildschirmgroessen?

Antworte NUR mit dem JSON-Objekt, keine zusaetzlichen Erklaerungen."""

    def __init__(
        self,
        model: str = None,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key: str = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the Component Composition Generator.

        Args:
            model: LLM model to use (overrides config)
            base_url: API base URL
            api_key: API key
            config: Configuration dict with generators.component_composition section
        """
        import os
        self.config = config or {}
        gen_config = self.config.get("generators", {}).get("component_composition", {})

        self.model = model or gen_config.get("model", "openai/gpt-4o-mini")
        self.temperature = gen_config.get("temperature", 0.5)
        self.max_tokens = gen_config.get("max_tokens", 4000)
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key or os.environ.get("OPENROUTER_API_KEY", ""))
        self._matrix: Optional[ComponentMatrix] = None

    async def initialize(self):
        """Initialize any async resources (placeholder for interface consistency)."""
        pass

    async def generate_compositions(
        self,
        ui_spec_dict: Dict[str, Any],
        ux_spec_dict: Dict[str, Any],
        user_stories: List[Any],
        api_endpoints: Optional[List[Any]] = None,
        project_name: str = ""
    ) -> ComponentMatrix:
        """
        Generate component-to-screen compositions.

        Args:
            ui_spec_dict: UI design spec dict (components, screens, etc.)
            ux_spec_dict: UX design spec dict (navigation_map, user_flows, etc.)
            user_stories: List of user story objects or dicts
            api_endpoints: Optional list of API endpoint objects or dicts
            project_name: Project name for labeling

        Returns:
            ComponentMatrix with all screen compositions
        """
        # 1. Extract navigation_map routes from ux_spec
        routes = self._extract_routes(ux_spec_dict)

        # 2. Extract available components from ui_spec
        available_components = self._extract_components(ui_spec_dict)

        # 3. For each route, LLM call to determine which components go on that screen
        compositions: List[ScreenComposition] = []
        all_missing: List[str] = []
        usage_count: Dict[str, int] = {}

        total = len(routes)
        for i, route_info in enumerate(routes, 1):
            route = route_info.get("path", route_info.get("route", "/"))
            screen_name = route_info.get("screen_name", route_info.get("name", f"Screen {i}"))
            screen_desc = route_info.get("description", "")

            print(f"    [{i}/{total}] Composing: {screen_name} ({route})...")

            # Match user stories to this screen
            matched_stories = self._match_user_stories(
                user_stories, screen_name, route
            )

            composition = await self._compose_screen(
                route=route,
                screen_name=screen_name,
                screen_description=screen_desc,
                available_components=available_components,
                matched_stories=matched_stories,
                api_endpoints=api_endpoints
            )

            if composition:
                compositions.append(composition)

                # Track missing components
                for mc in getattr(composition, '_screen_missing', []):
                    if mc not in all_missing:
                        all_missing.append(mc)

                # Track usage counts
                for cu in composition.components:
                    key = cu.component_id
                    usage_count[key] = usage_count.get(key, 0) + 1

        # 4. Build final matrix
        # Also check for referenced-but-missing components across all compositions
        known_ids = {c.get("id", "") for c in available_components}
        for comp in compositions:
            for cu in comp.components:
                if cu.component_id not in known_ids and cu.component_name not in all_missing:
                    all_missing.append(cu.component_name)

        matrix = ComponentMatrix(
            project_name=project_name,
            screens=compositions,
            missing_components=all_missing,
            component_usage_count=usage_count
        )
        self._matrix = matrix

        print(f"    Generated {len(compositions)} screen compositions, "
              f"{len(all_missing)} missing components")

        return matrix

    async def _compose_screen(
        self,
        route: str,
        screen_name: str,
        screen_description: str,
        available_components: List[Dict[str, Any]],
        matched_stories: List[Any],
        api_endpoints: Optional[List[Any]] = None
    ) -> Optional[ScreenComposition]:
        """Compose a single screen via LLM call."""

        # Build components text
        comp_lines = []
        for c in available_components:
            comp_id = c.get("id", "COMP-???")
            comp_name = c.get("name", "Unknown")
            comp_type = c.get("component_type", "custom")
            variants = ", ".join(c.get("variants", [])[:5])
            comp_lines.append(f"- {comp_id}: {comp_name} ({comp_type}) [Variants: {variants}]")
        components_text = "\n".join(comp_lines) if comp_lines else "Keine Komponenten verfuegbar"

        # Build user stories text
        story_lines = []
        story_ids = []
        for us in matched_stories[:10]:
            if hasattr(us, 'title'):
                us_id = getattr(us, 'id', getattr(us, 'story_id', 'US-???'))
                story_lines.append(f"- {us_id}: {us.title}")
                story_ids.append(str(us_id))
            elif isinstance(us, dict):
                us_id = us.get('id', us.get('story_id', 'US-???'))
                story_lines.append(f"- {us_id}: {us.get('title', 'Untitled')}")
                story_ids.append(str(us_id))
        user_stories_text = "\n".join(story_lines) if story_lines else "Keine zugehoerigen User Stories"

        # Build API endpoints text
        api_lines = []
        if api_endpoints:
            for ep in api_endpoints[:15]:
                if hasattr(ep, 'method'):
                    api_lines.append(f"- {ep.method} {ep.path}: {getattr(ep, 'summary', '')}")
                elif isinstance(ep, dict):
                    api_lines.append(f"- {ep.get('method', 'GET')} {ep.get('path', '/')}: {ep.get('summary', '')}")
        api_endpoints_text = "\n".join(api_lines) if api_lines else "Keine API Endpoints verfuegbar"

        prompt = self.COMPOSITION_PROMPT.format(
            screen_name=screen_name,
            route=route,
            screen_description=screen_description or f"Screen fuer {screen_name}",
            components_text=components_text,
            user_stories_text=user_stories_text,
            api_endpoints_text=api_endpoints_text
        )

        try:
            start_time = time.time()
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            latency_ms = int((time.time() - start_time) * 1000)

            content = response.choices[0].message.content.strip()

            # Log the LLM call
            log_llm_call(
                component="component_composition_generator",
                model=self.model,
                response=response,
                latency_ms=latency_ms,
                metadata={"method": "compose_screen", "route": route},
                user_message=prompt,
                response_text=content,
            )

            # Parse JSON with multi-strategy extraction
            data = self._parse_json(content)

            # Build ComponentUsage list
            comp_usages = []
            for c in data.get("components", []):
                usage = ComponentUsage(
                    component_id=c.get("component_id", ""),
                    component_name=c.get("component_name", ""),
                    props=c.get("props", {}),
                    position=c.get("position", "main"),
                    responsive=c.get("responsive", {})
                )
                comp_usages.append(usage)

            composition = ScreenComposition(
                route=route,
                screen_name=data.get("screen_name", screen_name),
                description=screen_description,
                user_stories=story_ids,
                components=comp_usages,
                layout=data.get("layout", ""),
                data_sources=data.get("data_sources", []),
                state_shape=data.get("state_shape", {})
            )

            # Attach missing components as temporary attribute for aggregation
            composition._screen_missing = data.get("missing_components", [])

            return composition

        except json.JSONDecodeError as e:
            print(f"    [WARN] Could not parse composition JSON for {screen_name}: {e}")
            return None
        except Exception as e:
            print(f"    [ERROR] Composition generation failed for {screen_name}: {e}")
            return None

    def _parse_json(self, content: str) -> Dict[str, Any]:
        """
        Parse JSON from LLM response with multi-strategy extraction.

        Strategies:
        1. Direct JSON parse
        2. Strip ```json ... ``` markdown fences
        3. Strip generic ``` ... ``` fences
        4. Regex bracket match for first { ... }
        """
        # Strategy 1: Direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Strategy 2: Markdown json fence
        if "```json" in content:
            try:
                extracted = content.split("```json")[1].split("```")[0].strip()
                return json.loads(extracted)
            except (json.JSONDecodeError, IndexError):
                pass

        # Strategy 3: Generic markdown fence
        if "```" in content:
            try:
                extracted = content.split("```")[1].split("```")[0].strip()
                return json.loads(extracted)
            except (json.JSONDecodeError, IndexError):
                pass

        # Strategy 4: Regex bracket match
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # All strategies failed
        raise json.JSONDecodeError("No valid JSON found in response", content, 0)

    def _extract_routes(self, ux_spec_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract routes/screens from UX specification."""
        routes = []

        # Try navigation_map first (Gap #12 format)
        nav_map = ux_spec_dict.get("navigation_map", [])
        if nav_map:
            for entry in nav_map:
                routes.append({
                    "path": entry.get("path", entry.get("route", "/")),
                    "screen_name": entry.get("screen_name", entry.get("name", "")),
                    "screen_id": entry.get("screen_id", ""),
                    "description": entry.get("description", ""),
                })
            return routes

        # Try information_architecture
        ia = ux_spec_dict.get("information_architecture", [])
        if ia:
            for node in ia:
                if isinstance(node, dict):
                    routes.append({
                        "path": node.get("path", node.get("route", "/")),
                        "screen_name": node.get("name", ""),
                        "description": node.get("description", ""),
                    })
                elif hasattr(node, 'path'):
                    routes.append({
                        "path": node.path,
                        "screen_name": getattr(node, 'name', ''),
                        "description": "",
                    })
            return routes

        # Try screens from ui_spec passed as ux (fallback)
        screens = ux_spec_dict.get("screens", [])
        for s in screens:
            if isinstance(s, dict):
                routes.append({
                    "path": s.get("route", "/"),
                    "screen_name": s.get("name", ""),
                    "description": s.get("description", ""),
                })

        return routes

    def _extract_components(self, ui_spec_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract available components from UI design specification."""
        components = ui_spec_dict.get("components", [])
        result = []
        for c in components:
            if isinstance(c, dict):
                result.append(c)
            elif hasattr(c, 'to_dict'):
                result.append(c.to_dict())
            elif hasattr(c, 'id'):
                result.append({
                    "id": c.id,
                    "name": getattr(c, 'name', ''),
                    "component_type": getattr(c, 'component_type', 'custom'),
                    "variants": getattr(c, 'variants', []),
                })
        return result

    def _match_user_stories(
        self,
        user_stories: List[Any],
        screen_name: str,
        route: str
    ) -> List[Any]:
        """Match user stories to a screen by keyword overlap."""
        screen_words = set(
            w.lower() for w in re.split(r'[\s/\-_:]+', f"{screen_name} {route}")
            if len(w) > 2
        )

        scored = []
        for us in user_stories:
            if hasattr(us, 'title'):
                title = us.title.lower()
                desc = getattr(us, 'description', '').lower()
            elif isinstance(us, dict):
                title = us.get('title', '').lower()
                desc = us.get('description', '').lower()
            else:
                continue

            story_words = set(
                w for w in re.split(r'[\s/\-_:]+', f"{title} {desc}")
                if len(w) > 2
            )
            overlap = len(screen_words & story_words)
            if overlap > 0:
                scored.append((overlap, us))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [us for _, us in scored[:10]]

    def to_markdown(self) -> str:
        """Generate markdown documentation from the last generated matrix."""
        if not self._matrix:
            return "# Component Compositions\n\nKeine Compositions generiert.\n"

        matrix = self._matrix
        md = f"# Component Compositions - {matrix.project_name}\n\n"

        md += "## Overview\n\n"
        md += f"| Property | Value |\n"
        md += f"|----------|-------|\n"
        md += f"| Screens | {len(matrix.screens)} |\n"
        md += f"| Missing Components | {len(matrix.missing_components)} |\n"
        md += f"| Unique Components Used | {len(matrix.component_usage_count)} |\n\n"

        # Usage count table
        if matrix.component_usage_count:
            md += "## Component Usage Frequency\n\n"
            md += "| Component ID | Usage Count |\n"
            md += "|-------------|-------------|\n"
            for comp_id, count in sorted(
                matrix.component_usage_count.items(),
                key=lambda x: x[1], reverse=True
            ):
                md += f"| `{comp_id}` | {count} |\n"
            md += "\n"

        # Missing components
        if matrix.missing_components:
            md += "## Missing Components\n\n"
            md += "Die folgenden Komponenten werden benoetigt, sind aber nicht im Design System definiert:\n\n"
            for mc in matrix.missing_components:
                md += f"- {mc}\n"
            md += "\n"

        # Per-screen compositions
        md += "---\n\n"
        for screen in matrix.screens:
            md += f"## {screen.screen_name}\n\n"
            md += f"**Route:** `{screen.route}`\n\n"
            if screen.description:
                md += f"{screen.description}\n\n"

            if screen.user_stories:
                md += f"**User Stories:** {', '.join(f'`{s}`' for s in screen.user_stories)}\n\n"

            if screen.layout:
                md += f"**Layout:** {screen.layout}\n\n"

            # Components table
            if screen.components:
                md += "### Components\n\n"
                md += "| Component | Position | Props | Responsive |\n"
                md += "|-----------|----------|-------|------------|\n"
                for cu in screen.components:
                    props_str = ", ".join(f"{k}={v}" for k, v in cu.props.items()) if cu.props else "-"
                    resp_str = ", ".join(f"{k}: {v}" for k, v in cu.responsive.items()) if cu.responsive else "-"
                    md += f"| `{cu.component_id}` {cu.component_name} | {cu.position} | {props_str} | {resp_str} |\n"
                md += "\n"

            # Data sources
            if screen.data_sources:
                md += "### Data Sources\n\n"
                for ds in screen.data_sources:
                    md += f"- `{ds}`\n"
                md += "\n"

            # State shape
            if screen.state_shape:
                md += "### State Shape\n\n```json\n"
                md += json.dumps(screen.state_shape, indent=2, ensure_ascii=False)
                md += "\n```\n\n"

            md += "---\n\n"

        return md


def save_compositions(matrix: ComponentMatrix, output_dir) -> None:
    """
    Save component compositions to files.

    Creates:
    - ui_design/compositions/<route>.json per screen
    - ui_design/compositions/component_matrix.md summary
    - ui_design/compositions/component_matrix.json full matrix
    """
    from pathlib import Path

    comp_dir = Path(output_dir) / "ui_design" / "compositions"
    comp_dir.mkdir(parents=True, exist_ok=True)

    # Save per-screen JSON files
    for screen in matrix.screens:
        # Sanitize route to filename
        filename = screen.route.strip("/").replace("/", "_").replace(":", "") or "index"
        filename = re.sub(r'[^a-zA-Z0-9_\-]', '', filename) or "screen"
        with open(comp_dir / f"{filename}.json", "w", encoding="utf-8") as f:
            json.dump(screen.to_dict(), f, indent=2, ensure_ascii=False)

    # Save component_matrix.md summary
    generator = ComponentCompositionGenerator.__new__(ComponentCompositionGenerator)
    generator._matrix = matrix
    md = generator.to_markdown()
    with open(comp_dir / "component_matrix.md", "w", encoding="utf-8") as f:
        f.write(md)

    # Save full matrix as JSON
    with open(comp_dir / "component_matrix.json", "w", encoding="utf-8") as f:
        json.dump(matrix.to_dict(), f, indent=2, ensure_ascii=False)
