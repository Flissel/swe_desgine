#!/usr/bin/env python
"""Test script for KiloDiagramGenerator."""

import asyncio
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))


@dataclass
class MockRequirement:
    """Mock requirement for testing."""
    requirement_id: str = "REQ-001"
    title: str = "User Login"
    description: str = "Users shall be able to log in with email and password"
    acceptance_criteria: List[str] = field(default_factory=lambda: [
        "Validate email format",
        "Check password against database",
        "Create session token on success",
        "Redirect to dashboard"
    ])


async def test_kilo_diagram_generator():
    """Test the KiloDiagramGenerator."""
    from requirements_engineer.diagrams.kilo_diagram_generator import KiloDiagramGenerator

    print("=" * 60)
    print("Testing KiloDiagramGenerator")
    print("=" * 60)

    # Create generator
    print("\n1. Initializing generator...")
    generator = KiloDiagramGenerator()
    await generator.initialize()

    # Create mock requirement
    req = MockRequirement()
    print(f"\n2. Test requirement: {req.requirement_id} - {req.title}")

    # Generate flowchart
    print("\n3. Generating flowchart diagram...")
    flowchart = await generator.generate_diagram(req, "flowchart")

    if flowchart:
        print("\nSUCCESS! Generated Mermaid flowchart:")
        print("-" * 40)
        print(f"```mermaid\n{flowchart}\n```")
        print("-" * 40)

        # Save to file
        output_path = Path("test_flowchart_output.mmd")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(flowchart)
        print(f"\nSaved to: {output_path}")
        return True
    else:
        print("\nFAILED: No mermaid code generated")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_kilo_diagram_generator())
    print(f"\n{'=' * 60}")
    print(f"Test result: {'PASSED' if success else 'FAILED'}")
    print("=" * 60)
    sys.exit(0 if success else 1)
