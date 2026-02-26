"""
Markdown Parser for RE System output files.

Parses user_stories.md to extract Epics and User Stories.
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Tuple, Any


def parse_user_stories_md(filepath: Path) -> Tuple[List[Dict], List[Dict]]:
    """
    Parse user_stories.md and extract Epics and User Stories.

    Args:
        filepath: Path to the user_stories.md file

    Returns:
        Tuple of (epics_list, user_stories_list)
    """
    content = filepath.read_text(encoding="utf-8")
    epics = []
    user_stories = []

    # Split into Epics and User Stories sections
    # The file has "# Epics" section followed by "# User Stories" section
    parts = re.split(r'\n# User Stories\s*\n', content, maxsplit=1)

    epics_section = parts[0] if parts else ""
    us_section = parts[1] if len(parts) > 1 else ""

    # Parse Epics
    # Format: # EPIC-XXX: Title
    epic_pattern = r'# (EPIC-\d+): (.+?)(?=\n# EPIC-|\n---\n# User Stories|\Z)'
    for match in re.finditer(epic_pattern, epics_section, re.DOTALL):
        epic_id = match.group(1)
        epic_content = match.group(2)

        title = epic_content.split('\n')[0].strip()
        description = extract_section(epic_content, "Description")
        linked_reqs = extract_list_items(epic_content, "Linked Requirements")
        linked_stories = extract_list_items(epic_content, "User Stories")
        status = extract_field(epic_content, "Status")

        epics.append({
            "id": epic_id,
            "title": title,
            "description": description,
            "status": status or "draft",
            "linked_requirements": linked_reqs,
            "linked_user_stories": linked_stories
        })

    # Parse User Stories
    # Format: ## US-XXX: Title
    us_pattern = r'## (US-\d+): (.+?)(?=\n## US-|\n---\s*$|\Z)'
    for match in re.finditer(us_pattern, us_section, re.DOTALL):
        us_id = match.group(1)
        us_content = match.group(2)

        title = us_content.split('\n')[0].strip()
        priority = extract_field(us_content, "Priority")
        linked_req = extract_field(us_content, "Linked Requirement")

        # Extract the user story text (As a... I want to... So that...)
        story_text = extract_user_story_text(us_content)

        # Extract acceptance criteria
        acceptance_criteria = extract_acceptance_criteria(us_content)

        user_stories.append({
            "id": us_id,
            "title": title,
            "priority": priority or "SHOULD",
            "linked_requirement": linked_req,
            "persona": story_text.get("persona", "user"),
            "action": story_text.get("action", ""),
            "benefit": story_text.get("benefit", ""),
            "acceptance_criteria": acceptance_criteria
        })

    return epics, user_stories


def extract_section(content: str, section_name: str) -> str:
    """Extract content from a ## Section header."""
    pattern = rf'## {section_name}\s*\n(.*?)(?=\n## |\n# |\Z)'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def extract_field(content: str, field_name: str) -> str:
    """Extract a **Field:** value line."""
    pattern = rf'\*\*{field_name}:\*\*\s*(.+?)(?:\n|$)'
    match = re.search(pattern, content)
    if match:
        return match.group(1).strip()
    return ""


def extract_list_items(content: str, section_name: str) -> List[str]:
    """Extract list items from a ## Section."""
    section_content = extract_section(content, section_name)
    if not section_content:
        return []

    items = []
    for line in section_content.split('\n'):
        line = line.strip()
        if line.startswith('- '):
            items.append(line[2:].strip())
    return items


def extract_user_story_text(content: str) -> Dict[str, str]:
    """
    Extract the user story format:
    > As a **Role**
    > I want to **action**
    > So that **benefit**
    """
    result = {"persona": "", "action": "", "benefit": ""}

    # Find the ### User Story section
    story_section = extract_section(content, "# User Story")
    if not story_section:
        # Try alternate header format
        pattern = r'### User Story\s*\n(.*?)(?=\n### |\n## |\Z)'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            story_section = match.group(1)

    if story_section:
        # Extract persona: As a **Role**
        persona_match = re.search(r'As a \*\*(.+?)\*\*', story_section)
        if persona_match:
            result["persona"] = persona_match.group(1)

        # Extract action: I want to **action**
        action_match = re.search(r'I want to \*\*(.+?)\*\*', story_section)
        if action_match:
            result["action"] = action_match.group(1)

        # Extract benefit: So that **benefit**
        benefit_match = re.search(r'So that \*\*(.+?)\*\*', story_section)
        if benefit_match:
            result["benefit"] = benefit_match.group(1)

    return result


