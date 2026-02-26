"""
Converter: arch_team ChunkMiner DTOs -> RE System v2 JSON

This module converts the output from arch_team's ChunkMinerAgent
into the RE System v2 input format.

arch_team DTO Format:
{
    "req_id": "REQ-abc123-001",
    "title": "The system must...",
    "tag": "functional|security|performance|...",
    "priority": "must|should|may",
    "measurable_criteria": "...",
    "actors": ["user", "admin"],
    "evidence": "...",
    "evidence_refs": [{"sourceFile": "...", "sha1": "...", "chunkIndex": 0}]
}

RE System v2 Format:
{
    "project": {"name": "...", "domain": "...", ...},
    "requirements": [{"id": "REQ-001", "title": "...", "description": "...", ...}],
    "constraints": {...},
    "agents": [],
    "integrations": []
}
"""

from typing import List, Dict, Any, Optional
import re


# Mapping: arch_team tag -> RE System v2 category
TAG_TO_CATEGORY = {
    "functional": "functional",
    "security": "security",
    "performance": "performance",
    "usability": "frontend",        # UI-focused
    "reliability": "non_functional",
    "compliance": "non_functional",
    "interface": "integration",     # API/interfaces
    "data": "backend",              # Data layer
    "constraint": "non_functional",
    # Additional mappings
    "ux": "frontend",
    "ops": "non_functional"
}

# Mapping: arch_team priority -> RE System v2 priority
PRIORITY_MAP = {
    "must": "must",
    "shall": "must",
    "should": "should",
    "may": "could",
    "can": "could"
}


def convert_arch_team_to_v2(
    items: List[Dict[str, Any]],
    project_name: str,
    project_domain: str = "general",
    project_description: str = "",
    autonomy_level: str = "medium",
    target_users: Optional[List[str]] = None,
    constraints: Optional[Dict[str, Any]] = None,
    agents: Optional[List[Dict[str, Any]]] = None,
    integrations: Optional[List[Dict[str, Any]]] = None,
    renumber_ids: bool = True,
    preserve_metadata: bool = True
) -> Dict[str, Any]:
    """
    Convert arch_team ChunkMiner output to RE System v2 JSON format.

    Args:
        items: List of arch_team requirement DTOs
        project_name: Name of the project
        project_domain: Domain (Finance, Healthcare, E-Commerce, etc.)
        project_description: Optional project description
        autonomy_level: none/low/medium/high/full
        target_users: List of target user personas
        constraints: Optional constraints dict (technical, regulatory, etc.)
        agents: Optional list of agent definitions
        integrations: Optional list of integration definitions
        renumber_ids: If True, renumber to REQ-001, REQ-002...
        preserve_metadata: If True, preserve arch_team evidence as _metadata

    Returns:
        RE System v2 compatible JSON structure
    """
    requirements = []

    for idx, item in enumerate(items):
        req = _convert_single_requirement(
            item=item,
            index=idx,
            renumber_ids=renumber_ids,
            preserve_metadata=preserve_metadata
        )
        requirements.append(req)

    # Build project metadata
    project = {
        "name": project_name,
        "domain": project_domain,
        "autonomy_level": autonomy_level,
        "target_users": target_users or []
    }

    if project_description:
        project["description"] = project_description

    # Build final v2 structure
    return {
        "project": project,
        "requirements": requirements,
        "constraints": constraints or {},
        "agents": agents or [],
        "integrations": integrations or []
    }


def _convert_single_requirement(
    item: Dict[str, Any],
    index: int,
    renumber_ids: bool = True,
    preserve_metadata: bool = True
) -> Dict[str, Any]:
    """
    Convert a single arch_team DTO to RE System v2 requirement format.

    Args:
        item: arch_team requirement DTO
        index: Index for ID generation
        renumber_ids: Whether to renumber IDs
        preserve_metadata: Whether to preserve arch_team metadata

    Returns:
        RE System v2 requirement dict
    """
    # ID handling
    if renumber_ids:
        req_id = f"REQ-{index + 1:03d}"
    else:
        req_id = item.get("req_id", f"REQ-{index + 1:03d}")
        # Ensure ID matches pattern
        if not re.match(r"^(REQ|FR|NFR|AUTO|STRAT|US|EPIC)-[A-Z0-9-]+$", req_id, re.IGNORECASE):
            req_id = f"REQ-{index + 1:03d}"

    # Title extraction
    full_title = item.get("title", "")
    short_title = _extract_short_title(full_title)

    # Category mapping
    tag = item.get("tag", "functional").lower()
    category = TAG_TO_CATEGORY.get(tag, "functional")

    # Priority mapping
    priority = item.get("priority", "should").lower()
    priority = PRIORITY_MAP.get(priority, "should")

    # Acceptance criteria (wrap in array)
    criteria = item.get("measurable_criteria", "")
    acceptance_criteria = [criteria] if criteria else []

    # Tags array
    tags = [tag] if tag else []

    # Add actors to tags if present
    actors = item.get("actors", [])
    if actors:
        tags.extend([f"actor:{a}" for a in actors if a])

    # Build requirement
    req = {
        "id": req_id,
        "title": short_title,
        "description": full_title,
        "category": category,
        "priority": priority,
        "tags": list(set(tags)),  # Deduplicate
        "acceptance_criteria": acceptance_criteria
    }

    # Preserve arch_team metadata for traceability
    if preserve_metadata:
        metadata = {}
        if item.get("req_id"):
            metadata["original_req_id"] = item.get("req_id")
        if item.get("evidence"):
            metadata["evidence"] = item.get("evidence")
        if item.get("evidence_refs"):
            metadata["evidence_refs"] = item.get("evidence_refs")
        if actors:
            metadata["actors"] = actors

        if metadata:
            req["_arch_team_metadata"] = metadata

    return req


