"""
Validation prompts for Stage 4: Validation
"""

from typing import List, Dict, Any


SYSTEM_PROMPT = """You are an experienced Requirements Validator.
Your task is to validate requirements for quality, completeness, and consistency.

Guidelines:
- Check for completeness (all aspects covered)
- Verify consistency (no conflicts)
- Assess testability (can be verified)
- Evaluate clarity (unambiguous language)
- Review feasibility (can be implemented)
- Confirm traceability (relationships clear)
"""

VALIDATION_PROMPT = """
## Requirements to Validate

{requirements_list}

## Validation Thresholds

- Completeness: {min_completeness}
- Consistency: {min_consistency}
- Testability: {min_testability}
- Clarity: {min_clarity}
- Feasibility: {min_feasibility}
- Traceability: {min_traceability}

## Task

Validate each requirement and provide scores and feedback:

1. **Completeness Score** (0.0-1.0): Are all necessary details provided?
2. **Consistency Score** (0.0-1.0): No conflicts with other requirements?
3. **Testability Score** (0.0-1.0): Can this be objectively verified?
4. **Clarity Score** (0.0-1.0): Is the language unambiguous?
5. **Feasibility Score** (0.0-1.0): Can this be implemented?
6. **Traceability Score** (0.0-1.0): Are relationships to other requirements clear?

{iteration_context}

Respond with a JSON object:
```json
{{
  "validations": [
    {{
      "requirement_id": "REQ-001",
      "completeness_score": 0.85,
      "consistency_score": 0.90,
      "testability_score": 0.80,
      "clarity_score": 0.75,
      "feasibility_score": 0.95,
      "traceability_score": 0.70,
      "issues": ["..."],
      "suggestions": ["..."],
      "status": "validated"
    }}
  ],
  "overall_assessment": {{
    "total_validated": 10,
    "total_failed": 2,
    "critical_issues": ["..."],
    "recommendations": ["..."]
  }}
}}
```
"""


def format_requirements_for_validation(requirements: List) -> str:
    """Format requirements for validation prompt."""
    lines = []
    for req in requirements:
        lines.append(f"### {req.requirement_id}: {req.title}")
        lines.append(f"- **Description**: {req.description}")
        lines.append(f"- **Type**: {req.type}")
        lines.append(f"- **Priority**: {req.priority}")
        if req.acceptance_criteria:
            lines.append("- **Acceptance Criteria**:")
            for ac in req.acceptance_criteria:
                lines.append(f"  - {ac}")
        if req.dependencies:
            lines.append(f"- **Dependencies**: {', '.join(req.dependencies)}")
        lines.append("")
    return "\n".join(lines)


def get_validation_prompt(
    requirements: List,
    thresholds: Dict[str, float],
    iteration: int
) -> Dict[str, str]:
    """
    Generate the validation prompt for a given iteration.

    Args:
        requirements: List of RequirementNode objects
        thresholds: Validation thresholds from config
        iteration: Current iteration number

    Returns:
        Formatted prompt dictionary
    """
    if iteration == 0:
        iteration_context = """
This is the initial validation. Focus on:
- Identifying major gaps
- Finding obvious inconsistencies
- Flagging unclear requirements
"""
    else:
        iteration_context = f"""
This is iteration {iteration + 1}. Focus on:
- Re-validating previously failed requirements
- Fine-tuning scores
- Verifying improvements
"""

    prompt = VALIDATION_PROMPT.format(
        requirements_list=format_requirements_for_validation(requirements),
        min_completeness=thresholds.get("min_completeness", 0.8),
        min_consistency=thresholds.get("min_consistency", 0.9),
        min_testability=thresholds.get("min_testability", 0.75),
        min_clarity=thresholds.get("min_clarity", 0.8),
        min_feasibility=thresholds.get("min_feasibility", 0.75),
        min_traceability=thresholds.get("min_traceability", 0.8),
        iteration_context=iteration_context
    )

    return {
        "System": SYSTEM_PROMPT,
        "Task": prompt
    }


VALIDATION_PROMPTS = {
    "system": SYSTEM_PROMPT,
    "validation": VALIDATION_PROMPT
}