def extract_acceptance_criteria(content: str) -> List[Dict[str, str]]:
    """Extract acceptance criteria from a user story."""
    criteria = []

    # Find the ### Acceptance Criteria section
    pattern = r'### Acceptance Criteria\s*\n(.*?)(?=\n## |\n---|\Z)'
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return criteria

    ac_section = match.group(1)

    # Split by **AC-X:** patterns
    ac_pattern = r'\*\*(AC-\d+):\*\*\s*(.*?)(?=\n\*\*AC-|\Z)'
    for ac_match in re.finditer(ac_pattern, ac_section, re.DOTALL):
        ac_id = ac_match.group(1)
        ac_content = ac_match.group(2).strip()

        # Extract Given/When/Then
        given = ""
        when = ""
        then = ""

        given_match = re.search(r'- Given:\s*(.+?)(?=\n- |\Z)', ac_content, re.DOTALL)
        if given_match:
            given = given_match.group(1).strip()

        when_match = re.search(r'- When:\s*(.+?)(?=\n- |\Z)', ac_content, re.DOTALL)
        if when_match:
            when = when_match.group(1).strip()

        then_match = re.search(r'- Then:\s*(.+?)(?=\n- |\n\*\*|\Z)', ac_content, re.DOTALL)
        if then_match:
            then = then_match.group(1).strip()

        criteria.append({
            "id": ac_id,
            "given": given,
            "when": when,
            "then": then,
            "description": f"Given {given}, When {when}, Then {then}"
        })

    return criteria


def extract_project_name(project_dir: Path) -> str:
    """
    Extract project name from folder name.
    Format: "Project Name_YYYYMMDD_HHMMSS" -> "Project Name"
    """
    name = project_dir.name
    # Remove timestamp suffix
    parts = name.rsplit("_", 2)
    if len(parts) >= 3 and parts[-2].isdigit() and parts[-1].isdigit():
        return "_".join(parts[:-2])
    return name


def extract_timestamp(folder_name: str) -> str:
    """
    Extract timestamp from folder name.
    Format: "Project Name_YYYYMMDD_HHMMSS" -> "YYYYMMDD_HHMMSS"
    """
    parts = folder_name.rsplit("_", 2)
    if len(parts) >= 3 and parts[-2].isdigit() and parts[-1].isdigit():
        return f"{parts[-2]}_{parts[-1]}"
    return ""


def parse_traceability_matrix_md(filepath: Path) -> List[Dict]:
    """
    Parse traceability_matrix.md and extract requirement linkages.

    Args:
        filepath: Path to the traceability_matrix.md file

    Returns:
        List of traceability entries with req_id, us_ids, test_ids
    """
    content = filepath.read_text(encoding="utf-8")
    entries = []

    # Find the markdown table in "Full Traceability" section
    # Table format: | Requirement | Type | Priority | User Stories | Test Cases |
    table_pattern = r'\| ([\w-]+) \| (\w+) \| (\w+) \| ([^|]*) \| ([^|]*) \|'

    for match in re.finditer(table_pattern, content):
        req_id = match.group(1).strip()
        req_type = match.group(2).strip()
        priority = match.group(3).strip()
        us_raw = match.group(4).strip()
        tc_raw = match.group(5).strip()

        # Skip header row
        if req_id == "Requirement":
            continue

        # Parse user stories (e.g., "US-001" or "US-001, US-002" or "-")
        user_stories = []
        if us_raw and us_raw != "-":
            us_matches = re.findall(r'US-\d+', us_raw)
            user_stories = us_matches

        # Parse test cases (e.g., "TC-001, TC-002, TC-003, TC-004, TC-005 (+5)")
        test_cases = []
        if tc_raw and tc_raw != "-":
            tc_matches = re.findall(r'TC-\d+', tc_raw)
            test_cases = tc_matches

        entries.append({
            "req_id": req_id,
            "type": req_type,
            "priority": priority,
            "user_stories": user_stories,
            "test_cases": test_cases
        })

    return entries