def _extract_short_title(full_title: str, max_length: int = 60) -> str:
    """
    Extract a short title from the full requirement statement.

    Removes modal verb prefixes like "The system must..." and truncates if needed.

    Args:
        full_title: Full requirement statement
        max_length: Maximum length for short title

    Returns:
        Shortened title suitable for display
    """
    if not full_title:
        return "Untitled Requirement"

    # Patterns to remove (modal verb prefixes)
    patterns = [
        r"^The\s+(system|application|service|api|platform|software)\s+(must|shall|should|may|can)\s+",
        r"^(Users?|Admins?|Administrators?|Operators?|Clients?)\s+(must|shall|should|may|can)\s+",
        r"^(It|This)\s+(must|shall|should|may|can)\s+",
    ]

    short = full_title
    for pattern in patterns:
        short = re.sub(pattern, "", short, flags=re.IGNORECASE)

    # Clean up leading/trailing whitespace
    short = short.strip()

    # Capitalize first letter
    if short:
        short = short[0].upper() + short[1:]

    # Truncate if still too long
    if len(short) > max_length:
        # Try to break at word boundary
        truncated = short[:max_length - 3]
        last_space = truncated.rfind(" ")
        if last_space > max_length // 2:
            truncated = truncated[:last_space]
        short = truncated + "..."

    return short or "Untitled Requirement"


def merge_requirements(
    extracted: List[Dict[str, Any]],
    manual: List[Dict[str, Any]],
    renumber_all: bool = True
) -> List[Dict[str, Any]]:
    """
    Merge extracted and manually added requirements.

    Args:
        extracted: Requirements extracted by arch_team
        manual: Manually added requirements
        renumber_all: Whether to renumber all requirements sequentially

    Returns:
        Merged list of requirements
    """
    all_reqs = []

    # Add extracted requirements (already in arch_team format)
    for item in extracted:
        all_reqs.append(item)

    # Add manual requirements (may already be in v2 format or need conversion)
    for item in manual:
        # Check if it's already in v2 format
        if "id" in item and "description" in item:
            # Already v2 format, just add
            all_reqs.append(item)
        else:
            # Might be in arch_team format
            all_reqs.append(item)

    return all_reqs


def validate_v2_output(output: Dict[str, Any]) -> List[str]:
    """
    Validate the generated v2 JSON against schema requirements.

    Args:
        output: Generated v2 JSON

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Check required fields
    if "project" not in output:
        errors.append("Missing required field: project")
    elif "name" not in output.get("project", {}):
        errors.append("Missing required field: project.name")

    if "requirements" not in output:
        errors.append("Missing required field: requirements")
    elif not isinstance(output.get("requirements"), list):
        errors.append("Field 'requirements' must be an array")
    else:
        for idx, req in enumerate(output["requirements"]):
            if "id" not in req:
                errors.append(f"Requirement {idx}: missing 'id'")
            if "title" not in req:
                errors.append(f"Requirement {idx}: missing 'title'")
            if "description" not in req:
                errors.append(f"Requirement {idx}: missing 'description'")

            # Validate ID pattern
            if "id" in req:
                if not re.match(r"^(REQ|FR|NFR|AUTO|STRAT|US|EPIC)-[A-Z0-9-]+$", req["id"], re.IGNORECASE):
                    errors.append(f"Requirement {idx}: invalid ID format '{req['id']}'")

            # Validate category
            valid_categories = [
                "functional", "non_functional", "strategic", "autonomy",
                "frontend", "backend", "integration", "security", "performance"
            ]
            if req.get("category") and req["category"] not in valid_categories:
                errors.append(f"Requirement {idx}: invalid category '{req['category']}'")

            # Validate priority
            valid_priorities = ["must", "should", "could", "wont"]
            if req.get("priority") and req["priority"] not in valid_priorities:
                errors.append(f"Requirement {idx}: invalid priority '{req['priority']}'")

    return errors


# Convenience function for quick conversion
def quick_convert(
    items: List[Dict[str, Any]],
    project_name: str = "Unnamed Project"
) -> Dict[str, Any]:
    """
    Quick conversion with minimal parameters.

    Args:
        items: arch_team requirement DTOs
        project_name: Project name

    Returns:
        RE System v2 JSON
    """
    return convert_arch_team_to_v2(
        items=items,
        project_name=project_name,
        renumber_ids=True,
        preserve_metadata=True
    )
