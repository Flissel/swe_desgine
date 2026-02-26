"""
Elicitation prompts for Stage 1: Discovery
"""

from typing import Dict, List, Any


SYSTEM_PROMPT = """You are an experienced Requirements Engineer specializing in software requirements elicitation.
Your task is to extract clear, actionable requirements from the provided project context.

Guidelines:
- Extract both functional and non-functional requirements
- Use clear, unambiguous language
- Each requirement should be testable
- Identify stakeholder concerns and constraints
- Flag any ambiguities that need clarification
"""

EXTRACTION_PROMPT = """
## Project Context

**Project Name:** {project_name}
**Domain:** {domain}
**Description:** {context}

## Stakeholders
{stakeholders}

## Initial Requirements (from user)
{initial_requirements}

## Constraints
{constraints}

## Task

Based on the above context, extract a comprehensive list of requirements.
For each requirement, provide:

1. **Title**: A short, descriptive name
2. **Description**: Clear explanation of what is needed
3. **Type**: functional, non_functional, or constraint
4. **Priority**: must, should, could, or wont (MoSCoW)
5. **Rationale**: Why this requirement is needed
6. **Source**: Where this requirement came from
7. **Acceptance Criteria**: How to verify the requirement is met

{iteration_context}

Respond with a JSON array of requirements:
```json
[
  {{
    "title": "...",
    "description": "...",
    "type": "functional",
    "priority": "must",
    "rationale": "...",
    "source": "...",
    "acceptance_criteria": ["...", "..."]
  }}
]
```
"""


def format_stakeholders(stakeholders: List[Dict]) -> str:
    """Format stakeholders for prompt."""
    if not stakeholders:
        return "Not specified"

    lines = []
    for s in stakeholders:
        role = s.get("role", "Unknown")
        concerns = ", ".join(s.get("concerns", []))
        lines.append(f"- **{role}**: {concerns}")
    return "\n".join(lines)


def format_constraints(constraints: Dict) -> str:
    """Format constraints for prompt."""
    if not constraints:
        return "Not specified"

    lines = []
    if "technical" in constraints:
        lines.append(f"- **Technical**: {', '.join(constraints['technical'])}")
    if "regulatory" in constraints:
        lines.append(f"- **Regulatory**: {', '.join(constraints['regulatory'])}")
    if "budget" in constraints:
        lines.append(f"- **Budget**: {constraints['budget']}")
    if "timeline" in constraints:
        lines.append(f"- **Timeline**: {constraints['timeline']}")
    return "\n".join(lines) if lines else "Not specified"


def format_initial_requirements(requirements: List[str]) -> str:
    """Format initial requirements for prompt."""
    if not requirements:
        return "None provided"
    return "\n".join(f"- {req}" for req in requirements)


def get_elicitation_prompt(
    project_input: Dict[str, Any],
    existing_requirements: List,
    iteration: int
) -> Dict[str, str]:
    """
    Generate the elicitation prompt for a given iteration.

    Args:
        project_input: Project input data
        existing_requirements: Already extracted requirements
        iteration: Current iteration number

    Returns:
        Formatted prompt dictionary
    """
    # Build iteration context
    if iteration == 0:
        iteration_context = "This is the initial extraction. Focus on capturing all core requirements."
    else:
        existing_count = len(existing_requirements)
        iteration_context = f"""
This is iteration {iteration + 1}.
We already have {existing_count} requirements extracted.
Focus on:
- Requirements we might have missed
- Edge cases and error handling
- Non-functional requirements (performance, security, usability)
- Integration points with external systems
"""

    prompt = EXTRACTION_PROMPT.format(
        project_name=project_input.get("Name", "Unknown"),
        domain=project_input.get("Domain", "custom"),
        context=project_input.get("Context", "No context provided"),
        stakeholders=format_stakeholders(project_input.get("Stakeholders", [])),
        initial_requirements=format_initial_requirements(project_input.get("Initial Requirements", [])),
        constraints=format_constraints(project_input.get("Constraints", {})),
        iteration_context=iteration_context
    )

    return {
        "System": SYSTEM_PROMPT,
        "Task": prompt
    }


# Function spec for structured output
REQUIREMENT_EXTRACTION_SPEC = {
    "name": "extract_requirements",
    "description": "Extract structured requirements from project context",
    "parameters": {
        "type": "object",
        "properties": {
            "requirements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Short descriptive name"},
                        "description": {"type": "string", "description": "Full requirement description"},
                        "type": {
                            "type": "string",
                            "enum": ["functional", "non_functional", "constraint"]
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["must", "should", "could", "wont"]
                        },
                        "rationale": {"type": "string"},
                        "source": {"type": "string"},
                        "acceptance_criteria": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["title", "description", "type", "priority"]
                }
            },
            "ambiguities": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of unclear points that need clarification"
            },
            "missing_info": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Information needed but not provided"
            }
        },
        "required": ["requirements"]
    }
}


ELICITATION_PROMPTS = {
    "system": SYSTEM_PROMPT,
    "extraction": EXTRACTION_PROMPT,
    "spec": REQUIREMENT_EXTRACTION_SPEC
}