def parse_data_dictionary_md(filepath: Path) -> Dict[str, Any]:
    """
    Parse data_dictionary.md and extract entities and relationships.

    Args:
        filepath: Path to the data_dictionary.md file

    Returns:
        Dict with 'entities', 'relationships', and 'glossary'
    """
    content = filepath.read_text(encoding="utf-8")
    result = {
        "entities": [],
        "relationships": [],
        "glossary": []
    }

    # Parse entities
    # Format: ### EntityName\nDescription\n*Source Requirements:* REQ-XXX\n| Attribute | ...
    entity_pattern = r'### (\w+)\n\n([^\n]+)\n\n\*Source Requirements:\*\s*([^\n]+)'

    for match in re.finditer(entity_pattern, content):
        entity_name = match.group(1).strip()
        description = match.group(2).strip()
        source_reqs = [r.strip() for r in match.group(3).split(',')]

        # Find the attribute table that follows
        entity_start = match.end()
        entity_section = content[entity_start:entity_start + 2000]  # Look ahead

        attributes = []
        attr_pattern = r'\| (\w+) \| (\w+) \| (Yes|No) \| ([^|]*) \|'
        for attr_match in re.finditer(attr_pattern, entity_section):
            attr_name = attr_match.group(1).strip()
            if attr_name == "Attribute":  # Skip header
                continue
            attributes.append({
                "name": attr_name,
                "type": attr_match.group(2).strip(),
                "required": attr_match.group(3).strip() == "Yes",
                "description": attr_match.group(4).strip()
            })

        result["entities"].append({
            "name": entity_name,
            "description": description,
            "source_requirements": source_reqs,
            "attributes": attributes
        })

    # Parse relationships
    # Format: | Relationship | Source | Target | Cardinality | Description |
    rel_section = content.split("## Relationships")[-1].split("## Glossary")[0] if "## Relationships" in content else ""
    rel_pattern = r'\| ([\w_]+) \| (\w+) \| (\w+) \| ([^|]+) \| ([^|]*) \|'

    for match in re.finditer(rel_pattern, rel_section):
        rel_name = match.group(1).strip()
        if rel_name == "Relationship":  # Skip header
            continue
        result["relationships"].append({
            "name": rel_name,
            "source": match.group(2).strip(),
            "target": match.group(3).strip(),
            "cardinality": match.group(4).strip(),
            "description": match.group(5).strip()
        })

    # Parse glossary
    # Format: ### Term\nDefinition
    glossary_section = content.split("## Glossary")[-1] if "## Glossary" in content else ""
    glossary_pattern = r'### ([^\n]+)\n\n([^\n#]+)'

    for match in re.finditer(glossary_pattern, glossary_section):
        result["glossary"].append({
            "term": match.group(1).strip(),
            "definition": match.group(2).strip()
        })

    return result


def parse_work_breakdown_md(filepath: Path) -> List[Dict]:
    """
    Parse feature_breakdown.md and extract features/work packages.

    Args:
        filepath: Path to the feature_breakdown.md file

    Returns:
        List of features with their requirements
    """
    content = filepath.read_text(encoding="utf-8")
    features = []

    # Pattern: ### FEAT-XXX: Title\n**Priority:** XXX\n**Complexity:** XXX\n...Requirements:
    feat_pattern = r'### (FEAT-\d+): ([^\n]+)\n\n\*\*Priority:\*\*\s*(\w+)\n\*\*Complexity:\*\*\s*(\w+)'

    for match in re.finditer(feat_pattern, content):
        feat_id = match.group(1).strip()
        title = match.group(2).strip()
        priority = match.group(3).strip()
        complexity = match.group(4).strip()

        # Find requirements list that follows
        feat_start = match.end()
        feat_section = content[feat_start:feat_start + 2000]

        requirements = []
        # Look for **Requirements:** section with list items
        req_section = feat_section.split("**Requirements:**")[-1].split("###")[0] if "**Requirements:**" in feat_section else ""
        req_matches = re.findall(r'- ([\w-]+)', req_section)
        requirements = req_matches

        features.append({
            "id": feat_id,
            "title": title,
            "priority": priority,
            "complexity": complexity,
            "requirements": requirements
        })

    return features


