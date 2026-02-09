"""
Markdown Parser for RE System output files.

Parses user_stories.md to extract Epics and User Stories.
"""

import re
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

    # Pattern: ### METHOD /path\n**Description:** ...\n**Request Body:**
    endpoint_pattern = r'### (GET|POST|PUT|DELETE|PATCH)\s+([^\n]+)\n+(?:\*\*Description:\*\*\s*([^\n]*))?'

    for match in re.finditer(endpoint_pattern, content):
        method = match.group(1).strip()
        path = match.group(2).strip()
        description = match.group(3).strip() if match.group(3) else ""

        endpoints.append({
            "method": method,
            "path": path,
            "description": description
        })

    return endpoints
