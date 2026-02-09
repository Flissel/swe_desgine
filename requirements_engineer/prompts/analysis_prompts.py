"""
Analysis prompts for Stage 2: Analysis
"""

from typing import List, Dict, Any


SYSTEM_PROMPT = """You are an experienced Requirements Analyst.
Your task is to analyze, decompose, and classify requirements.

Guidelines:
- Decompose complex requirements into atomic units
- Identify dependencies between requirements
- Detect conflicts and inconsistencies
- Classify requirements accurately
- Apply MoSCoW prioritization
- Build traceability relationships
"""

ANALYSIS_PROMPT = """
## Requirements to Analyze

{requirements_list}

## Task

Analyze the above requirements and provide:

1. **Decomposition**: Break complex requirements into smaller, atomic requirements
2. **Dependencies**: Identify which requirements depend on others
3. **Conflicts**: Find any conflicting requirements
4. **Classifications**: Verify/correct the type classification
5. **Priorities**: Review and adjust priorities based on dependencies
6. **Traceability**: Group related requirements

{iteration_context}

Respond with a JSON object:
```json
{{
  "decomposed_requirements": [
    {{
      "original_id": "REQ-001",
      "sub_requirements": [
        {{
          "title": "...",
          "description": "...",
          "type": "functional",
          "priority": "must"
        }}
      ]
    }}
  ],
  "dependencies": [
    {{"from": "REQ-001", "to": "REQ-002", "type": "depends_on"}}
  ],
  "conflicts": [
    {{"req1": "REQ-003", "req2": "REQ-004", "description": "..."}}
  ],
  "priority_adjustments": [
    {{"requirement_id": "REQ-005", "new_priority": "must", "reason": "..."}}
  ],
  "requirement_groups": [
    {{"name": "User Authentication", "requirements": ["REQ-001", "REQ-002"]}}
  ]
}}
```
"""


def format_requirements_for_analysis(requirements: List) -> str:
    """Format requirements for analysis prompt."""
    lines = []
    for req in requirements:
        lines.append(f"### {req.requirement_id}: {req.title}")
        lines.append(f"- **Type**: {req.type}")
        lines.append(f"- **Priority**: {req.priority}")
        lines.append(f"- **Description**: {req.description}")
        if req.acceptance_criteria:
            lines.append(f"- **Acceptance Criteria**: {', '.join(req.acceptance_criteria)}")
        lines.append("")
    return "\n".join(lines)


def get_analysis_prompt(requirements: List, iteration: int) -> Dict[str, str]:
    """
    Generate the analysis prompt for a given iteration.

    Args:
        requirements: List of RequirementNode objects
        iteration: Current iteration number

    Returns:
        Formatted prompt dictionary
    """
    if iteration == 0:
        iteration_context = """
This is the initial analysis. Focus on:
- Finding obvious dependencies
- Identifying clear conflicts
- Grouping related requirements
"""
    else:
        iteration_context = f"""
This is iteration {iteration + 1}. Focus on:
- Fine-grained decomposition
- Subtle dependencies
- Implicit conflicts
- Optimizing priority order
"""

    prompt = ANALYSIS_PROMPT.format(
        requirements_list=format_requirements_for_analysis(requirements),
        iteration_context=iteration_context
    )

    return {
        "System": SYSTEM_PROMPT,
        "Task": prompt
    }


ANALYSIS_PROMPTS = {
    "system": SYSTEM_PROMPT,
    "analysis": ANALYSIS_PROMPT
}