def parse_api_documentation_md(filepath: Path) -> List[Dict]:
    """
    Parse api_documentation.md and extract API endpoints.

    Args:
        filepath: Path to the api_documentation.md file

    Returns:
        List of API endpoints with method, path, description
    """
    content = filepath.read_text(encoding="utf-8")
    endpoints = []

    # Supports both old format (### METHOD /path) and new format (#### `METHOD` /path)
    endpoint_pattern = (
        r'#{3,4}\s+`?(GET|POST|PUT|DELETE|PATCH)`?\s+([^\n]+)\n+'
        r'(?:\*\*([^\n*]+)\*\*\n+)?'          # **Bold title** (optional)
        r'(?:([^\n*][^\n]*)\n+)?'              # Description line (optional, non-bold)
        r'(?:\*Requirement:\*\s*([^\n]*))?'    # *Requirement:* ID (optional)
    )

    for match in re.finditer(endpoint_pattern, content):
        method = match.group(1).strip()
        path = match.group(2).strip()
        title = match.group(3).strip() if match.group(3) else ""
        description = match.group(4).strip() if match.group(4) else title
        req_id = match.group(5).strip() if match.group(5) else ""

        # Generate id matching nodeFactory format: API-METHOD-path-segments
        sanitized_path = re.sub(r'[/{}]', '-', path).strip('-')
        sanitized_path = re.sub(r'-+', '-', sanitized_path)
        api_id = f"API-{method}-{sanitized_path}"

        ep = {
            "id": api_id,
            "method": method,
            "path": path,
            "description": description or title,
        }
        if req_id:
            ep["parent_requirement_id"] = req_id
        endpoints.append(ep)

    return endpoints


def parse_screen_markdown_files(screens_dir: Path) -> List[Dict]:
    """Parse all screen-*.md files from ui_design/screens/ directory.

    Expected format:
    # <Screen Title>
    **ID:** `SCREEN-001`
    **Route:** `/settings/2fa`
    **Layout:** single-column

    ## Components Used
    - `COMP-001`
    - `COMP-002`

    ## Data Requirements
    - `GET /api/settings/2fa/status`
    - `POST /api/settings/2fa/enable`

    ## Related User Story
    `US-002`

    ## Wireframe
    ```
    <ASCII wireframe>
    ```

    ## Component Layout
    | ID | Name | X | Y | W | H |
    |-----|------|---|---|---|---|
    ...

    Args:
        screens_dir: Path to the ui_design/screens/ directory

    Returns:
        List of screen dictionaries with metadata
    """
    screens = []

    if not screens_dir.exists():
        return screens

    for md_file in sorted(screens_dir.glob("screen-*.md")):
        try:
            content = md_file.read_text(encoding="utf-8")

            # Extract metadata
            screen = {}

            # ID from **ID:** `SCREEN-001`
            id_match = re.search(r'\*\*ID:\*\*\s+`([^`]+)`', content)
            if id_match:
                screen['id'] = id_match.group(1)

            # Route from **Route:** `/path`
            route_match = re.search(r'\*\*Route:\*\*\s+`([^`]+)`', content)
            if route_match:
                screen['route'] = route_match.group(1)

            # Layout from **Layout:** single-column
            layout_match = re.search(r'\*\*Layout:\*\*\s+(\S+)', content)
            if layout_match:
                screen['layout'] = layout_match.group(1)

            # Title (first heading)
            title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
            if title_match:
                screen['name'] = title_match.group(1).strip()

            # Components Used section
            components_section = re.search(
                r'## Components Used\s*\n((?:- `[^`]+`\s*\n?)+)',
                content
            )
            if components_section:
                comp_lines = components_section.group(1)
                screen['components_used'] = re.findall(r'`([^`]+)`', comp_lines)
            else:
                screen['components_used'] = []

            # Data Requirements (API endpoints)
            data_section = re.search(
                r'## Data Requirements\s*\n((?:- `[^`]+`\s*\n?)+)',
                content
            )
            if data_section:
                data_lines = data_section.group(1)
                screen['api_endpoints'] = re.findall(r'`([^`]+)`', data_lines)
            else:
                screen['api_endpoints'] = []

            # Related User Story
            story_match = re.search(r'## Related User Story\s*\n`([^`]+)`', content)
            if story_match:
                screen['user_story_id'] = story_match.group(1)

            # Wireframe (code block after ## Wireframe)
            wireframe_match = re.search(
                r'## Wireframe\s*\n```[^\n]*\n(.*?)```',
                content,
                re.DOTALL
            )
            if wireframe_match:
                screen['wireframe'] = wireframe_match.group(1).strip()

            # Component Layout table
            layout_section = re.search(
                r'## Component Layout\s*\n\|[^\n]+\|\s*\n\|[-:| ]+\|\s*\n((?:\|[^\n]+\|\s*\n?)+)',
                content
            )
            if layout_section:
                table_rows = layout_section.group(1)
                screen['component_positions'] = []
                for row in table_rows.strip().split('\n'):
                    cells = [c.strip() for c in row.split('|')[1:-1]]  # Skip first/last empty
                    if len(cells) >= 6:
                        screen['component_positions'].append({
                            'id': cells[0],
                            'name': cells[1],
                            'x': int(cells[2]) if cells[2].isdigit() else 0,
                            'y': int(cells[3]) if cells[3].isdigit() else 0,
                            'w': int(cells[4]) if cells[4].isdigit() else 0,
                            'h': int(cells[5]) if cells[5].isdigit() else 0
                        })

            screens.append(screen)

        except Exception as e:
            print(f"  [WARN] Could not parse screen file {md_file.name}: {e}")

    return screens


