"""
UX Design Generator - Generates User Experience design artifacts.

This module creates UX artifacts including personas, user flows,
information architecture, and accessibility requirements.
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
class FlowStep:
    """Individual step in a user flow."""
    step_number: int
    action: str
    screen: str
    expected_result: str
    decision_point: bool = False
    error_scenario: str = ""


@dataclass_json
@dataclass
class UserFlow:
    """User flow through the application."""
    id: str
    name: str
    description: str
    actor: str  # Persona
    trigger: str
    steps: List[FlowStep] = field(default_factory=list)
    success_criteria: str = ""
    error_scenarios: List[str] = field(default_factory=list)
    mermaid_diagram: str = ""
    # Relationships for Dashboard linking
    linked_persona_id: str = ""  # Persona ID that performs this flow
    linked_screen_ids: List[str] = field(default_factory=list)  # Screens involved in this flow
    linked_user_story_ids: List[str] = field(default_factory=list)  # User stories this flow implements


@dataclass_json
@dataclass
class Persona:
    """User persona for UX design."""
    id: str
    name: str
    role: str
    age_range: str = ""
    goals: List[str] = field(default_factory=list)
    pain_points: List[str] = field(default_factory=list)
    tech_savviness: str = "medium"  # low, medium, high
    frequency_of_use: str = "weekly"  # daily, weekly, monthly, occasional
    quote: str = ""
    background: str = ""


@dataclass_json
@dataclass
class IANode:
    """Information Architecture node (page/section)."""
    id: str
    name: str
    path: str
    parent_id: str = ""
    children: List[str] = field(default_factory=list)
    content_types: List[str] = field(default_factory=list)


@dataclass_json
@dataclass
class UXDesignSpec:
    """Complete UX design specification."""
    project_name: str
    personas: List[Persona] = field(default_factory=list)
    user_flows: List[UserFlow] = field(default_factory=list)
    information_architecture: List[IANode] = field(default_factory=list)
    accessibility_requirements: List[str] = field(default_factory=list)
    interaction_patterns: List[str] = field(default_factory=list)
    design_principles: List[str] = field(default_factory=list)
    # Gap #15: Input validation rules per field/screen
    validation_rules: List[Dict] = field(default_factory=list)


class UXDesignGenerator:
    """Generates UX design artifacts from requirements and user stories."""

    PERSONA_PROMPT = """Du bist ein UX Designer. Erstelle Personas basierend auf den Stakeholdern und User Stories.

## Projekt: {project_name}
## Domain: {domain}

## Stakeholders:
{stakeholders_text}

## User Stories:
{user_stories_text}

Erstelle 2-4 Personas im folgenden JSON-Format:

{{
    "personas": [
        {{
            "id": "PERSONA-001",
            "name": "Max Mustermann",
            "role": "Finance Manager",
            "age_range": "35-45",
            "goals": ["Effiziente Rechnungsbearbeitung", "Transparente Uebersicht"],
            "pain_points": ["Manuelle Dateneingabe", "Fehlende Automatisierung"],
            "tech_savviness": "medium",
            "frequency_of_use": "daily",
            "quote": "Ich brauche einen schnellen Ueberblick ueber alle offenen Rechnungen.",
            "background": "10 Jahre Erfahrung im Finanzwesen, arbeitet mit Excel und ERP-Systemen."
        }}
    ]
}}

Antworte NUR mit dem JSON-Objekt."""

    USER_FLOW_PROMPT = """Du bist ein UX Designer. Erstelle User Flows basierend auf den User Stories.

## Projekt: {project_name}
## Persona: {persona_name} ({persona_role})

## User Story:
{user_story_text}

Erstelle einen detaillierten User Flow im folgenden JSON-Format:

