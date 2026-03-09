"""
Kilo Diagram Generator - Generates Mermaid diagrams using the Kilo Agent.

Uses the UserKiloAgent to generate all 6 types of Mermaid diagrams:
- Flowchart
- Sequence Diagram
- Class Diagram
- ER Diagram
- State Diagram
- C4 Context Diagram
"""

import sys
import os
import asyncio
from typing import Dict, List, Any, Optional
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from requirements_engineer.tools.mermaid_output_handler import MermaidOutputHandler
from requirements_engineer.tools.mermaid_validator import MermaidValidator, ValidationResult


# Prompt templates for each diagram type
# IMPORTANT: These prompts explicitly request the mermaid code IN THE RESPONSE (not saved to file)
DIAGRAM_PROMPTS = {
    "flowchart": """Erstelle ein Mermaid Flowchart-Diagramm für folgendes Requirement.

WICHTIG: Gib den Mermaid-Code DIREKT in deiner Antwort aus - NICHT in eine Datei speichern!

**{req_id}: {title}**
{description}

Akzeptanzkriterien:
{acceptance_criteria}

Das Flowchart soll:
- Den Hauptprozessablauf zeigen (graph TD)
- Entscheidungspunkte mit Rauten {{}}
- Start und Ende klar markieren
- Alle wichtigen Schritte enthalten

Antworte NUR mit dem Mermaid-Code in diesem Format:

```mermaid
flowchart TD
    Start([Start]) --> ...
    ...
    ... --> End([End])
```""",

    "sequence": """Erstelle ein Mermaid Sequence-Diagramm für folgendes Requirement.

WICHTIG: Gib den Mermaid-Code DIREKT in deiner Antwort aus - NICHT in eine Datei speichern!

**{req_id}: {title}**
{description}

Akzeptanzkriterien:
{acceptance_criteria}

Das Sequence-Diagramm soll:
- Alle beteiligten Akteure/Systeme zeigen
- Die Nachrichtenflüsse in korrekter Reihenfolge
- Aktivierungen wo sinnvoll

Antworte NUR mit dem Mermaid-Code in diesem Format:

```mermaid
sequenceDiagram
    participant User
    participant System
    ...
```""",

    "class": """Erstelle ein Mermaid Class-Diagramm für folgendes Requirement.

WICHTIG: Gib den Mermaid-Code DIREKT in deiner Antwort aus - NICHT in eine Datei speichern!

**{req_id}: {title}**
{description}

Akzeptanzkriterien:
{acceptance_criteria}

Das Class-Diagramm soll:
- Die Hauptentitäten/Klassen zeigen
- Wichtige Attribute und Methoden
- Beziehungen zwischen Klassen

Antworte NUR mit dem Mermaid-Code in diesem Format:

```mermaid
classDiagram
    class ClassName {{
        +attribute
        +method()
    }}
```""",

    "er": """Erstelle ein Mermaid ER-Diagramm für folgendes Requirement.

WICHTIG: Gib den Mermaid-Code DIREKT in deiner Antwort aus - NICHT in eine Datei speichern!

**{req_id}: {title}**
{description}

Akzeptanzkriterien:
{acceptance_criteria}

Das ER-Diagramm soll:
- Alle Daten-Entitäten zeigen
- Primär- und Fremdschlüssel markieren
- Beziehungen mit korrekter Kardinalität

Antworte NUR mit dem Mermaid-Code in diesem Format:

```mermaid
erDiagram
    ENTITY ||--o{{ OTHER : relationship
    ENTITY {{
        string id PK
        string name
    }}
```""",

    "state": """Erstelle ein Mermaid State-Diagramm für folgendes Requirement.

WICHTIG: Gib den Mermaid-Code DIREKT in deiner Antwort aus - NICHT in eine Datei speichern!

**{req_id}: {title}**
{description}

Akzeptanzkriterien:
{acceptance_criteria}

Das State-Diagramm soll:
- Alle möglichen Zustände zeigen
- Übergänge mit Triggern beschriften
- Start- und Endzustand markieren

Antworte NUR mit dem Mermaid-Code in diesem Format:

```mermaid
stateDiagram-v2
    [*] --> State1
    State1 --> State2 : event
    State2 --> [*]
```""",

    "c4": """Erstelle ein Mermaid C4 Context-Diagramm für folgendes Requirement.

WICHTIG: Gib den Mermaid-Code DIREKT in deiner Antwort aus - NICHT in eine Datei speichern!

**{req_id}: {title}**
{description}

Akzeptanzkriterien:
{acceptance_criteria}

Das C4 Context-Diagramm soll:
- Das Hauptsystem in der Mitte
- Externe Benutzer/Akteure
- Externe Systeme/APIs

Antworte NUR mit dem Mermaid-Code in diesem Format:

```mermaid
C4Context
    title System Context
    Person(user, "User", "Description")
    System(system, "System", "Description")
    Rel(user, system, "Uses")
```"""
}