def parse_state_machines_json(file_path: Path) -> List[dict]:
    """Parse state_machines/state_machines.json.

    Expected format:
    [
      {
        "entity": "user_registration",
        "description": "...",
        "states": ["not_started", "phone_entered", ...],
        "initial_state": "not_started",
        "final_states": ["completed", "failed"],
        "transitions": [
          {
            "from_state": "...",
            "to_state": "...",
            "trigger": "...",
            "guard": "...",
            "action": "..."
          }
        ],
        "mermaid_diagram": "...",
        "source_requirements": ["WA-AUTH-001"]
      }
    ]

    Args:
        file_path: Path to state_machines.json

    Returns:
        List of state machine dicts
    """
    if not file_path.exists():
        return []

    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        state_machines = []
        for sm in data:
            # Generate ID from entity name
            entity = sm.get("entity", "")
            sm_id = f"SM-{entity.upper().replace('_', '-')}"

            state_machines.append({
                "id": sm_id,
                "entity": entity,
                "name": sm.get("description", entity.replace("_", " ").title()),
                "states": sm.get("states", []),
                "initial_state": sm.get("initial_state"),
                "final_states": sm.get("final_states", []),
                "transition_count": len(sm.get("transitions", [])),
                "transitions": sm.get("transitions", []),
                "mermaid_code": sm.get("mermaid_diagram", ""),
                "source_requirements": sm.get("source_requirements", [])
            })

        return state_machines

    except Exception as e:
        print(f"  [WARN] Could not parse state_machines.json: {e}")
        return []


def parse_infrastructure_json(file_path: Path) -> dict:
    """Parse infrastructure/infrastructure.json.

    Actual format from infrastructure generator:
    {
      "project_name": "...",
      "env_vars": {...},
      "docker_compose": "yaml string with services",
      "dockerfile": "...",
      "k8s_deployment": "...",
      "k8s_service": "...",
      "k8s_configmap": "...",
      "ci_pipeline": "..."
    }

    Args:
        file_path: Path to infrastructure.json

    Returns:
        Infrastructure dict with extracted services, or None if file doesn't exist
    """
    if not file_path.exists():
        return None

    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        # Extract services from docker_compose YAML
        services = []
        docker_compose = data.get("docker_compose", "")

        # Simple regex extraction of service names from docker-compose
        # Format: "  servicename:" at start of line
        service_pattern = re.compile(r'^  (\w+):$', re.MULTILINE)
        service_matches = service_pattern.findall(docker_compose)

        for i, service_name in enumerate(service_matches):
            # Skip top-level docker-compose keys
            if service_name in ["services", "volumes", "networks"]:
                continue

            # Extract image for technology detection
            image_pattern = re.compile(rf'^\s*image:\s*(.+?)(?:\s|$)', re.MULTILINE)
            lines_after_service = docker_compose.split(f'  {service_name}:')[1].split('\n  ')[0] if f'  {service_name}:' in docker_compose else ""
            image_match = image_pattern.search(lines_after_service)
            technology = image_match.group(1) if image_match else service_name

            services.append({
                "id": f"SVC-{service_name.upper().replace('-', '_')}",
                "name": service_name,
                "technology": technology,
                "source": "docker-compose"
            })

        return {
            "project_name": data.get("project_name"),
            "architecture_style": "containerized" if docker_compose else "unknown",
            "services": services,
            "service_count": len(services),
            "env_vars": data.get("env_vars", {}),
            "has_dockerfile": bool(data.get("dockerfile")),
            "has_k8s": bool(data.get("k8s_deployment")),
            "has_ci": bool(data.get("ci_pipeline"))
        }

    except Exception as e:
        print(f"  [WARN] Could not parse infrastructure.json: {e}")
        return None