{{
    "id": "FLOW-001",
    "name": "Rechnung erstellen",
    "description": "Flow zum Erstellen einer neuen Rechnung",
    "actor": "{persona_name}",
    "trigger": "User klickt auf 'Neue Rechnung'",
    "steps": [
        {{
            "step_number": 1,
            "action": "User oeffnet Dashboard",
            "screen": "Dashboard",
            "expected_result": "Dashboard wird angezeigt",
            "decision_point": false,
            "error_scenario": ""
        }},
        {{
            "step_number": 2,
            "action": "User klickt 'Neue Rechnung'",
            "screen": "Dashboard",
            "expected_result": "Rechnungsformular oeffnet sich",
            "decision_point": false,
            "error_scenario": "Button deaktiviert wenn keine Berechtigung"
        }}
    ],
    "success_criteria": "Rechnung wurde erfolgreich erstellt und gespeichert",
    "error_scenarios": [
        "Validierungsfehler bei Pflichtfeldern",
        "Serververbindung fehlgeschlagen"
    ]
}}

Antworte NUR mit dem JSON-Objekt."""

    IA_PROMPT = """Du bist ein UX Designer. Erstelle eine Information Architecture basierend auf den Features.

## Projekt: {project_name}

## Features:
{features_text}

## User Flows:
{flows_summary}

Erstelle eine Information Architecture (Sitemap) im folgenden JSON-Format:

{{
    "nodes": [
        {{
            "id": "IA-001",
            "name": "Home",
            "path": "/",
            "parent_id": "",
            "children": ["IA-002", "IA-003"],
            "content_types": ["dashboard", "quick-actions"]
        }},
        {{
            "id": "IA-002",
            "name": "Rechnungen",
            "path": "/invoices",
            "parent_id": "IA-001",
            "children": ["IA-004", "IA-005"],
            "content_types": ["list", "filters", "search"]
        }}
    ],
    "accessibility_requirements": [
        "WCAG 2.1 Level AA Compliance",
        "Keyboard Navigation fuer alle Funktionen",
        "Screen Reader Support",
        "Kontrastverhältnis mindestens 4.5:1"
    ],
    "interaction_patterns": [
        "Infinite Scroll fuer Listen",
        "Modal Dialoge fuer Formulare",
        "Toast Notifications fuer Feedback",
        "Drag & Drop fuer Datei-Upload"
    ],
    "design_principles": [
        "Mobile First",
        "Progressive Disclosure",
        "Consistency ueber alle Screens",
        "Fehlertoleranz"
    ]
}}

Antworte NUR mit dem JSON-Objekt."""

    VALIDATION_PROMPT = """Du bist ein UX Engineer. Definiere Input-Validierungsregeln fuer die User Flows und Screens.

## Projekt: {project_name}

## User Flows:
{flows_text}

## Screens/Formulare:
{screens_text}

Erstelle Validierungsregeln im folgenden JSON-Format:

{{
    "validations": [
        {{
            "field": "phone_number",
            "screen": "Registration",
            "rules": [
                {{"type": "required", "message": "Phone number is required"}},
                {{"type": "format", "pattern": "E.164", "message": "Must be valid E.164 format"}},
                {{"type": "min_length", "value": 9, "message": "Too short"}},
                {{"type": "max_length", "value": 15, "message": "Too long"}}
            ]
        }},
        {{
            "field": "email",
            "screen": "Profile",
            "rules": [
                {{"type": "required", "message": "Email is required"}},
                {{"type": "format", "pattern": "email", "message": "Must be a valid email"}}
            ]
        }}
    ]
}}

Beruecksichtige:
- Pflichtfelder (required)
- Format-Validierung (email, phone, URL, etc.)
- Laenge (min_length, max_length)
- Bereich (min, max) fuer numerische Felder
- Muster (pattern) fuer spezielle Formate
- Abhaengigkeiten zwischen Feldern

