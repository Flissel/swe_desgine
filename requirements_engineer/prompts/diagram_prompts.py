"""
Diagram generation prompts for Mermaid diagrams
"""

from typing import List, Dict, Any


DIAGRAM_SYSTEM_PROMPT = """You are an expert at creating Mermaid diagrams for software documentation.
Generate clear, well-structured diagrams that accurately represent the requirements.

Guidelines:
- Use proper Mermaid syntax
- Keep diagrams readable (not too complex)
- Use meaningful node IDs and labels
- Include relevant relationships
- Add notes where helpful
"""

FLOWCHART_PROMPT = """
## Requirements

{requirements_summary}

## Task

Create a Mermaid flowchart diagram showing the main process flows described in these requirements.

- Use `graph TD` for top-down layout
- Show decision points with diamond shapes
- Include start and end nodes
- Label all transitions

```mermaid
graph TD
    Start([Start]) --> A[First Step]
    A --> B{{Decision?}}
    B -->|Yes| C[Action]
    B -->|No| D[Other Action]
    C --> End([End])
    D --> End
```

Generate the flowchart:
"""

SEQUENCE_PROMPT = """
## Requirements

{requirements_summary}

## Task

Create a Mermaid sequence diagram showing the interactions between system components and actors.

- Include all relevant actors (users, systems)
- Show the sequence of messages
- Include activation boxes where appropriate
- Add notes for complex interactions

```mermaid
sequenceDiagram
    actor User
    participant System
    participant Database

    User->>System: Request
    activate System
    System->>Database: Query
    Database-->>System: Result
    System-->>User: Response
    deactivate System
```

Generate the sequence diagram:
"""

CLASS_PROMPT = """
## Requirements

{requirements_summary}

## Task

Create a Mermaid class diagram showing the domain model entities and their relationships.

- Include main entities/classes
- Show attributes and methods
- Indicate relationships (inheritance, composition, association)
- Use proper cardinality

```mermaid
classDiagram
    class User {{
        +String id
        +String email
        +login()
        +logout()
    }}
    class Order {{
        +String id
        +Date createdAt
        +submit()
    }}
    User "1" --> "*" Order : places
```

Generate the class diagram:
"""

ER_PROMPT = """
## Requirements

{requirements_summary}

## Task

Create a Mermaid ER diagram showing the data model and relationships.

- Include all entities
- Show primary and foreign keys
- Indicate relationship cardinality
- Use proper data types

```mermaid
erDiagram
    USER ||--o{{ ORDER : places
    USER {{
        string id PK
        string email
        string name
    }}
    ORDER {{
        string id PK
        string user_id FK
        date created_at
        float total
    }}
```

Generate the ER diagram:
"""

STATE_PROMPT = """
## Requirements

{requirements_summary}

## Task

Create a Mermaid state diagram showing the states and transitions of the main entities.

- Show all valid states
- Include transitions with triggers
- Add guards where applicable
- Include initial and final states

```mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> Submitted : submit
    Submitted --> Approved : approve
    Submitted --> Rejected : reject
    Approved --> [*]
    Rejected --> Draft : revise
```

Generate the state diagram:
"""

C4_PROMPT = """
## Requirements

{requirements_summary}

## Task

Create a Mermaid C4 Context diagram showing the system context and external dependencies.

- Show the main system
- Include external users/actors
- Show external systems
- Indicate relationships

```mermaid
C4Context
    title System Context Diagram

    Person(user, "User", "A user of the system")
    System(system, "Main System", "The system being designed")
    System_Ext(external, "External API", "Third-party service")

    Rel(user, system, "Uses")
    Rel(system, external, "Integrates with")
```

Generate the C4 diagram:
"""


# ============================================================================
# DIAGRAM TYPE SELECTION PROMPT
# ============================================================================

DIAGRAM_SELECTION_PROMPT = """Analyze the following requirement and select which diagram types would be most useful to visualize it.

## Requirement

**ID:** {requirement_id}
**Title:** {requirement_title}
**Type:** {requirement_type}
**Description:**
{requirement_description}

## Available Diagram Types

- **flowchart**: Process flows, workflows, decision trees, step-by-step procedures
- **sequenceDiagram**: Interactions between actors/systems, API calls, message sequences
- **classDiagram**: Domain models, entities and relationships, object structures
- **erDiagram**: Database structures, entity-relationships, data models
- **stateDiagram**: State machines, lifecycle management, status transitions
- **C4Context**: System architecture, context diagrams, external dependencies

## Selection Criteria

Consider:
1. Does the requirement describe a **process or workflow**? → flowchart
2. Does it involve **multiple actors or systems interacting**? → sequenceDiagram
3. Does it define **entities, objects, or domain concepts**? → classDiagram
4. Does it describe **data storage or database relationships**? → erDiagram
5. Does it involve **states, status changes, or lifecycles**? → stateDiagram
6. Does it describe **system integration or architecture**? → C4Context

## Task

Select 2-3 diagram types that would best visualize this requirement.
Respond ONLY with a JSON array of diagram type names. Example:

["flowchart", "sequenceDiagram"]

Your selection:"""


DIAGRAM_SELECTION_SYSTEM_PROMPT = """You are an expert requirements analyst who selects the most appropriate diagram types for visualizing software requirements.

Rules:
- Always select 2-3 diagram types (minimum 2, maximum 3)
- Choose types that add unique value (don't select redundant types)
- Consider the requirement type (functional, non-functional, data, UI, etc.)
- Respond ONLY with a valid JSON array, nothing else"""


DIAGRAM_PROMPTS_MAP = {
    "flowchart": FLOWCHART_PROMPT,
    "sequenceDiagram": SEQUENCE_PROMPT,
    "classDiagram": CLASS_PROMPT,
    "erDiagram": ER_PROMPT,
    "stateDiagram": STATE_PROMPT,
    "C4Context": C4_PROMPT
}


def format_requirements_summary(requirements: List) -> str:
    """Create a summary of requirements for diagram generation."""
    lines = []
    for req in requirements:
        lines.append(f"- **{req.requirement_id}**: {req.title} - {req.description[:100]}...")
    return "\n".join(lines)


def get_diagram_prompt(requirements: List, diagram_type: str) -> Dict[str, str]:
    """
    Generate a diagram prompt for a specific diagram type.

    Args:
        requirements: List of RequirementNode objects
        diagram_type: Type of diagram to generate

    Returns:
        Formatted prompt dictionary
    """
    template = DIAGRAM_PROMPTS_MAP.get(diagram_type, FLOWCHART_PROMPT)

    prompt = template.format(
        requirements_summary=format_requirements_summary(requirements)
    )

    return {
        "System": DIAGRAM_SYSTEM_PROMPT,
        "Task": prompt,
        "DiagramType": diagram_type
    }


DIAGRAM_PROMPTS = {
    "system": DIAGRAM_SYSTEM_PROMPT,
    "flowchart": FLOWCHART_PROMPT,
    "sequence": SEQUENCE_PROMPT,
    "class": CLASS_PROMPT,
    "er": ER_PROMPT,
    "state": STATE_PROMPT,
    "c4": C4_PROMPT
}
