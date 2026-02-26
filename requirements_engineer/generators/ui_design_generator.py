"""
UI Design Generator - Generates User Interface design specifications.

This module creates UI artifacts including design system tokens, component library,
screen specifications, and responsive design guidelines.
"""

import json
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from dataclasses_json import dataclass_json
from openai import AsyncOpenAI

# Import LLM logger
from requirements_engineer.core.llm_logger import get_llm_logger, log_llm_call


@dataclass_json
@dataclass
class DesignTokens:
    """Design system tokens (colors, typography, spacing, etc.)."""

    # Colors
    colors: Dict[str, str] = field(default_factory=lambda: {
        "primary": "#3B82F6",
        "primary-dark": "#2563EB",
        "primary-light": "#60A5FA",
        "secondary": "#10B981",
        "background": "#FFFFFF",
        "surface": "#F3F4F6",
        "text-primary": "#111827",
        "text-secondary": "#6B7280",
        "error": "#EF4444",
        "warning": "#F59E0B",
        "success": "#10B981",
        "info": "#3B82F6"
    })

    # Typography
    typography: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {
        "font-family": {"base": "Inter, system-ui, sans-serif", "mono": "JetBrains Mono, monospace"},
        "h1": {"size": "2.5rem", "weight": "700", "line-height": "1.2"},
        "h2": {"size": "2rem", "weight": "600", "line-height": "1.25"},
        "h3": {"size": "1.5rem", "weight": "600", "line-height": "1.3"},
        "h4": {"size": "1.25rem", "weight": "600", "line-height": "1.4"},
        "body": {"size": "1rem", "weight": "400", "line-height": "1.5"},
        "body-small": {"size": "0.875rem", "weight": "400", "line-height": "1.5"},
        "caption": {"size": "0.75rem", "weight": "400", "line-height": "1.4"}
    })

    # Spacing
    spacing: Dict[str, str] = field(default_factory=lambda: {
        "xs": "0.25rem",
        "sm": "0.5rem",
        "md": "1rem",
        "lg": "1.5rem",
        "xl": "2rem",
        "2xl": "3rem",
        "3xl": "4rem"
    })

    # Breakpoints
    breakpoints: Dict[str, int] = field(default_factory=lambda: {
        "mobile": 320,
        "mobile-lg": 480,
        "tablet": 768,
        "desktop": 1024,
        "desktop-lg": 1280,
        "desktop-xl": 1536
    })

    # Shadows
    shadows: Dict[str, str] = field(default_factory=lambda: {
        "sm": "0 1px 2px rgba(0, 0, 0, 0.05)",
        "md": "0 4px 6px rgba(0, 0, 0, 0.1)",
        "lg": "0 10px 15px rgba(0, 0, 0, 0.1)",
        "xl": "0 20px 25px rgba(0, 0, 0, 0.15)"
    })

    # Border radius
    border_radius: Dict[str, str] = field(default_factory=lambda: {
        "none": "0",
        "sm": "0.125rem",
        "md": "0.375rem",
        "lg": "0.5rem",
        "xl": "0.75rem",
        "full": "9999px"
    })


@dataclass_json
@dataclass
class UIComponent:
    """UI component specification."""
    id: str
    name: str
    component_type: str  # button, input, card, modal, table, etc.
    description: str = ""
    variants: List[str] = field(default_factory=list)
    props: Dict[str, str] = field(default_factory=dict)
    states: List[str] = field(default_factory=list)
    accessibility: Dict[str, str] = field(default_factory=dict)
    example_usage: str = ""
    # Relationships for Dashboard linking
    parent_screen_ids: List[str] = field(default_factory=list)  # Screens that use this component
    source_user_story_id: str = ""  # User story that requires this component