Antworte NUR mit dem JSON-Objekt."""

    def __init__(
        self,
        model: str = None,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key: str = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the UX Design Generator.

        Args:
            model: LLM model to use (overrides config)
            base_url: API base URL
            api_key: API key
            config: Configuration dict with generators.ux_design section
        """
        import os
        self.config = config or {}
        gen_config = self.config.get("generators", {}).get("ux_design", {})

        self.model = model or gen_config.get("model", "openai/gpt-4o-mini")
        self.temperature = gen_config.get("temperature", 0.6)
        self.max_tokens = gen_config.get("max_tokens", 8000)
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key or os.environ.get("OPENROUTER_API_KEY"))
        self.persona_counter = 0
        self.flow_counter = 0

    async def generate_personas(
        self,
        project_name: str,
        domain: str,
        stakeholders: List[Any],
        user_stories: List[Any]
    ) -> List[Persona]:
        """Generate personas from stakeholders and user stories."""

        # Build stakeholders text
        stakeholder_lines = []
        for sh in stakeholders[:5]:
            if isinstance(sh, dict):
                role = sh.get('role', 'User')
                concerns = sh.get('concerns', [])
                stakeholder_lines.append(f"- {role}: {', '.join(concerns)}")
            elif hasattr(sh, 'role'):
                stakeholder_lines.append(f"- {sh.role}: {', '.join(sh.concerns or [])}")

        stakeholders_text = "\n".join(stakeholder_lines) if stakeholder_lines else "Keine Stakeholder definiert"

        # Build user stories text
        us_lines = []
        for us in user_stories[:10]:
            if hasattr(us, 'persona'):
                us_lines.append(f"- Als {us.persona} moechte ich {us.action}, um {us.benefit}")
            elif isinstance(us, dict):
                us_lines.append(f"- {us.get('title', 'Story')}: {us.get('description', '')[:100]}")

        user_stories_text = "\n".join(us_lines) if us_lines else "Keine User Stories"

        prompt = self.PERSONA_PROMPT.format(
            project_name=project_name,
            domain=domain,
            stakeholders_text=stakeholders_text,
            user_stories_text=user_stories_text
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
                component="ux_design_generator",
                model=self.model,
                response=response,
                latency_ms=latency_ms,
                metadata={"method": "generate_personas"},
                user_message=prompt,
                response_text=content,
            )

            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            data = json.loads(content)
            personas = []

            for p in data.get("personas", []):
                self.persona_counter += 1
                persona = Persona(
                    id=f"PERSONA-{self.persona_counter:03d}",
                    name=p.get("name", f"User {self.persona_counter}"),
                    role=p.get("role", "User"),
                    age_range=p.get("age_range", ""),
                    goals=p.get("goals", []),
                    pain_points=p.get("pain_points", []),
                    tech_savviness=p.get("tech_savviness", "medium"),
                    frequency_of_use=p.get("frequency_of_use", "weekly"),
                    quote=p.get("quote", ""),
                    background=p.get("background", "")
                )
                personas.append(persona)

            return personas

        except Exception as e:
            print(f"    [WARN] Persona generation failed: {e}")
            return []

    async def generate_user_flow(
        self,
        project_name: str,
        persona: Persona,
        user_story: Any
    ) -> Optional[UserFlow]:
        """Generate a user flow for a specific user story and persona."""

        # Build user story text
        if hasattr(user_story, 'persona'):
            # Handle AcceptanceCriterion objects or strings
            ac_list = user_story.acceptance_criteria or []
            ac_lines = []
            for ac in ac_list:
                if hasattr(ac, 'to_gherkin'):
                    ac_lines.append('- ' + ac.to_gherkin().replace('\n', '; '))
                else:
                    ac_lines.append('- ' + str(ac))
            us_text = f"""ID: {user_story.id}
Title: {user_story.title}
Als {user_story.persona} moechte ich {user_story.action}, um {user_story.benefit}

Acceptance Criteria:
{chr(10).join(ac_lines)}"""
        elif isinstance(user_story, dict):
            us_text = f"""ID: {user_story.get('id', 'US-XXX')}
Title: {user_story.get('title', 'User Story')}
Description: {user_story.get('description', '')}"""
        else:
            us_text = str(user_story)

        prompt = self.USER_FLOW_PROMPT.format(
            project_name=project_name,
            persona_name=persona.name,
            persona_role=persona.role,
            user_story_text=us_text
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
                component="ux_design_generator",
                model=self.model,
                response=response,
                latency_ms=latency_ms,
                metadata={"method": "generate_user_flow"},
                user_message=prompt,
                response_text=content,
            )

            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            data = json.loads(content)
            self.flow_counter += 1

            steps = []
            for s in data.get("steps", []):
                step = FlowStep(
                    step_number=s.get("step_number", 0),
                    action=s.get("action", ""),
                    screen=s.get("screen", ""),
                    expected_result=s.get("expected_result", ""),
                    decision_point=s.get("decision_point", False),
                    error_scenario=s.get("error_scenario", "")
                )
                steps.append(step)

            flow = UserFlow(
                id=f"FLOW-{self.flow_counter:03d}",
                name=data.get("name", f"Flow {self.flow_counter}"),
                description=data.get("description", ""),
                actor=persona.name,
                trigger=data.get("trigger", ""),
                steps=steps,
                success_criteria=data.get("success_criteria", ""),
                error_scenarios=data.get("error_scenarios", []),
                mermaid_diagram=self._generate_flow_diagram(data.get("name", "Flow"), steps)
            )

            return flow

        except Exception as e:
            print(f"    [WARN] User flow generation failed: {e}")
            return None

    def _generate_flow_diagram(self, flow_name: str, steps: List[FlowStep]) -> str:
        """Generate Mermaid flowchart for user flow."""

        diagram = f"""flowchart TD
    Start([Start: {flow_name}])
"""

        prev_id = "Start"
        for step in steps:
            step_id = f"S{step.step_number}"
            if step.decision_point:
                diagram += f"    {step_id}{{{step.action}}}\n"
            else:
                diagram += f"    {step_id}[{step.action}]\n"

            diagram += f"    {prev_id} --> {step_id}\n"

            if step.error_scenario:
                err_id = f"E{step.step_number}"
                diagram += f"    {err_id}[/{step.error_scenario}/]\n"
                diagram += f"    {step_id} -.-> {err_id}\n"

            prev_id = step_id

        diagram += f"    {prev_id} --> End([End])\n"

        return diagram

    async def generate_information_architecture(
        self,
        project_name: str,
        features: List[Any],
        user_flows: List[UserFlow]
    ) -> tuple:
        """Generate information architecture from features and flows."""

        # Build features text
        feature_lines = []
        for f in features[:10]:
            if hasattr(f, 'name'):
                feature_lines.append(f"- {f.name}: {getattr(f, 'description', '')[:100]}")
            elif isinstance(f, dict):
                feature_lines.append(f"- {f.get('name', f.get('id', 'Feature'))}: {f.get('description', '')[:100]}")

        features_text = "\n".join(feature_lines) if feature_lines else "Keine Features"

        # Build flows summary
        flows_summary = "\n".join([f"- {flow.name}: {flow.description}" for flow in user_flows[:5]])

        prompt = self.IA_PROMPT.format(
            project_name=project_name,
            features_text=features_text,
            flows_summary=flows_summary or "Keine Flows"
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
                component="ux_design_generator",
                model=self.model,
                response=response,
                latency_ms=latency_ms,
                metadata={"method": "generate_information_architecture"},
                user_message=prompt,
                response_text=content,
            )

            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            data = json.loads(content)

            nodes = []
            for n in data.get("nodes", []):
                node = IANode(
                    id=n.get("id", ""),
                    name=n.get("name", ""),
                    path=n.get("path", ""),
                    parent_id=n.get("parent_id", ""),
                    children=n.get("children", []),
                    content_types=n.get("content_types", [])
                )
                nodes.append(node)

            accessibility = data.get("accessibility_requirements", [])
            interaction_patterns = data.get("interaction_patterns", [])
            design_principles = data.get("design_principles", [])

            return nodes, accessibility, interaction_patterns, design_principles

        except Exception as e:
            print(f"    [WARN] IA generation failed: {e}")
            return [], [], [], []

    async def generate_validation_rules(
        self,
        project_name: str,
        user_flows: List[UserFlow],
        user_stories: List[Any]
    ) -> List[Dict]:
        """Generate input validation rules for screens and flows (Gap #15)."""
        flows_text = "\n".join(
            f"- {f.name}: {f.description}" for f in user_flows[:5]
        ) if user_flows else "Keine Flows"

        screens_text = []
        for us in user_stories[:10]:
            if hasattr(us, 'title'):
                screens_text.append(f"- {us.title}: {getattr(us, 'action', '')}")
            elif isinstance(us, dict):
                screens_text.append(f"- {us.get('title', 'Screen')}: {us.get('description', '')[:100]}")
        screens_str = "\n".join(screens_text) if screens_text else "Keine Screens"

        prompt = self.VALIDATION_PROMPT.format(
            project_name=project_name,
            flows_text=flows_text,
            screens_text=screens_str,
        )

        try:
            start_time = time.time()
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            latency_ms = int((time.time() - start_time) * 1000)

            content = response.choices[0].message.content.strip()

            log_llm_call(
                component="ux_design_generator",
                model=self.model,
                response=response,
                latency_ms=latency_ms,
                metadata={"method": "generate_validation_rules"},
                user_message=prompt,
                response_text=content,
            )
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            data = json.loads(content)
            return data.get("validations", [])

        except Exception as e:
            print(f"    [WARN] Validation rules generation failed: {e}")
            return []

    async def generate_ux_spec(
        self,
        project_name: str,
        domain: str,
        stakeholders: List[Any],
        user_stories: List[Any],
        features: List[Any]
    ) -> UXDesignSpec:
        """Generate complete UX design specification."""

        print("  Generating personas...")
        personas = await self.generate_personas(project_name, domain, stakeholders, user_stories)
        print(f"    Generated {len(personas)} personas")

        print("  Generating user flows...")
        user_flows = []
        # Generate flows for top user stories with first persona
        main_persona = personas[0] if personas else Persona(id="PERSONA-001", name="Default User", role="User")

        for i, us in enumerate(user_stories[:5], 1):
            title = us.get('title', 'Story') if isinstance(us, dict) else getattr(us, 'title', 'Story')
            print(f"    [{i}/5] Flow for: {title}...")
            flow = await self.generate_user_flow(project_name, main_persona, us)
            if flow:
                user_flows.append(flow)
        print(f"    Generated {len(user_flows)} user flows")

        print("  Generating information architecture...")
        ia_nodes, accessibility, patterns, principles = await self.generate_information_architecture(
            project_name, features, user_flows
        )
        print(f"    Generated {len(ia_nodes)} IA nodes")

        # Gap #15: Generate validation rules
        print("  Generating validation rules...")
        validation_rules = await self.generate_validation_rules(
            project_name, user_flows, user_stories
        )
        print(f"    Generated {len(validation_rules)} validation rules")

        return UXDesignSpec(
            project_name=project_name,
            personas=personas,
            user_flows=user_flows,
            information_architecture=ia_nodes,
            accessibility_requirements=accessibility,
            interaction_patterns=patterns,
            design_principles=principles,
            validation_rules=validation_rules,
        )


