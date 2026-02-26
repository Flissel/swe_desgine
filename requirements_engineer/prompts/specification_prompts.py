"""
Specification prompts for Stage 3: Specification
"""

from typing import List, Dict, Any


SYSTEM_PROMPT = """You are an experienced Requirements Specifier.
Your task is to formalize requirements with precise acceptance criteria.

Guidelines:
- Write clear, unambiguous specifications
- Define measurable acceptance criteria
- Use consistent terminology
- Include all necessary details for implementation
- Consider edge cases and error scenarios
"""

SPECIFICATION_PROMPT = """
## Requirements to Specify

{requirements_list}

## Task

For each requirement, provide a formal specification:

1. **Formal Description**: Precise, unambiguous wording
2. **Acceptance Criteria**: Specific, testable conditions (Given-When-Then format)
3. **Preconditions**: What must be true before the requirement applies
4. **Postconditions**: What must be true after the requirement is satisfied
5. **Assumptions**: Any assumptions made
6. **Constraints**: Technical or business constraints
7. **Error Scenarios**: How errors should be handled

{iteration_context}

Respond with a JSON object:
```json
{{
  "specifications": [
    {{
      "requirement_id": "REQ-001",
      "formal_description": "...",
      "acceptance_criteria": [
        {{
          "given": "...",
          "when": "...",
          "then": "..."
        }}
      ],
      "preconditions": ["..."],
      "postconditions": ["..."],
      "assumptions": ["..."],
      "constraints": ["..."],
      "error_scenarios": [
        {{"scenario": "...", "expected_behavior": "..."}}
      ]
    }}
  ]
}}
```
"""


def format_requirements_for_specification(requirements: List) -> str:
    """Format requirements for specification prompt."""
    lines = []
    for req in requirements:
        lines.append(f"### {req.requirement_id}: {req.title}")
        lines.append(f"- **Description**: {req.description}")
        lines.append(f"- **Type**: {req.type}")
        lines.append(f"- **Priority**: {req.priority}")
        if req.rationale:
            lines.append(f"- **Rationale**: {req.rationale}")
        lines.append("")
    return "\n".join(lines)


def get_specification_prompt(requirements: List, iteration: int) -> Dict[str, str]:
    """
    Generate the specification prompt for a given iteration.

    Args:
        requirements: List of RequirementNode objects
        iteration: Current iteration number

    Returns:
        Formatted prompt dictionary
    """
    if iteration == 0:
        iteration_context = """
This is the initial specification. Focus on:
- Core functionality requirements
- Primary success scenarios
- Basic acceptance criteria
"""
    else:
        iteration_context = f"""
This is iteration {iteration + 1}. Focus on:
- Refining acceptance criteria
- Adding edge cases
- Error handling scenarios
- Performance and scalability criteria
"""

    prompt = SPECIFICATION_PROMPT.format(
        requirements_list=format_requirements_for_specification(requirements),
        iteration_context=iteration_context
    )

    return {
        "System": SYSTEM_PROMPT,
        "Task": prompt
    }


SPECIFICATION_PROMPTS = {
    "system": SYSTEM_PROMPT,
    "specification": SPECIFICATION_PROMPT
}
