"""
Mermaid Diagram Validator - Validates Mermaid diagram syntax.

Inspired by AI-Scientist's code execution validation approach.
Validates diagrams using pattern matching or external tools.
"""

from typing import Optional, List, Tuple
from dataclasses import dataclass
import re
import subprocess
import logging

logger = logging.getLogger("diagram-validator")


@dataclass
class ValidationResult:
    """Result of diagram validation."""
    valid: bool
    diagram_type: str
    errors: Optional[List[str]] = None
    warnings: Optional[List[str]] = None
    fixed_code: Optional[str] = None


# Mermaid diagram type patterns
DIAGRAM_PATTERNS = {
    "flowchart": r"^(flowchart|graph)\s+(TD|TB|BT|RL|LR)",
    "sequenceDiagram": r"^sequenceDiagram",
    "classDiagram": r"^classDiagram",
    "erDiagram": r"^erDiagram",
    "stateDiagram": r"^stateDiagram(-v2)?",
    "gantt": r"^gantt",
    "pie": r"^pie",
    "C4Context": r"^C4Context",
    "C4Container": r"^C4Container",
    "C4Component": r"^C4Component",
}

# Common syntax errors and fixes
COMMON_FIXES = [
    # Fix missing arrows
    (r"(\w+)\s+(\w+)", r"\1 --> \2"),
    # Fix unquoted labels with special chars
    (r'\[([^"\]]*[<>&][^"\]]*)\]', r'["\1"]'),
    # Fix missing semicolons in sequences
    (r"(\w+)->>(\w+):\s*([^\n;]+)(?=\n)", r"\1->>\2: \3;"),
]