def save_ux_design(ux_spec: UXDesignSpec, output_dir) -> None:
    """Save UX design specification to files."""
    from pathlib import Path

    ux_dir = Path(output_dir) / "ux_design"
    ux_dir.mkdir(parents=True, exist_ok=True)

    # Create subdirectories
    flows_dir = ux_dir / "user_flows"
    flows_dir.mkdir(exist_ok=True)

    # Save Personas
    personas_md = generate_personas_markdown(ux_spec.personas)
    with open(ux_dir / "personas.md", "w", encoding="utf-8") as f:
        f.write(personas_md)

    # Save User Flows Overview
    flows_md = generate_user_flows_markdown(ux_spec.user_flows)
    with open(ux_dir / "user_flows.md", "w", encoding="utf-8") as f:
        f.write(flows_md)

    # Save individual flow diagrams
    for flow in ux_spec.user_flows:
        with open(flows_dir / f"{flow.id.lower()}.mmd", "w", encoding="utf-8") as f:
            f.write(flow.mermaid_diagram)

    # Save Information Architecture
    ia_md = generate_ia_markdown(ux_spec)
    with open(ux_dir / "information_architecture.md", "w", encoding="utf-8") as f:
        f.write(ia_md)

    # Save Accessibility Checklist
    a11y_md = generate_accessibility_checklist(ux_spec.accessibility_requirements)
    with open(ux_dir / "accessibility_checklist.md", "w", encoding="utf-8") as f:
        f.write(a11y_md)

    # Save JSON
    with open(ux_dir / "ux_spec.json", "w", encoding="utf-8") as f:
        json.dump(ux_spec.to_dict(), f, indent=2, ensure_ascii=False)