class KiloDiagramGenerator:
    """
    Generates Mermaid diagrams using the OpenAI-compatible API directly.

    This class calls the LLM API directly to generate mermaid diagrams,
    without going through the Kilo CLI which creates files.
    """

    # Supported diagram types (internal short names)
    DIAGRAM_TYPES = ["flowchart", "sequence", "class", "er", "state", "c4"]

    # Mapping from config names (full Mermaid names) to internal short names
    TYPE_MAPPING = {
        # Full Mermaid names -> short names
        "sequenceDiagram": "sequence",
        "classDiagram": "class",
        "erDiagram": "er",
        "stateDiagram": "state",
        "stateDiagram-v2": "state",
        "C4Context": "c4",
        "c4context": "c4",
        # Short names map to themselves
        "flowchart": "flowchart",
        "sequence": "sequence",
        "class": "class",
        "er": "er",
        "state": "state",
        "c4": "c4",
    }

    @classmethod
    def normalize_type(cls, diagram_type: str) -> str:
        """Normalize diagram type name to internal short form."""
        return cls.TYPE_MAPPING.get(diagram_type, diagram_type)

    def __init__(
        self,
        model_name: str = None,
        api_key: Optional[str] = None,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: int = 300,
        # Validation settings
        validate: bool = True,
        validation_method: str = "pattern",
        retry_on_error: bool = True,
        max_retries: int = 2,
        skip_invalid: bool = False,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the Kilo Diagram Generator.

        Args:
            model_name: Name of the model to use (overrides config)
            api_key: API key (loaded from env if not provided)
            base_url: API base URL
            timeout: Timeout for API calls
            validate: Whether to validate generated diagrams
            validation_method: Validation method ('pattern', 'kroki', 'mmdc')
            retry_on_error: Whether to retry generation if validation fails
            max_retries: Maximum number of retry attempts
            skip_invalid: If True, return None for invalid diagrams instead of best effort
            config: Configuration dict with diagrams.kilo_generator section
        """
        self.config = config or {}
        diag_config = self.config.get("diagrams", {}).get("kilo_generator", {})

        self.model_name = model_name or diag_config.get("model", "openai/gpt-4o-mini")
        self.temperature = diag_config.get("temperature", 0.5)
        self.max_tokens = diag_config.get("max_tokens", 4000)
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.base_url = base_url
        self.timeout = timeout
        self.client = None
        self._initialized = False

        # Validation settings
        self.validate = validate
        self.validation_method = validation_method
        self.retry_on_error = retry_on_error
        self.max_retries = max_retries
        self.skip_invalid = skip_invalid

        # Track validation statistics
        self.validation_stats = {
            "total": 0,
            "valid": 0,
            "invalid": 0,
            "retried": 0,
            "fixed_after_retry": 0
        }

    async def initialize(self):
        """Initialize the OpenAI client."""
        if self._initialized:
            return

        # Load .env if present
        try:
            from dotenv import load_dotenv
            load_dotenv()
            if not self.api_key:
                self.api_key = os.getenv("OPENROUTER_API_KEY")
        except ImportError:
            pass

        # Create OpenAI-compatible client
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout
        )
        self._initialized = True
        print(f"  KiloDiagramGenerator initialized with model: {self.model_name}")

    def _build_prompt(
        self,
        requirement: Any,
        diagram_type: str
    ) -> str:
        """
        Build a prompt for diagram generation.

        Args:
            requirement: RequirementNode object
            diagram_type: Type of diagram to generate

        Returns:
            Formatted prompt string
        """
        template = DIAGRAM_PROMPTS.get(diagram_type, DIAGRAM_PROMPTS["flowchart"])

        # Format acceptance criteria
        ac_list = requirement.acceptance_criteria if hasattr(requirement, 'acceptance_criteria') else []
        ac_formatted = "\n".join(f"- {ac}" for ac in ac_list) if ac_list else "- Nicht spezifiziert"

        return template.format(
            req_id=requirement.requirement_id,
            title=requirement.title,
            description=requirement.description,
            acceptance_criteria=ac_formatted
        )

    async def generate_diagram(
        self,
        requirement: Any,
        diagram_type: str
    ) -> Optional[str]:
        """
        Generate a Mermaid diagram for a requirement.

        Args:
            requirement: RequirementNode object
            diagram_type: Type of diagram (flowchart, sequence, class, er, state, c4)
                          Also accepts full Mermaid names (sequenceDiagram, classDiagram, etc.)

        Returns:
            Mermaid code as string, or None if generation failed
        """
        if not self._initialized:
            await self.initialize()

        # Normalize diagram type (handles both short and full Mermaid names)
        original_type = diagram_type
        diagram_type = self.normalize_type(diagram_type)

        if diagram_type not in self.DIAGRAM_TYPES:
            print(f"  Warning: Unknown diagram type '{original_type}', using flowchart")
            diagram_type = "flowchart"

        # Generate with optional validation and retry
        mermaid_code = await self._generate_with_retry(requirement, diagram_type)

        return mermaid_code

    async def _generate_with_retry(
        self,
        requirement: Any,
        diagram_type: str,
        previous_errors: Optional[List[str]] = None,
        attempt: int = 1
    ) -> Optional[str]:
        """
        Generate diagram with validation and retry logic.

        Args:
            requirement: RequirementNode object
            diagram_type: Normalized diagram type
            previous_errors: Errors from previous attempt (for retry feedback)
            attempt: Current attempt number

        Returns:
            Validated mermaid code or None
        """
        # Build prompt (with error feedback if retrying)
        prompt = self._build_prompt(requirement, diagram_type)

        if previous_errors and attempt > 1:
            error_feedback = "\n".join(f"- {e}" for e in previous_errors)
            prompt += f"\n\nWICHTIG: Der vorherige Versuch hatte Syntaxfehler:\n{error_feedback}\n\nBitte korrigiere diese Fehler im neuen Diagramm."

        try:
            # Call the LLM API directly
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "Du bist ein Experte für Mermaid-Diagramme. Gib NUR den Mermaid-Code aus, keine Erklärungen. Formatiere den Code mit ```mermaid Markdown-Blöcken. Achte auf korrekte Syntax!"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3 if attempt == 1 else 0.1,  # Lower temp for retries
                max_tokens=2000
            )

            if response and response.choices:
                content = response.choices[0].message.content

                if content:
                    # Extract mermaid from response
                    _, mermaid_code = MermaidOutputHandler.extract_mermaid_block(content)

                    if not mermaid_code:
                        # Maybe the response IS the mermaid code without wrapper
                        content_clean = content.strip()
                        for dtype in MermaidOutputHandler.MERMAID_DIAGRAM_TYPES:
                            if content_clean.startswith(dtype):
                                mermaid_code = content_clean
                                break

                    if not mermaid_code:
                        print(f"  Warning: No mermaid code found in response for {requirement.requirement_id}/{diagram_type}")
                        return None

                    # Validate if enabled
                    if self.validate:
                        self.validation_stats["total"] += 1
                        validation_result = MermaidValidator.validate(
                            mermaid_code,
                            method=self.validation_method
                        )

                        if validation_result.is_valid:
                            self.validation_stats["valid"] += 1
                            if attempt > 1:
                                self.validation_stats["fixed_after_retry"] += 1
                            return mermaid_code
                        else:
                            self.validation_stats["invalid"] += 1
                            errors_str = "; ".join(validation_result.errors[:3])  # Show first 3 errors
                            print(f"  Validation failed for {requirement.requirement_id}/{diagram_type}: {errors_str}")

                            # Retry if enabled and within limits
                            if self.retry_on_error and attempt < self.max_retries:
                                self.validation_stats["retried"] += 1
                                print(f"  Retrying (attempt {attempt + 1}/{self.max_retries})...")
                                return await self._generate_with_retry(
                                    requirement,
                                    diagram_type,
                                    previous_errors=validation_result.errors,
                                    attempt=attempt + 1
                                )

                            # Return based on skip_invalid setting
                            if self.skip_invalid:
                                print(f"  Skipping invalid diagram")
                                return None
                            else:
                                print(f"  Returning diagram despite validation errors (skip_invalid=False)")
                                return mermaid_code

                    return mermaid_code
            else:
                print(f"  Warning: Empty response for {requirement.requirement_id}/{diagram_type}")
                return None

        except Exception as e:
            print(f"  Error generating {diagram_type} for {requirement.requirement_id}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_validation_stats(self) -> Dict[str, Any]:
        """Get validation statistics."""
        stats = self.validation_stats.copy()
        if stats["total"] > 0:
            stats["success_rate"] = stats["valid"] / stats["total"]
            stats["retry_success_rate"] = (
                stats["fixed_after_retry"] / stats["retried"]
                if stats["retried"] > 0 else 0
            )
        else:
            stats["success_rate"] = 0
            stats["retry_success_rate"] = 0
        return stats

    def print_validation_summary(self):
        """Print a summary of validation statistics."""
        stats = self.get_validation_stats()
        print(f"\n  Validation Summary:")
        print(f"    Total generated: {stats['total']}")
        print(f"    Valid: {stats['valid']} ({stats['success_rate']:.1%})")
        print(f"    Invalid: {stats['invalid']}")
        print(f"    Retried: {stats['retried']}")
        print(f"    Fixed after retry: {stats['fixed_after_retry']}")

    async def generate_all_diagrams_for_requirement(
        self,
        requirement: Any,
        diagram_types: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """
        Generate all diagram types for a single requirement.

        Args:
            requirement: RequirementNode object
            diagram_types: List of diagram types to generate (default: all)
                           Accepts both short names and full Mermaid names.

        Returns:
            Dictionary mapping diagram type to mermaid code.
            Keys use the normalized short names for consistency.
        """
        types_to_generate = diagram_types or self.DIAGRAM_TYPES
        results = {}

        for dtype in types_to_generate:
            # Normalize for display and storage
            normalized = self.normalize_type(dtype)
            print(f"  Generating {normalized} diagram for {requirement.requirement_id}...")
            mermaid = await self.generate_diagram(requirement, dtype)
            if mermaid:
                # Store with normalized name for consistency
                results[normalized] = mermaid

        return results

    async def generate_diagrams_for_all_requirements(
        self,
        requirements: List[Any],
        diagram_types: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, str]]:
        """
        Generate diagrams for all requirements.

        Args:
            requirements: List of RequirementNode objects
            diagram_types: List of diagram types to generate (default: all)

        Returns:
            Nested dictionary: {requirement_id: {diagram_type: mermaid_code}}
        """
        if not self._initialized:
            await self.initialize()

        results = {}
        total = len(requirements)

        for i, req in enumerate(requirements):
            print(f"\nProcessing requirement {i+1}/{total}: {req.requirement_id}")
            req_diagrams = await self.generate_all_diagrams_for_requirement(req, diagram_types)
            results[req.requirement_id] = req_diagrams

        return results


async def test_generator():
    """Test the KiloDiagramGenerator with a sample requirement."""
    from dataclasses import dataclass, field
    from typing import List

    @dataclass
    class MockRequirement:
        requirement_id: str = "REQ-001"
        title: str = "User Login"
        description: str = "Users shall be able to log in with email and password"
        acceptance_criteria: List[str] = field(default_factory=lambda: [
            "User enters valid email and password",
            "System validates credentials",
            "User is redirected to dashboard on success"
        ])

    # Create generator
    generator = KiloDiagramGenerator()
    await generator.initialize()

    # Create mock requirement
    req = MockRequirement()

    # Generate a flowchart
    print("\nGenerating flowchart for login requirement...")
    flowchart = await generator.generate_diagram(req, "flowchart")

    if flowchart:
        print("\n=== Generated Flowchart ===")
        print(f"```mermaid\n{flowchart}\n```")
    else:
        print("Failed to generate flowchart")

    return flowchart is not None


if __name__ == "__main__":
    # Run test
    success = asyncio.run(test_generator())
    sys.exit(0 if success else 1)