@dataclass_json
@dataclass
class Screen:
    """Screen/page specification."""
    id: str
    name: str
    route: str
    layout: str = "default"  # sidebar, fullwidth, split, dashboard
    description: str = ""
    components: List[str] = field(default_factory=list)  # Component IDs
    component_layout: List[Dict] = field(default_factory=list)  # [{id, name, x, y, w, h}]
    data_requirements: List[str] = field(default_factory=list)  # API endpoints
    parent_user_story: str = ""
    wireframe_mermaid: str = ""
    wireframe_ascii: str = ""  # ASCII-Art wireframe with coordinate grid
    # Gap #11: State-to-component bindings (e.g. {"COMP-001": "auth.phoneNumber"})
    state_bindings: Dict[str, str] = field(default_factory=dict)
    # Gap #12: Navigation rules (e.g. [{"trigger": "submit_success", "target": "/dashboard"}])
    navigation_rules: List[Dict] = field(default_factory=list)
    # Gap #20: Responsive layout overrides per breakpoint
    responsive: Dict[str, Dict] = field(default_factory=dict)
    # Auth requirement for this screen
    auth_required: bool = True


@dataclass_json
@dataclass
class UIDesignSpec:
    """Complete UI design specification."""
    project_name: str
    design_tokens: DesignTokens = field(default_factory=DesignTokens)
    components: List[UIComponent] = field(default_factory=list)
    screens: List[Screen] = field(default_factory=list)
    responsive_strategy: str = "mobile-first"
    theme_support: bool = True
    dark_mode: bool = True
    # Gap #12: Global navigation map (routes + transitions)
    navigation_map: List[Dict] = field(default_factory=list)
    # Gap #11: State architecture (Redux slices / Zustand stores)
    state_architecture: Dict[str, Any] = field(default_factory=dict)