def generate_personas_markdown(personas: List[Persona]) -> str:
    """Generate markdown for personas."""

    md = "# User Personas\n\n"

    for persona in personas:
        md += f"""## {persona.name}

**Role:** {persona.role}
**Age Range:** {persona.age_range}
**Tech Savviness:** {persona.tech_savviness}
**Usage Frequency:** {persona.frequency_of_use}

> "{persona.quote}"

### Background

{persona.background}

### Goals

"""
        for goal in persona.goals:
            md += f"- {goal}\n"

        md += "\n### Pain Points\n\n"
        for pain in persona.pain_points:
            md += f"- {pain}\n"

        md += "\n---\n\n"

    return md


def generate_user_flows_markdown(flows: List[UserFlow]) -> str:
    """Generate markdown for user flows."""

    md = "# User Flows\n\n"

    for flow in flows:
        md += f"""## {flow.id}: {flow.name}

**Actor:** {flow.actor}
**Trigger:** {flow.trigger}

{flow.description}

### Steps

| # | Action | Screen | Expected Result |
|---|--------|--------|-----------------|
"""
        for step in flow.steps:
            decision = " (Decision)" if step.decision_point else ""
            md += f"| {step.step_number} | {step.action}{decision} | {step.screen} | {step.expected_result} |\n"

        md += f"""
### Success Criteria

{flow.success_criteria}

### Error Scenarios

"""
        for err in flow.error_scenarios:
            md += f"- {err}\n"

        md += f"\n**Diagram:** See `user_flows/{flow.id.lower()}.mmd`\n\n---\n\n"

    return md