class DiagramValidator:
    """
    Validates Mermaid diagram syntax using pattern-based or tool-based validation.

    Similar to AI-Scientist's code execution for hypothesis testing,
    but adapted for diagram validation.
    """

    def __init__(
        self,
        method: str = "pattern",  # "pattern", "kroki", "mmdc"
        retry_on_error: bool = True,
        max_retries: int = 2
    ):
        """
        Initialize the validator.

        Args:
            method: Validation method - "pattern" (fast), "kroki" (API), "mmdc" (CLI)
            retry_on_error: Whether to retry generation on error
            max_retries: Maximum retry attempts
        """
        self.method = method
        self.retry_on_error = retry_on_error
        self.max_retries = max_retries

    def validate(self, mermaid_code: str) -> ValidationResult:
        """
        Validate a Mermaid diagram.

        Args:
            mermaid_code: Mermaid diagram code

        Returns:
            ValidationResult with validity status and any errors
        """
        # Detect diagram type
        diagram_type = self._detect_diagram_type(mermaid_code)

        if self.method == "pattern":
            return self._validate_pattern(mermaid_code, diagram_type)
        elif self.method == "kroki":
            return self._validate_kroki(mermaid_code, diagram_type)
        elif self.method == "mmdc":
            return self._validate_mmdc(mermaid_code, diagram_type)
        else:
            return self._validate_pattern(mermaid_code, diagram_type)

    def _detect_diagram_type(self, code: str) -> str:
        """Detect the type of Mermaid diagram."""
        code_stripped = code.strip()
        for dtype, pattern in DIAGRAM_PATTERNS.items():
            if re.match(pattern, code_stripped, re.MULTILINE):
                return dtype
        return "unknown"

    def _validate_pattern(self, code: str, diagram_type: str) -> ValidationResult:
        """
        Validate using pattern matching (fast, offline).

        Checks for common syntax errors without external tools.
        """
        errors = []
        warnings = []

        lines = code.strip().split("\n")

        # Check for diagram type declaration
        if diagram_type == "unknown":
            errors.append("Unknown or missing diagram type declaration")

        # Check for balanced brackets
        bracket_count = {"[": 0, "]": 0, "(": 0, ")": 0, "{": 0, "}": 0}
        for line in lines:
            for char in line:
                if char in bracket_count:
                    bracket_count[char] += 1

        if bracket_count["["] != bracket_count["]"]:
            errors.append(f"Unbalanced square brackets: [ = {bracket_count['[']}, ] = {bracket_count[']']}")
        if bracket_count["("] != bracket_count[")"]:
            errors.append(f"Unbalanced parentheses: ( = {bracket_count['(']}, ) = {bracket_count[')']}")
        if bracket_count["{"] != bracket_count["}"]:
            errors.append(f"Unbalanced curly braces: {{ = {bracket_count['{']}, }} = {bracket_count['}']}")

        # Check for empty diagram
        if len(lines) <= 1:
            errors.append("Diagram appears to be empty or too short")

        # Type-specific validation
        if diagram_type == "flowchart":
            errors.extend(self._validate_flowchart(code))
        elif diagram_type == "sequenceDiagram":
            errors.extend(self._validate_sequence(code))
        elif diagram_type == "classDiagram":
            errors.extend(self._validate_class(code))
        elif diagram_type == "erDiagram":
            errors.extend(self._validate_er(code))

        # Check for common issues
        if "undefined" in code.lower():
            warnings.append("Code contains 'undefined' - may indicate generation issues")
        if "todo" in code.lower() or "fixme" in code.lower():
            warnings.append("Code contains TODO/FIXME markers")

        return ValidationResult(
            valid=len(errors) == 0,
            diagram_type=diagram_type,
            errors=errors if errors else None,
            warnings=warnings if warnings else None
        )

    def _validate_flowchart(self, code: str) -> List[str]:
        """Validate flowchart-specific syntax."""
        errors = []

        # Check for node connections
        if not re.search(r"(-->|---|\|>|--o|--x)", code):
            errors.append("Flowchart has no connections between nodes")

        # Check for node definitions
        if not re.search(r"\w+\[", code) and not re.search(r"\w+\(", code):
            errors.append("Flowchart has no node definitions")

        return errors

    def _validate_sequence(self, code: str) -> List[str]:
        """Validate sequence diagram syntax."""
        errors = []

        # Check for participants
        if not re.search(r"(participant|actor)", code, re.IGNORECASE):
            # Not strictly required, but recommended
            pass

        # Check for messages
        if not re.search(r"(->>|-->>|->|-->)", code):
            errors.append("Sequence diagram has no message arrows")

        return errors

    def _validate_class(self, code: str) -> List[str]:
        """Validate class diagram syntax."""
        errors = []

        # Check for class definitions
        if not re.search(r"class\s+\w+", code):
            errors.append("Class diagram has no class definitions")

        return errors

    def _validate_er(self, code: str) -> List[str]:
        """Validate ER diagram syntax."""
        errors = []

        # Check for entity definitions
        if not re.search(r"\w+\s*\{", code):
            errors.append("ER diagram has no entity definitions")

        # Check for relationships
        if not re.search(r"(\|\|--|--\|\||\|o--|--o\||\}o--|--o\{)", code):
            errors.append("ER diagram has no relationship definitions")

        return errors

    def _validate_kroki(self, code: str, diagram_type: str) -> ValidationResult:
        """
        Validate using Kroki API (requires internet).

        Kroki is a free diagram rendering service.
        """
        try:
            import requests
            import base64
            import zlib

            # Encode diagram for Kroki
            encoded = base64.urlsafe_b64encode(
                zlib.compress(code.encode('utf-8'), 9)
            ).decode('ascii')

            # Try to render (HEAD request to check validity)
            url = f"https://kroki.io/mermaid/svg/{encoded}"
            response = requests.head(url, timeout=10)

            if response.status_code == 200:
                return ValidationResult(
                    valid=True,
                    diagram_type=diagram_type
                )
            else:
                return ValidationResult(
                    valid=False,
                    diagram_type=diagram_type,
                    errors=[f"Kroki returned status {response.status_code}"]
                )

        except ImportError:
            logger.warning("requests library not available, falling back to pattern validation")
            return self._validate_pattern(code, diagram_type)
        except Exception as e:
            logger.error(f"Kroki validation failed: {e}")
            return ValidationResult(
                valid=False,
                diagram_type=diagram_type,
                errors=[f"Kroki validation error: {str(e)}"]
            )

    def _validate_mmdc(self, code: str, diagram_type: str) -> ValidationResult:
        """
        Validate using Mermaid CLI (mmdc).

        Requires mermaid-cli to be installed: npm install -g @mermaid-js/mermaid-cli
        """
        try:
            import tempfile
            import os

            # Write code to temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.mmd', delete=False) as f:
                f.write(code)
                temp_input = f.name

            temp_output = temp_input.replace('.mmd', '.svg')

            try:
                # Run mmdc
                result = subprocess.run(
                    ['mmdc', '-i', temp_input, '-o', temp_output],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode == 0:
                    return ValidationResult(
                        valid=True,
                        diagram_type=diagram_type
                    )
                else:
                    return ValidationResult(
                        valid=False,
                        diagram_type=diagram_type,
                        errors=[result.stderr] if result.stderr else ["mmdc validation failed"]
                    )

            finally:
                # Cleanup temp files
                if os.path.exists(temp_input):
                    os.remove(temp_input)
                if os.path.exists(temp_output):
                    os.remove(temp_output)

        except FileNotFoundError:
            logger.warning("mmdc not found, falling back to pattern validation")
            return self._validate_pattern(code, diagram_type)
        except subprocess.TimeoutExpired:
            return ValidationResult(
                valid=False,
                diagram_type=diagram_type,
                errors=["mmdc validation timed out"]
            )
        except Exception as e:
            logger.error(f"mmdc validation failed: {e}")
            return ValidationResult(
                valid=False,
                diagram_type=diagram_type,
                errors=[f"mmdc validation error: {str(e)}"]
            )

    def try_fix(self, code: str, errors: List[str]) -> Tuple[str, bool]:
        """
        Attempt to fix common syntax errors.

        Args:
            code: Original Mermaid code
            errors: List of errors from validation

        Returns:
            Tuple of (fixed_code, was_fixed)
        """
        fixed = code
        was_fixed = False

        for pattern, replacement in COMMON_FIXES:
            new_code = re.sub(pattern, replacement, fixed)
            if new_code != fixed:
                fixed = new_code
                was_fixed = True

        return fixed, was_fixed


def validate_mermaid(diagram_code: str, method: str = "pattern") -> ValidationResult:
    """
    Convenience function to validate a Mermaid diagram.

    Args:
        diagram_code: Mermaid diagram code
        method: Validation method

    Returns:
        ValidationResult
    """
    validator = DiagramValidator(method=method)
    return validator.validate(diagram_code)
