"""
State Machine Generator - Extracts state machines from requirements and user stories.

This module analyzes requirements and user stories to identify entities with
meaningful state lifecycles, then generates state machines with states,
transitions, guards, actions, and Mermaid stateDiagram-v2 visualizations.
"""

import json
import os
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
class StateTransition:
    """A single transition between two states."""
    from_state: str
    to_state: str
    trigger: str = ""
    guard: str = ""  # condition
    action: str = ""  # side effect


@dataclass_json
@dataclass
class StateMachine:
    """Complete state machine for a domain entity."""
    entity: str  # message, user_session, call, group_member, device
    description: str = ""
    states: List[str] = field(default_factory=list)
    initial_state: str = ""
    final_states: List[str] = field(default_factory=list)
    transitions: List[StateTransition] = field(default_factory=list)
    mermaid_diagram: str = ""
    source_requirements: List[str] = field(default_factory=list)


class StateMachineGenerator:
    """Generates state machines from requirements and user stories."""

    IDENTIFY_ENTITIES_PROMPT = """Du bist ein Senior Software Architect spezialisiert auf Zustandsmodellierung. Analysiere die folgenden Requirements und User Stories und identifiziere alle Entitaeten/Konzepte die einen bedeutsamen Zustandslebenszyklus haben.

## Domain: {domain}

## Requirements:
{requirements_text}

## User Stories:
{user_stories_text}

## Bekannte Entities (falls vorhanden):
{entities_text}

Identifiziere Entitaeten die verschiedene Zustaende durchlaufen (z.B. Bestellung: erstellt -> bezahlt -> versendet -> zugestellt). Ignoriere Entitaeten die nur CRUD-Operationen haben ohne echte Zustandsuebergaenge.

Antworte NUR mit einem JSON-Array im folgenden Format:

[
    {{
        "entity": "entity_name_snake_case",
        "description": "Kurze Beschreibung des Lebenszyklus",
        "key_requirements": ["REQ-001", "REQ-005"]
    }}
]

Antworte NUR mit dem JSON-Array, keine zusaetzlichen Erklaerungen."""

    EXTRACT_STATES_PROMPT = """Du bist ein Senior Software Architect spezialisiert auf Zustandsmodellierung. Extrahiere die vollstaendige State Machine fuer die folgende Entitaet.

## Domain: {domain}

## Entitaet: {entity}
## Beschreibung: {description}

## Relevante Requirements:
{relevant_requirements}

## Relevante User Stories:
{relevant_stories}

Generiere eine vollstaendige State Machine mit allen Zustaenden, Uebergaengen, Guards und Actions.

Antworte NUR mit einem JSON-Objekt im folgenden Format:

{{
    "entity": "{entity}",
    "states": ["state_1", "state_2", "state_3"],
    "initial_state": "state_1",
    "final_states": ["state_3"],
    "transitions": [
        {{
            "from_state": "state_1",
            "to_state": "state_2",
            "trigger": "event_name",
            "guard": "optional_condition",
            "action": "optional_side_effect"
        }}
    ]
}}

Beachte:
- Verwende snake_case fuer alle Zustandsnamen und Trigger
- Jeder Zustand muss erreichbar sein (keine verwaisten Zustaende)
- Definiere mindestens einen Initial-State und mindestens einen Final-State
- Guards sind optionale Bedingungen (z.B. "payment_valid", "stock_available")
- Actions sind optionale Seiteneffekte (z.B. "send_notification", "update_inventory")
- Decke auch Fehlerzustaende und Rollback-Pfade ab

Antworte NUR mit dem JSON-Objekt, keine zusaetzlichen Erklaerungen."""

    def __init__(
        self,
        model_name: str = "openai/gpt-4o-mini",
        base_url: str = "https://openrouter.ai/api/v1",
        api_key: str = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the State Machine Generator.

        Args:
            model_name: LLM model to use (overrides config)
            base_url: API base URL
            api_key: API key
            config: Configuration dict with generators.state_machine section
        """
        self.config = config or {}
        gen_config = self.config.get("generators", {}).get("state_machine", {})

        self.model = model_name or gen_config.get("model", "openai/gpt-4o-mini")
        self.temperature = gen_config.get("temperature", 0.4)
        self.max_tokens = gen_config.get("max_tokens", 4000)
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or os.environ.get("OPENROUTER_API_KEY", "")
        )
        self.machines: List[StateMachine] = []

    async def initialize(self):
        """Initialize generator (placeholder for future async setup)."""
        pass

    async def generate_state_machines(
        self,
        requirements: List[Any],
        user_stories: List[Any],
        entities: Optional[List[Any]] = None,
        domain: str = ""
    ) -> List[StateMachine]:
        """
        Generate state machines from requirements and user stories.

        Step 1: Identify entities that have state (LLM call)
        Step 2: For each identified entity, extract states and transitions (LLM call per entity)
        Step 3: Generate Mermaid stateDiagram-v2 for each

        Args:
            requirements: List of requirement objects or dicts
            user_stories: List of user story objects or dicts
            entities: Optional list of known data entities
            domain: Project domain description

        Returns:
            List of StateMachine objects
        """
        self.machines = []

        # Build text representations
        requirements_text = self._format_requirements(requirements)
        user_stories_text = self._format_user_stories(user_stories)
        entities_text = self._format_entities(entities)

        # Step 1: Identify entities with state lifecycles
        identified = await self._identify_stateful_entities(
            requirements_text, user_stories_text, entities_text, domain
        )

        if not identified:
            return self.machines

        # Step 2: Extract state machine for each entity
        for entity_info in identified:
            entity_name = entity_info.get("entity", "")
            description = entity_info.get("description", "")
            key_reqs = entity_info.get("key_requirements", [])

            if not entity_name:
                continue

            machine = await self._extract_state_machine(
                entity=entity_name,
                description=description,
                key_requirements=key_reqs,
                requirements=requirements,
                user_stories=user_stories,
                domain=domain
            )

            if machine and machine.states:
                # Step 3: Generate Mermaid diagram
                machine.mermaid_diagram = self._generate_mermaid(machine)
                self.machines.append(machine)

        return self.machines

    async def _identify_stateful_entities(
        self,
        requirements_text: str,
        user_stories_text: str,
        entities_text: str,
        domain: str
    ) -> List[Dict[str, Any]]:
        """Step 1: Ask LLM to identify entities with meaningful state lifecycles."""
        prompt = self.IDENTIFY_ENTITIES_PROMPT.format(
            domain=domain or "Nicht spezifiziert",
            requirements_text=requirements_text,
            user_stories_text=user_stories_text,
            entities_text=entities_text
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
                component="state_machine_generator",
                model=self.model,
                response=response,
                latency_ms=latency_ms,
                user_message=prompt,
                response_text=content,
            )

            # Parse JSON
            data = self._parse_json(content)

            if isinstance(data, list):
                return data
            return []

        except Exception as e:
            print(f"    [ERROR] Entity identification failed: {e}")
            return []

    async def _extract_state_machine(
        self,
        entity: str,
        description: str,
        key_requirements: List[str],
        requirements: List[Any],
        user_stories: List[Any],
        domain: str
    ) -> Optional[StateMachine]:
        """Step 2: Extract states and transitions for a single entity."""
        # Filter relevant requirements and stories
        relevant_reqs = self._filter_relevant(requirements, key_requirements, entity)
        relevant_stories = self._filter_relevant_stories(user_stories, entity)

        prompt = self.EXTRACT_STATES_PROMPT.format(
            domain=domain or "Nicht spezifiziert",
            entity=entity,
            description=description,
            relevant_requirements=relevant_reqs,
            relevant_stories=relevant_stories
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
                component="state_machine_generator",
                model=self.model,
                response=response,
                latency_ms=latency_ms,
                user_message=prompt,
                response_text=content,
                metadata={"entity": entity},
            )

            # Parse JSON
            data = self._parse_json(content)

            if not isinstance(data, dict):
                return None

            # Build transitions
            transitions = []
            for t in data.get("transitions", []):
                transitions.append(StateTransition(
                    from_state=t.get("from_state", ""),
                    to_state=t.get("to_state", ""),
                    trigger=t.get("trigger", ""),
                    guard=t.get("guard", ""),
                    action=t.get("action", ""),
                ))

            return StateMachine(
                entity=data.get("entity", entity),
                description=description,
                states=data.get("states", []),
                initial_state=data.get("initial_state", ""),
                final_states=data.get("final_states", []),
                transitions=transitions,
                source_requirements=key_requirements,
            )

        except Exception as e:
            print(f"    [ERROR] State extraction for '{entity}' failed: {e}")
            return None

    def _generate_mermaid(self, machine: StateMachine) -> str:
        """Step 3: Programmatically generate Mermaid stateDiagram-v2."""
        lines = ["stateDiagram-v2"]

        # Initial state transition
        if machine.initial_state:
            lines.append(f"    [*] --> {machine.initial_state}")

        # Regular transitions
        for t in machine.transitions:
            label_parts = []
            if t.trigger:
                label_parts.append(t.trigger)
            if t.guard:
                label_parts.append(f"[{t.guard}]")
            if t.action:
                label_parts.append(f"/ {t.action}")

            label = " ".join(label_parts)
            if label:
                lines.append(f"    {t.from_state} --> {t.to_state} : {label}")
            else:
                lines.append(f"    {t.from_state} --> {t.to_state}")

        # Final state transitions
        for fs in machine.final_states:
            lines.append(f"    {fs} --> [*]")

        return "\n".join(lines)

    def _parse_json(self, content: str) -> Any:
        """Parse JSON from LLM response with multiple fallback strategies."""
        # Strategy 1: Direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Strategy 2: Strip markdown json fences
        if "```json" in content:
            try:
                extracted = content.split("```json")[1].split("```")[0].strip()
                return json.loads(extracted)
            except (json.JSONDecodeError, IndexError):
                pass

        # Strategy 3: Strip generic markdown fences
        if "```" in content:
            try:
                extracted = content.split("```")[1].split("```")[0].strip()
                return json.loads(extracted)
            except (json.JSONDecodeError, IndexError):
                pass

        # Strategy 4: Regex extract JSON array or object
        match = re.search(r'(\[[\s\S]*\]|\{[\s\S]*\})', content)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        print(f"    [WARN] Could not parse JSON from LLM response")
        return None

    def _format_requirements(self, requirements: List[Any]) -> str:
        """Format requirements list for prompt injection."""
        lines = []
        for req in requirements[:30]:  # Limit to avoid token overflow
            if hasattr(req, 'title'):
                req_id = getattr(req, 'requirement_id', 'REQ')
                lines.append(f"- {req_id}: {req.title}")
                desc = getattr(req, 'description', '')
                if desc:
                    lines.append(f"  {desc[:200]}")
            elif isinstance(req, dict):
                lines.append(f"- {req.get('id', req.get('requirement_id', 'REQ'))}: {req.get('title', 'Untitled')}")
                desc = req.get('description', '')
                if desc:
                    lines.append(f"  {desc[:200]}")
        return "\n".join(lines) if lines else "Keine Requirements angegeben"

    def _format_user_stories(self, user_stories: List[Any]) -> str:
        """Format user stories list for prompt injection."""
        lines = []
        for story in user_stories[:20]:  # Limit
            if hasattr(story, 'title'):
                sid = getattr(story, 'story_id', getattr(story, 'id', 'US'))
                lines.append(f"- {sid}: {story.title}")
                if hasattr(story, 'acceptance_criteria') and story.acceptance_criteria:
                    for ac in story.acceptance_criteria[:3]:
                        ac_text = ac if isinstance(ac, str) else getattr(ac, 'description', str(ac))
                        lines.append(f"  AC: {ac_text[:150]}")
            elif isinstance(story, dict):
                lines.append(f"- {story.get('id', story.get('story_id', 'US'))}: {story.get('title', 'Untitled')}")
                for ac in story.get('acceptance_criteria', [])[:3]:
                    ac_text = ac if isinstance(ac, str) else ac.get('description', str(ac))
                    lines.append(f"  AC: {ac_text[:150]}")
        return "\n".join(lines) if lines else "Keine User Stories angegeben"

    def _format_entities(self, entities: Optional[List[Any]]) -> str:
        """Format known entities for prompt injection."""
        if not entities:
            return "Keine bekannten Entities"

        lines = []
        entity_list = list(entities.values()) if isinstance(entities, dict) else list(entities)
        for e in entity_list[:15]:
            if hasattr(e, 'name'):
                lines.append(f"- {e.name}")
            elif isinstance(e, dict):
                lines.append(f"- {e.get('name', str(e))}")
            elif isinstance(e, str):
                lines.append(f"- {e}")
        return "\n".join(lines) if lines else "Keine bekannten Entities"

    def _filter_relevant(
        self,
        requirements: List[Any],
        key_req_ids: List[str],
        entity: str
    ) -> str:
        """Filter and format requirements relevant to an entity."""
        lines = []
        entity_lower = entity.lower().replace("_", " ")

        for req in requirements[:30]:
            req_id = ""
            title = ""
            desc = ""

            if hasattr(req, 'requirement_id'):
                req_id = req.requirement_id
                title = getattr(req, 'title', '')
                desc = getattr(req, 'description', '')
            elif isinstance(req, dict):
                req_id = req.get('id', req.get('requirement_id', ''))
                title = req.get('title', '')
                desc = req.get('description', '')

            # Include if ID matches or entity keyword found in text
            is_key = req_id in key_req_ids
            text = f"{title} {desc}".lower()
            is_relevant = entity_lower in text

            if is_key or is_relevant:
                lines.append(f"- {req_id}: {title}")
                if desc:
                    lines.append(f"  {desc[:300]}")

        return "\n".join(lines) if lines else "Keine spezifischen Requirements gefunden"

    def _filter_relevant_stories(self, user_stories: List[Any], entity: str) -> str:
        """Filter and format user stories relevant to an entity."""
        lines = []
        entity_lower = entity.lower().replace("_", " ")

        for story in user_stories[:20]:
            title = ""
            desc = ""

            if hasattr(story, 'title'):
                sid = getattr(story, 'story_id', getattr(story, 'id', 'US'))
                title = story.title
                desc = getattr(story, 'description', '')
            elif isinstance(story, dict):
                sid = story.get('id', story.get('story_id', 'US'))
                title = story.get('title', '')
                desc = story.get('description', '')
            else:
                continue

            text = f"{title} {desc}".lower()
            if entity_lower in text:
                lines.append(f"- {sid}: {title}")
                if desc:
                    lines.append(f"  {desc[:300]}")

        return "\n".join(lines) if lines else "Keine spezifischen User Stories gefunden"

    def to_markdown(self) -> str:
        """Generate markdown documentation for all state machines."""
        if not self.machines:
            return "# State Machines\n\nKeine State Machines identifiziert.\n"

        md = "# State Machines\n\n"
        md += f"Insgesamt **{len(self.machines)}** State Machines identifiziert.\n\n"
        md += "---\n\n"

        for i, machine in enumerate(self.machines, 1):
            md += f"## {i}. {machine.entity.replace('_', ' ').title()}\n\n"

            if machine.description:
                md += f"_{machine.description}_\n\n"

            # States table
            md += "### Zustaende\n\n"
            md += "| Zustand | Typ |\n"
            md += "|---------|-----|\n"
            for state in machine.states:
                state_type = ""
                if state == machine.initial_state:
                    state_type = "Initial"
                elif state in machine.final_states:
                    state_type = "Final"
                md += f"| `{state}` | {state_type} |\n"
            md += "\n"

            # Transitions table
            if machine.transitions:
                md += "### Uebergaenge\n\n"
                md += "| Von | Nach | Trigger | Guard | Action |\n"
                md += "|-----|------|---------|-------|--------|\n"
                for t in machine.transitions:
                    guard = t.guard if t.guard else "-"
                    action = t.action if t.action else "-"
                    md += f"| `{t.from_state}` | `{t.to_state}` | `{t.trigger}` | {guard} | {action} |\n"
                md += "\n"

            # Mermaid diagram
            if machine.mermaid_diagram:
                md += "### Diagramm\n\n"
                md += "```mermaid\n"
                md += machine.mermaid_diagram
                md += "\n```\n\n"

            # Source requirements
            if machine.source_requirements:
                md += "### Quell-Requirements\n\n"
                for req_id in machine.source_requirements:
                    md += f"- {req_id}\n"
                md += "\n"

            md += "---\n\n"

        return md


def save_state_machines(machines: List[StateMachine], output_dir) -> None:
    """
    Save state machines to files.

    Creates:
    - state_machines/{entity}.mmd - Mermaid diagram per entity
    - state_machines/state_machines.md - Summary markdown
    - state_machines/state_machines.json - JSON export

    Args:
        machines: List of StateMachine objects
        output_dir: Output directory path
    """
    from pathlib import Path

    sm_dir = Path(output_dir) / "state_machines"
    sm_dir.mkdir(parents=True, exist_ok=True)

    # Save each machine as {entity}.mmd
    for machine in machines:
        if machine.mermaid_diagram:
            mmd_path = sm_dir / f"{machine.entity}.mmd"
            with open(mmd_path, "w", encoding="utf-8") as f:
                f.write(machine.mermaid_diagram)

    # Save summary markdown
    generator = StateMachineGenerator.__new__(StateMachineGenerator)
    generator.machines = machines
    md_content = generator.to_markdown()
    with open(sm_dir / "state_machines.md", "w", encoding="utf-8") as f:
        f.write(md_content)

    # Save JSON
    machines_data = [m.to_dict() for m in machines]
    with open(sm_dir / "state_machines.json", "w", encoding="utf-8") as f:
        json.dump(machines_data, f, indent=2, ensure_ascii=False)