class UIDesignGenerator:
    """Generates UI design specifications from UX spec and requirements."""

    COMPONENT_PROMPT = """Du bist ein UI/UX Designer. Erstelle eine Component Library basierend auf den Screens und User Flows.

## Projekt: {project_name}

## Screens:
{screens_text}

## User Flows:
{flows_text}

Erstelle UI-Komponenten im folgenden JSON-Format:

{{
    "components": [
        {{
            "id": "COMP-001",
            "name": "Button",
            "component_type": "button",
            "description": "Primary action button component",
            "variants": ["primary", "secondary", "outline", "ghost", "danger"],
            "props": {{
                "size": "sm | md | lg",
                "disabled": "boolean",
                "loading": "boolean",
                "icon": "ReactNode (optional)",
                "onClick": "() => void"
            }},
            "states": ["default", "hover", "active", "focus", "disabled", "loading"],
            "accessibility": {{
                "role": "button",
                "aria-label": "Required for icon-only buttons",
                "aria-disabled": "When disabled"
            }},
            "example_usage": "<Button variant='primary' size='md'>Save</Button>"
        }},
        {{
            "id": "COMP-002",
            "name": "DataTable",
            "component_type": "table",
            "description": "Sortable, filterable data table",
            "variants": ["default", "compact", "striped"],
            "props": {{
                "columns": "Column[]",
                "data": "T[]",
                "sortable": "boolean",
                "filterable": "boolean",
                "pagination": "boolean"
            }},
            "states": ["loading", "empty", "error"],
            "accessibility": {{
                "role": "table",
                "aria-label": "Table description required"
            }},
            "example_usage": "<DataTable columns={{cols}} data={{rows}} sortable />"
        }}
    ]
}}

Erstelle 8-12 wichtige Komponenten die fuer die Screens benoetigt werden.
Antworte NUR mit dem JSON-Objekt."""

    SCREEN_PROMPT = """Du bist ein UI Designer. Erstelle Screen-Spezifikationen basierend auf den User Stories und IA.

## Projekt: {project_name}

## User Story:
{user_story_text}

## Information Architecture Node:
{ia_node_text}

## Verfuegbare Komponenten:
{components_text}

Erstelle eine Screen-Spezifikation im folgenden JSON-Format.
WICHTIG: Das "wireframe_ascii" Feld MUSS ein detailliertes ASCII-Art Wireframe des Screens enthalten!
Das Wireframe zeigt wo welche Komponente liegt - mit Koordinaten-Raster.

{{
    "name": "Invoice List",
    "route": "/invoices",
    "layout": "sidebar",
    "description": "Uebersicht aller Rechnungen mit Filter und Suche",
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
    "wireframe_ascii": "     0    5   10   15   20   25   30   35   40   45   50   55   60\\n   0 +------------------------------------------------------------+\\n     |  [Logo]        [NavBar: Home | Invoices | Settings]     |\\n   2 |  COMP-001                                                |\\n     +------------------------------------------------------------+\\n   4 | [SideFilter] |  [SearchInput]              [+NewBtn]     |\\n     | COMP-002     |                                           |\\n   6 | [x] Status   |  +---------------------------------------+|\\n     | [x] Date     |  | ID  | Kunde  | Betrag | Status | Akt ||\\n   8 | [x] Amount   |  |-----|--------|--------|--------|-----||\\n     |              |  | 001 | Firma A| 1.200  | Offen  | ... ||\\n  10 | [DateRange]  |  | 002 | Firma B| 3.400  | Bezahlt| ... ||\\n     |              |  | 003 | Firma C|   890  | Offen  | ... ||\\n  12 |              |  |     COMP-005 (DataTable)         | ... ||\\n     |              |  +---------------------------------------+|\\n  14 +--------------+-------------------------------------------+\\n     |                    [Pagination: < 1 2 3 >]               |\\n  16 +------------------------------------------------------------+",
    "state_bindings": {{"COMP-002": "invoices.filters", "COMP-005": "invoices.list"}},
    "navigation_rules": [
        {{"trigger": "row_click", "target": "/invoices/{{id}}", "condition": ""}},
        {{"trigger": "new_btn_click", "target": "/invoices/new", "condition": "user.canCreate"}}
    ],
    "auth_required": true,
    "responsive": {{
        "mobile": {{"layout": "stack", "hidden_components": ["COMP-002"]}},
        "tablet": {{"layout": "sidebar-collapsed"}},
        "desktop": {{"layout": "sidebar"}}
    }}
}}

Das ASCII-Wireframe MUSS:
- Koordinaten-Raster am Rand zeigen (X oben, Y links) damit man Positionen ablesen kann
- Jede Komponente klar markieren mit [KomponentenName] und COMP-ID
- Die Seitenstruktur mit +, |, - Zeichen zeigen
- Spalten-Layout (sidebar, split) klar darstellen
- 60 Zeichen breit sein fuer Desktop-Darstellung
- Alle in "components" referenzierten Component-IDs muessen im Wireframe vorkommen

Das "component_layout" Array MUSS:
- Fuer jede Komponente x,y Position (in Raster-Einheiten) und w,h Groesse angeben
- Die Werte muessen zum ASCII-Wireframe passen

Antworte NUR mit dem JSON-Objekt."""

    DESIGN_TOKENS_PROMPT = """Du bist ein UI Designer. Erstelle Design Tokens basierend auf dem Projekt-Domain und Requirements.

## Projekt: {project_name}
## Domain: {domain}

## Kontext:
{context}

Erstelle passende Design Tokens im folgenden JSON-Format:

{{
    "colors": {{
        "primary": "#hex",
        "primary-dark": "#hex",
        "primary-light": "#hex",
        "secondary": "#hex",
        "background": "#hex",
        "surface": "#hex",
        "text-primary": "#hex",
        "text-secondary": "#hex",
        "error": "#hex",
        "warning": "#hex",
        "success": "#hex",
        "info": "#hex"
    }},
    "typography": {{
        "font-family": {{"base": "Font, fallback", "mono": "MonoFont, fallback"}},
        "h1": {{"size": "2.5rem", "weight": "700", "line-height": "1.2"}},
        "body": {{"size": "1rem", "weight": "400", "line-height": "1.5"}}
    }},
    "spacing": {{
        "xs": "0.25rem",
        "sm": "0.5rem",
        "md": "1rem",
        "lg": "1.5rem",
        "xl": "2rem"
    }},
    "border_radius": {{
        "sm": "0.125rem",
        "md": "0.375rem",
        "lg": "0.5rem"
    }}
}}

Wähle Farben die zur Domain passen:
- Finance/Billing: Professionell, Blau/Grau
- Healthcare: Vertrauenswuerdig, Blau/Gruen
- E-Commerce: Modern, je nach Marke

Antworte NUR mit dem JSON-Objekt."""

    def __init__(
        self,
        model: str = None,
        screen_model: str = None,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key: str = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the UI Design Generator.

        Args:
            model: LLM model to use for components/tokens (overrides config)
            screen_model: Separate LLM model for screen generation (can be stronger)
            base_url: API base URL
            api_key: API key
            config: Configuration dict with generators.ui_design section
        """
        import os
        self.config = config or {}
        gen_config = self.config.get("generators", {}).get("ui_design", {})

        self.model = model or gen_config.get("model", "openai/gpt-4o-mini")
        # Screen generation is more complex - allow separate (stronger) model
        self.screen_model = screen_model or gen_config.get("screen_model", self.model)
        self.temperature = gen_config.get("temperature", 0.6)
        self.max_tokens = gen_config.get("max_tokens", 8000)
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key or os.environ.get("OPENROUTER_API_KEY"))
        self.component_counter = 0
        self.screen_counter = 0

    async def generate_design_tokens(
        self,
        project_name: str,
        domain: str,
        context: str = ""
    ) -> DesignTokens:
        """Generate design tokens based on project domain."""

        prompt = self.DESIGN_TOKENS_PROMPT.format(
            project_name=project_name,
            domain=domain,
            context=context or f"Professional {domain} application"
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
                component="ui_design_generator",
                model=self.model,
                response=response,
                latency_ms=latency_ms,
                metadata={"method": "generate_design_tokens"},
                user_message=prompt,
                response_text=content,
            )

            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            data = json.loads(content)

            tokens = DesignTokens()
            if "colors" in data:
                tokens.colors.update(data["colors"])
            if "typography" in data:
                tokens.typography.update(data["typography"])
            if "spacing" in data:
                tokens.spacing.update(data["spacing"])
            if "border_radius" in data:
                tokens.border_radius.update(data["border_radius"])

            return tokens

        except Exception as e:
            print(f"    [WARN] Design tokens generation failed: {e}")
            return DesignTokens()

    async def generate_components(
        self,
        project_name: str,
        screens_info: List[Dict],
        flows_info: List[Dict]
    ) -> List[UIComponent]:
        """Generate component library based on screens and flows."""

        # Build screens text
        screens_text = "\n".join([
            f"- {s.get('name', 'Screen')}: {s.get('description', '')}"
            for s in screens_info[:10]
        ]) if screens_info else "Dashboard, Listen, Formulare"

        # Build flows text
        flows_text = "\n".join([
            f"- {f.get('name', 'Flow')}: {f.get('description', '')}"
            for f in flows_info[:5]
        ]) if flows_info else "Standard CRUD Flows"

        prompt = self.COMPONENT_PROMPT.format(
            project_name=project_name,
            screens_text=screens_text,
            flows_text=flows_text
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
                component="ui_design_generator",
                model=self.model,
                response=response,
                latency_ms=latency_ms,
                metadata={"method": "generate_components"},
                user_message=prompt,
                response_text=content,
            )

            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            data = json.loads(content)
            components = []

            for c in data.get("components", []):
                self.component_counter += 1
                comp = UIComponent(
                    id=f"COMP-{self.component_counter:03d}",
                    name=c.get("name", f"Component {self.component_counter}"),
                    component_type=c.get("component_type", "custom"),
                    description=c.get("description", ""),
                    variants=c.get("variants", []),
                    props=c.get("props", {}),
                    states=c.get("states", []),
                    accessibility=c.get("accessibility", {}),
                    example_usage=c.get("example_usage", "")
                )
                components.append(comp)

            return components

        except Exception as e:
            print(f"    [WARN] Component generation failed: {e}")
            return self._get_default_components()

    def _get_default_components(self) -> List[UIComponent]:
        """Return default component library."""
        defaults = [
            UIComponent(id="COMP-001", name="Button", component_type="button",
                       variants=["primary", "secondary", "outline"],
                       states=["default", "hover", "active", "disabled"]),
            UIComponent(id="COMP-002", name="Input", component_type="input",
                       variants=["text", "email", "password", "search"],
                       states=["default", "focus", "error", "disabled"]),
            UIComponent(id="COMP-003", name="Card", component_type="card",
                       variants=["default", "elevated", "outlined"]),
            UIComponent(id="COMP-004", name="Modal", component_type="modal",
                       variants=["default", "fullscreen", "drawer"]),
            UIComponent(id="COMP-005", name="DataTable", component_type="table",
                       variants=["default", "compact", "striped"]),
            UIComponent(id="COMP-006", name="Select", component_type="dropdown",
                       variants=["single", "multi", "searchable"]),
            UIComponent(id="COMP-007", name="Tabs", component_type="navigation",
                       variants=["default", "pills", "underline"]),
            UIComponent(id="COMP-008", name="Alert", component_type="feedback",
                       variants=["info", "success", "warning", "error"]),
        ]
        return defaults

    async def generate_screen(
        self,
        project_name: str,
        user_story: Any,
        ia_node: Any,
        components: List[UIComponent]
    ) -> Optional[Screen]:
        """Generate screen specification with retry logic."""
        import traceback

        MAX_RETRIES = 2

        # Build user story text
        if hasattr(user_story, 'title'):
            us_text = f"{user_story.id}: {user_story.title}\n{user_story.action if hasattr(user_story, 'action') else ''}"
        elif isinstance(user_story, dict):
            us_text = f"{user_story.get('id', 'US')}: {user_story.get('title', 'Story')}"
        else:
            us_text = str(user_story)

        # Build IA node text
        if hasattr(ia_node, 'name'):
            ia_text = f"{ia_node.name} ({ia_node.path})\nContent: {', '.join(ia_node.content_types)}"
        elif isinstance(ia_node, dict):
            ia_text = f"{ia_node.get('name', 'Page')} ({ia_node.get('path', '/')})"
        else:
            ia_text = str(ia_node) if ia_node else "Dashboard"

        # Build components text
        comp_text = "\n".join([f"- {c.id}: {c.name} ({c.component_type})" for c in components[:10]])

        prompt = self.SCREEN_PROMPT.format(
            project_name=project_name,
            user_story_text=us_text,
            ia_node_text=ia_text,
            components_text=comp_text
        )

        content = ""  # Track raw response for error reporting

        for attempt in range(MAX_RETRIES + 1):
            try:
                start_time = time.time()
                # Use screen_model (can be stronger than default model)
                # Lower temperature on retry for more deterministic output
                current_temp = 0.4 if attempt > 0 else self.temperature

                response = await self.client.chat.completions.create(
                    model=self.screen_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=current_temp,
                    max_tokens=self.max_tokens
                )
                latency_ms = int((time.time() - start_time) * 1000)

                content = response.choices[0].message.content.strip()

                # Log the LLM call
                log_llm_call(
                    component="ui_design_generator",
                    model=self.screen_model,
                    response=response,
                    latency_ms=latency_ms,
                    metadata={"method": "generate_screen", "attempt": attempt + 1},
                    user_message=prompt,
                    response_text=content,
                )

                # Extract JSON
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()

                data = json.loads(content)
                self.screen_counter += 1

                # Get ASCII wireframe from LLM response, or generate fallback
                ascii_wireframe = data.get("wireframe_ascii", "")
                if ascii_wireframe:
                    # Ensure proper line breaks (LLM might escape them)
                    ascii_wireframe = ascii_wireframe.replace("\\n", "\n")

                screen = Screen(
                    id=f"SCREEN-{self.screen_counter:03d}",
                    name=data.get("name", f"Screen {self.screen_counter}"),
                    route=data.get("route", f"/screen-{self.screen_counter}"),
                    layout=data.get("layout", "default"),
                    description=data.get("description", ""),
                    components=data.get("components", []),
                    component_layout=data.get("component_layout", []),
                    data_requirements=data.get("data_requirements", []),
                    parent_user_story=getattr(user_story, 'id', user_story.get('id', '')) if hasattr(user_story, 'id') or isinstance(user_story, dict) else "",
                    wireframe_mermaid=self._generate_wireframe(data.get("name", "Screen"), data.get("wireframe_description", "")),
                    wireframe_ascii=ascii_wireframe,
                    # Gap #11: State bindings
                    state_bindings=data.get("state_bindings", {}),
                    # Gap #12: Navigation rules
                    navigation_rules=data.get("navigation_rules", []),
                    # Gap #20: Responsive layout overrides
                    responsive=data.get("responsive", {}),
                    auth_required=data.get("auth_required", True),
                )

                return screen

            except json.JSONDecodeError as e:
                print(f"    [WARN] Attempt {attempt+1}/{MAX_RETRIES+1}: JSON parse error - {e}")
                if attempt == MAX_RETRIES:
                    print(f"    [ERROR] Screen JSON parse failed after {MAX_RETRIES+1} attempts!")
                    print(f"    [ERROR] Raw LLM response:\n{content[:500]}...")
                    print(f"    [DEBUG] User Story: {us_text[:100]}")
                    return None

            except Exception as e:
                print(f"    [WARN] Attempt {attempt+1}/{MAX_RETRIES+1}: {type(e).__name__}: {e}")
                if attempt == MAX_RETRIES:
                    print(f"    [ERROR] Screen generation failed after {MAX_RETRIES+1} attempts!")
                    print(f"    [DEBUG] User Story: {us_text[:100]}")
                    print(f"    [DEBUG] IA Node: {ia_text[:100]}")
                    traceback.print_exc()
                    return None

        return None  # Should not reach here

    @staticmethod
    def _select_diverse_stories(stories: List[Any], max_screens: int) -> List[Any]:
        """Select stories covering different functional areas (Gap #10)."""
        if len(stories) <= max_screens:
            return list(stories)

        CATEGORY_KEYWORDS = {
            "auth": ["login", "register", "password", "auth", "2fa", "passkey", "signup", "sign-up"],
            "messaging": ["message", "chat", "send", "receive", "group", "conversation", "thread"],
            "profile": ["profile", "status", "picture", "about", "avatar", "account"],
            "settings": ["setting", "preference", "config", "notification", "privacy"],
            "media": ["photo", "video", "image", "media", "upload", "gallery", "camera"],
            "contacts": ["contact", "friend", "block", "invite", "address"],
            "calls": ["call", "voice", "ring", "dial", "audio"],
            "search": ["search", "find", "discover", "filter", "browse"],
            "admin": ["admin", "manage", "moderate", "report", "dashboard"],
        }

        categories: Dict[str, List] = {k: [] for k in CATEGORY_KEYWORDS}
        categories["other"] = []

        for story in stories:
            title = (story.get("title", "") if isinstance(story, dict)
                     else getattr(story, "title", "")).lower()
            desc = (story.get("description", "") if isinstance(story, dict)
                    else getattr(story, "description", "")).lower()
            text = f"{title} {desc}"

            placed = False
            for cat, keywords in CATEGORY_KEYWORDS.items():
                if any(kw in text for kw in keywords):
                    categories[cat].append(story)
                    placed = True
                    break
            if not placed:
                categories["other"].append(story)

        # Round-robin pick from non-empty categories
        result = []
        non_empty = {k: v for k, v in categories.items() if v}
        idx = {k: 0 for k in non_empty}

        while len(result) < max_screens:
            added_this_round = False
            for cat in list(non_empty.keys()):
                if len(result) >= max_screens:
                    break
                if idx[cat] < len(non_empty[cat]):
                    result.append(non_empty[cat][idx[cat]])
                    idx[cat] += 1
                    added_this_round = True
            if not added_this_round:
                break

        return result

    @staticmethod
    def _build_navigation_map(screens: List['Screen']) -> List[Dict]:
        """Build global navigation map from generated screens (Gap #12)."""
        nav_map = []
        for screen in screens:
            entry = {
                "path": screen.route,
                "screen_id": screen.id,
                "screen_name": screen.name,
                "auth_required": screen.auth_required,
                "transitions": [],
            }
            for rule in screen.navigation_rules:
                entry["transitions"].append({
                    "to": rule.get("target", ""),
                    "trigger": rule.get("trigger", ""),
                    "condition": rule.get("condition", ""),
                })
            nav_map.append(entry)
        return nav_map

    def _generate_wireframe(self, screen_name: str, description: str) -> str:
        """Generate simple Mermaid wireframe diagram."""

        wireframe = f"""flowchart TD
    subgraph {screen_name.replace(' ', '_')}
        Header[Header / Navigation]
        Main[Main Content Area]
        Sidebar[Sidebar / Filters]
        Footer[Footer / Actions]
    end

    Header --> Main
    Sidebar --> Main
    Main --> Footer

    %% {description}
"""
        return wireframe

    async def generate_ui_spec(
        self,
        project_name: str,
        domain: str,
        user_stories: List[Any],
        ux_spec: Any = None,
        api_endpoints: List[Any] = None
    ) -> UIDesignSpec:
        """Generate complete UI design specification."""

        print("  Generating design tokens...")
        design_tokens = await self.generate_design_tokens(project_name, domain)

        # Prepare screens and flows info
        screens_info = []
        flows_info = []

        if ux_spec:
            if hasattr(ux_spec, 'information_architecture'):
                screens_info = [{"name": n.name, "description": n.path} for n in ux_spec.information_architecture]
            if hasattr(ux_spec, 'user_flows'):
                flows_info = [{"name": f.name, "description": f.description} for f in ux_spec.user_flows]

        print("  Generating component library...")
        components = await self.generate_components(project_name, screens_info, flows_info)
        print(f"    Generated {len(components)} components")

        print("  Generating screen specifications...")
        screens = []

        # Get IA nodes if available
        ia_nodes = []
        if ux_spec and hasattr(ux_spec, 'information_architecture'):
            ia_nodes = ux_spec.information_architecture

        # Gap #10: Select diverse stories instead of sequential slice
        gen_config = self.config.get("generators", {}).get("ui_design", {})
        max_screens = gen_config.get("max_screens", 20)
        diverse_stories = self._select_diverse_stories(user_stories, max_screens)
        total = len(diverse_stories)

        for i, us in enumerate(diverse_stories, 1):
            ia_node = ia_nodes[i-1] if i <= len(ia_nodes) else None
            title = us.get('title', 'Story') if isinstance(us, dict) else getattr(us, 'title', 'Story')
            print(f"    [{i}/{total}] Screen for: {title}...")

            screen = await self.generate_screen(project_name, us, ia_node, components)
            if screen:
                screens.append(screen)

        print(f"    Generated {len(screens)} screens")

        # Gap #12: Generate global navigation map from screens
        navigation_map = self._build_navigation_map(screens)

        return UIDesignSpec(
            project_name=project_name,
            design_tokens=design_tokens,
            components=components,
            screens=screens,
            responsive_strategy="mobile-first",
            theme_support=True,
            dark_mode=True,
            navigation_map=navigation_map,
        )


def save_ui_design(ui_spec: UIDesignSpec, output_dir) -> None:
    """Save UI design specification to files."""
    from pathlib import Path

    ui_dir = Path(output_dir) / "ui_design"
    ui_dir.mkdir(parents=True, exist_ok=True)

    screens_dir = ui_dir / "screens"
    screens_dir.mkdir(exist_ok=True)

    # Save Design System
    design_md = generate_design_system_markdown(ui_spec)
    with open(ui_dir / "design_system.md", "w", encoding="utf-8") as f:
        f.write(design_md)

    # Save Design Tokens JSON (for CSS-in-JS / Tailwind)
    with open(ui_dir / "design_tokens.json", "w", encoding="utf-8") as f:
        json.dump(ui_spec.design_tokens.to_dict(), f, indent=2, ensure_ascii=False)

    # Save Components
    components_md = generate_components_markdown(ui_spec.components)
    with open(ui_dir / "components.md", "w", encoding="utf-8") as f:
        f.write(components_md)

    # Save Screens
    for screen in ui_spec.screens:
        screen_md = generate_screen_markdown(screen)
        with open(screens_dir / f"{screen.id.lower()}.md", "w", encoding="utf-8") as f:
            f.write(screen_md)

        # Save wireframe
        if screen.wireframe_mermaid:
            with open(screens_dir / f"{screen.id.lower()}_wireframe.mmd", "w", encoding="utf-8") as f:
                f.write(screen.wireframe_mermaid)

    # Save complete spec JSON
    with open(ui_dir / "ui_spec.json", "w", encoding="utf-8") as f:
        json.dump(ui_spec.to_dict(), f, indent=2, ensure_ascii=False)


def generate_design_system_markdown(ui_spec: UIDesignSpec) -> str:
    """Generate design system documentation."""

    tokens = ui_spec.design_tokens

    md = f"""# Design System - {ui_spec.project_name}

## Overview

| Property | Value |
|----------|-------|
| Responsive Strategy | {ui_spec.responsive_strategy} |
| Theme Support | {'Yes' if ui_spec.theme_support else 'No'} |
| Dark Mode | {'Yes' if ui_spec.dark_mode else 'No'} |

---

## Colors

| Token | Value | Preview |
|-------|-------|---------|
"""
    for name, value in tokens.colors.items():
        md += f"| `{name}` | `{value}` | |n"

    md += """
---

## Typography

| Style | Size | Weight | Line Height |
|-------|------|--------|-------------|
"""
    for name, props in tokens.typography.items():
        if isinstance(props, dict) and "size" in props:
            md += f"| `{name}` | {props.get('size', '-')} | {props.get('weight', '-')} | {props.get('line-height', '-')} |\n"

    md += """
---

## Spacing Scale

| Token | Value |
|-------|-------|
"""
    for name, value in tokens.spacing.items():
        md += f"| `{name}` | `{value}` |\n"

    md += """
---

## Breakpoints

| Name | Min Width |
|------|-----------|
"""
    for name, value in tokens.breakpoints.items():
        md += f"| `{name}` | `{value}px` |\n"

    md += """
---

## Shadows

| Token | Value |
|-------|-------|
"""
    for name, value in tokens.shadows.items():
        md += f"| `{name}` | `{value}` |\n"

    md += """
---

## Border Radius

| Token | Value |
|-------|-------|
"""
    for name, value in tokens.border_radius.items():
        md += f"| `{name}` | `{value}` |\n"

    return md


def generate_components_markdown(components: List[UIComponent]) -> str:
    """Generate component library documentation."""

    md = "# Component Library\n\n"

    for comp in components:
        md += f"""## {comp.name}

**ID:** `{comp.id}`
**Type:** {comp.component_type}

{comp.description}

### Variants

"""
        for variant in comp.variants:
            md += f"- `{variant}`\n"

        md += "\n### Props\n\n| Prop | Type |\n|------|------|\n"
        for prop, prop_type in comp.props.items():
            md += f"| `{prop}` | `{prop_type}` |\n"

        md += "\n### States\n\n"
        for state in comp.states:
            md += f"- {state}\n"

        if comp.accessibility:
            md += "\n### Accessibility\n\n"
            for attr, desc in comp.accessibility.items():
                md += f"- **{attr}:** {desc}\n"

        if comp.example_usage:
            md += f"\n### Example\n\n```tsx\n{comp.example_usage}\n```\n"

        md += "\n---\n\n"

    return md


def generate_screen_markdown(screen: Screen) -> str:
    """Generate screen specification documentation."""

    md = f"""# {screen.name}

**ID:** `{screen.id}`
**Route:** `{screen.route}`
**Layout:** {screen.layout}

{screen.description}

---

## Components Used

"""
    for comp_id in screen.components:
        md += f"- `{comp_id}`\n"

    md += """
---

## Data Requirements

"""
    for endpoint in screen.data_requirements:
        md += f"- `{endpoint}`\n"

    if screen.parent_user_story:
        md += f"""
---

## Related User Story

`{screen.parent_user_story}`
"""

    md += """
---

## Wireframe

"""
    # Show ASCII wireframe if available
    if screen.wireframe_ascii:
        md += "```\n"
        md += screen.wireframe_ascii
        md += "\n```\n"
    else:
        md += f"See `{screen.id.lower()}_wireframe.mmd` for the wireframe diagram.\n"

    return md