def parse_ui_compositions_json(compositions_dir: Path) -> List[dict]:
    """Parse ui_design/compositions/*.json files.

    Expected format (per file):
    {
      "route": "/settings/2fa",
      "screen_name": "2FA Settings",
      "user_stories": ["US-002"],
      "components": [
        {
          "component_id": "COMP-001",
          "component_name": "Button",
          "props": {"variant": "primary", "size": "md"},
          "position": "footer",
          "responsive": {...}
        }
      ]
    }

    Args:
        compositions_dir: Path to ui_design/compositions/ directory

    Returns:
        List of composition dicts
    """
    compositions = []

    if not compositions_dir.exists():
        return compositions

    for json_file in sorted(compositions_dir.glob("*.json")):
        try:
            with open(json_file, encoding="utf-8") as f:
                comp = json.load(f)

            # Generate ID from filename
            comp_id = f"COMP-{json_file.stem.upper().replace('_', '-')}"

            compositions.append({
                "id": comp_id,
                "route": comp.get("route", ""),
                "screen_name": comp.get("screen_name", json_file.stem),
                "user_stories": comp.get("user_stories", []),
                "components": comp.get("components", []),
                "component_count": len(comp.get("components", [])),
                "file_name": json_file.name
            })

        except Exception as e:
            print(f"  [WARN] Could not parse {json_file.name}: {e}")

    return compositions


def parse_test_factories_json(file_path: Path) -> List[dict]:
    """Parse testing/factories/factories.json.

    Expected format:
    [
      {
        "entity_name": "user",
        "table_name": "user",
        "fields": [
          {
            "name": "user_id",
            "data_type": "uuid",
            "faker_method": "factory.LazyFunction(uuid4)",
            "is_fk": false
          }
        ]
      }
    ]

    Args:
        file_path: Path to factories.json

    Returns:
        List of factory dicts
    """
    if not file_path.exists():
        return []

    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        factories = []
        for factory in data:
            entity = factory.get("entity_name", "")
            factory_id = f"FACTORY-{entity.upper().replace('_', '-')}"

            factories.append({
                "id": factory_id,
                "entity_name": entity,
                "table_name": factory.get("table_name", entity),
                "field_count": len(factory.get("fields", [])),
                "fields": factory.get("fields", [])
            })

        return factories

    except Exception as e:
        print(f"  [WARN] Could not parse factories.json: {e}")
        return []


def parse_architecture_json(file_path: Path) -> dict:
    """Parse architecture/architecture.json.

    Contains the full logical microservice architecture with services,
    dependencies, responsibilities, and C4/deployment/data-flow diagrams.

    Args:
        file_path: Path to architecture.json

    Returns:
        Architecture dict with enriched services, or None if file doesn't exist
    """
    if not file_path.exists():
        return None

    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        # Enrich services with IDs
        services = data.get("services", [])
        for i, service in enumerate(services):
            name = service.get("name", f"service-{i}")
            service["id"] = f"ARCH-{name.upper().replace('-', '_')}"

        # Categorize services by type
        services_by_type: Dict[str, list] = {}
        for service in services:
            svc_type = service.get("type", "unknown")
            if svc_type not in services_by_type:
                services_by_type[svc_type] = []
            services_by_type[svc_type].append(service)

        # Extract diagrams from top-level keys
        diagrams = []
        diagram_keys = [
            "c4_context_diagram",
            "c4_container_diagram",
            "deployment_diagram",
            "data_flow_diagram",
        ]
        for diagram_type in diagram_keys:
            diagram_code = data.get(diagram_type)
            if diagram_code:
                diagrams.append({
                    "id": f"ARCH-DIAGRAM-{diagram_type.upper().replace('_', '-')}",
                    "type": diagram_type.replace("_diagram", ""),
                    "mermaid_code": diagram_code,
                    "title": diagram_type.replace("_", " ").title(),
                })

        return {
            "project_name": data.get("project_name"),
            "architecture_pattern": data.get("architecture_pattern"),
            "communication_patterns": data.get("communication_patterns", []),
            "services": services,
            "service_count": len(services),
            "services_by_type": services_by_type,
            "diagrams": diagrams,
            "api_count": len(services_by_type.get("api", [])),
            "database_count": len(services_by_type.get("database", [])),
            "worker_count": len(services_by_type.get("worker", [])),
            "gateway_count": len(services_by_type.get("gateway", [])),
        }

    except Exception as e:
        print(f"  [WARN] Could not parse architecture.json: {e}")
        return None