def generate_ia_markdown(ux_spec: UXDesignSpec) -> str:
    """Generate markdown for information architecture."""

    md = f"""# Information Architecture - {ux_spec.project_name}

## Site Map

"""

    # Build tree structure
    for node in ux_spec.information_architecture:
        indent = "  " if node.parent_id else ""
        md += f"{indent}- **{node.name}** (`{node.path}`)\n"
        if node.content_types:
            md += f"{indent}  - Content: {', '.join(node.content_types)}\n"

    md += """
---

## Interaction Patterns

"""
    for pattern in ux_spec.interaction_patterns:
        md += f"- {pattern}\n"

    md += """
---

## Design Principles

"""
    for principle in ux_spec.design_principles:
        md += f"1. {principle}\n"

    return md


def generate_accessibility_checklist(requirements: List[str]) -> str:
    """Generate accessibility checklist."""

    md = """# Accessibility Checklist

## Requirements

"""
    for req in requirements:
        md += f"- [ ] {req}\n"

    md += """
---

## WCAG 2.1 Quick Reference

### Perceivable

- [ ] All images have alt text
- [ ] Videos have captions
- [ ] Color is not the only way to convey information
- [ ] Text can be resized up to 200%

### Operable

- [ ] All functionality available via keyboard
- [ ] No keyboard traps
- [ ] Skip navigation links provided
- [ ] Focus indicators visible

### Understandable

- [ ] Language of page is identified
- [ ] Navigation is consistent
- [ ] Error messages are clear
- [ ] Labels describe purpose of inputs

### Robust

- [ ] Valid HTML markup
- [ ] ARIA attributes used correctly
- [ ] Works with assistive technologies
"""

    return md
