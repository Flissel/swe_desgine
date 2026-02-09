"""
Mermaid Syntax Validator - Validates Mermaid diagram syntax.

Supports multiple validation strategies:
- Pattern-based (fast, no dependencies)
- Kroki API (online, high accuracy)
- mmdc CLI (requires Node.js, highest accuracy)
"""

import re
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """Result of Mermaid syntax validation."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    diagram_type: Optional[str] = None
    method_used: str = "pattern"


class MermaidValidator:
    """
    Validates Mermaid diagram syntax using multiple strategies.

    Strategies (in order of preference):
    1. pattern - Fast regex-based validation (no dependencies)
    2. kroki - Online API validation (requires internet)
    3. mmdc - Mermaid CLI validation (requires Node.js)
    """

    # Valid diagram types
    DIAGRAM_TYPES = [
        'flowchart', 'graph', 'sequenceDiagram', 'classDiagram',
        'stateDiagram', 'stateDiagram-v2', 'erDiagram', 'gantt',
        'pie', 'journey', 'gitgraph', 'mindmap', 'timeline',
        'quadrantChart', 'requirementDiagram', 'C4Context'
    ]

    # Syntax patterns for each diagram type
    SYNTAX_PATTERNS: Dict[str, List[Tuple[str, str, bool]]] = {
        # (pattern, error_message, is_required)
        'flowchart': [
            (r'flowchart\s+(TD|TB|BT|LR|RL)', 'Flowchart requires direction (TD, TB, BT, LR, or RL)', True),
            (r'--+>', 'Flowchart should have arrow connections (-->)', False),
        ],
        'graph': [
            (r'graph\s+(TD|TB|BT|LR|RL)', 'Graph requires direction (TD, TB, BT, LR, or RL)', True),
        ],
        'sequenceDiagram': [
            (r'sequenceDiagram', 'Must start with sequenceDiagram', True),
            (r'(participant|actor)\s+\w+', 'Sequence diagram should have participants or actors', False),
        ],
        'classDiagram': [
            (r'classDiagram', 'Must start with classDiagram', True),
            (r'class\s+\w+', 'Class diagram should define classes', False),
        ],
        'erDiagram': [
            (r'erDiagram', 'Must start with erDiagram', True),
            (r'\w+\s*(\|\||\|o|o\||\}o|o\{|\}\||\|\{)', 'ER diagram should have relationships', False),
        ],
        'stateDiagram': [
            (r'stateDiagram(-v2)?', 'Must start with stateDiagram or stateDiagram-v2', True),
            (r'\[\*\]|state\s+\w+', 'State diagram should have states', False),
        ],
        'stateDiagram-v2': [
            (r'stateDiagram-v2', 'Must start with stateDiagram-v2', True),
        ],
        'C4Context': [
            (r'C4Context', 'Must start with C4Context', True),
            (r'(Person|System|Container|Component)\s*\(', 'C4 diagram should have C4 elements', False),
        ],
    }

    # Common syntax errors to check across all diagram types
    COMMON_ERRORS: List[Tuple[str, str]] = [
        (r'--+>\s*$', 'Arrow with no target node'),
        (r'--+>\s*\n\s*\n', 'Arrow followed by empty line (missing target)'),
        (r'\(\s*\)', 'Empty parentheses'),
        (r'\[\s*\]', 'Empty square brackets'),
        (r'\{\s*\}(?!\s*-->)', 'Empty curly braces (except in arrows)'),
    ]

    # Bracket pairs to check for balance
    BRACKET_PAIRS = [
        ('(', ')'),
        ('[', ']'),
        ('{', '}'),
    ]

    @classmethod
    def detect_diagram_type(cls, code: str) -> Optional[str]:
        """Detect the diagram type from Mermaid code."""
        if not code:
            return None

        first_line = code.strip().split('\n')[0].strip().lower()

        # Check each diagram type
        for dtype in cls.DIAGRAM_TYPES:
            if first_line.startswith(dtype.lower()):
                return dtype

        # Special case for graph (alias for flowchart)
        if first_line.startswith('graph'):
            return 'graph'

        return None

    @classmethod
    def validate(
        cls,
        code: str,
        method: str = 'pattern',
        expected_type: Optional[str] = None
    ) -> ValidationResult:
        """
        Validate Mermaid diagram syntax.

        Args:
            code: Mermaid diagram code
            method: Validation method ('pattern', 'kroki', 'mmdc')
            expected_type: Expected diagram type (optional)

        Returns:
            ValidationResult with validation details
        """
        if not code or not code.strip():
            return ValidationResult(
                is_valid=False,
                errors=['Empty Mermaid code'],
                method_used=method
            )

        # Normalize code
        code = code.strip()

        # Detect diagram type
        diagram_type = cls.detect_diagram_type(code)

        if method == 'pattern':
            return cls._validate_pattern(code, diagram_type, expected_type)
        elif method == 'kroki':
            return cls._validate_kroki(code, diagram_type)
        elif method == 'mmdc':
            return cls._validate_mmdc(code, diagram_type)
        else:
            # Default to pattern
            return cls._validate_pattern(code, diagram_type, expected_type)

    @classmethod
    def _validate_pattern(
        cls,
        code: str,
        diagram_type: Optional[str],
        expected_type: Optional[str] = None
    ) -> ValidationResult:
        """Pattern-based validation (no external dependencies)."""
        errors = []
        warnings = []

        # Check if diagram type was detected
        if not diagram_type:
            errors.append('No valid diagram type found. Code must start with: flowchart, sequenceDiagram, classDiagram, erDiagram, stateDiagram, C4Context, etc.')
            return ValidationResult(
                is_valid=False,
                errors=errors,
                warnings=warnings,
                diagram_type=None,
                method_used='pattern'
            )

        # Check if type matches expected
        if expected_type:
            normalized_expected = expected_type.lower().replace('-', '')
            normalized_actual = diagram_type.lower().replace('-', '')
            if normalized_expected != normalized_actual:
                # Allow some aliases
                aliases = {
                    'flowchart': ['graph'],
                    'statediagram': ['statediagramv2'],
                }
                is_alias = normalized_actual in aliases.get(normalized_expected, [])
                if not is_alias:
                    warnings.append(f'Expected {expected_type} but found {diagram_type}')

        # Get type-specific patterns
        patterns = cls.SYNTAX_PATTERNS.get(diagram_type, [])

        for pattern, message, is_required in patterns:
            if not re.search(pattern, code, re.IGNORECASE | re.MULTILINE):
                if is_required:
                    errors.append(message)
                else:
                    warnings.append(message)

        # Check common errors
        lines = code.split('\n')
        for line_num, line in enumerate(lines, 1):
            for pattern, message in cls.COMMON_ERRORS:
                if re.search(pattern, line):
                    errors.append(f'Line {line_num}: {message}')

        # Check bracket balance
        for open_b, close_b in cls.BRACKET_PAIRS:
            open_count = code.count(open_b)
            close_count = code.count(close_b)
            if open_count != close_count:
                errors.append(f'Unbalanced brackets: {open_count} "{open_b}" vs {close_count} "{close_b}"')

        # Check for duplicate node definitions (flowchart/graph only)
        if diagram_type in ['flowchart', 'graph']:
            node_defs = re.findall(r'^[\s]*([A-Za-z][A-Za-z0-9_]*)\s*[\[\(\{]', code, re.MULTILINE)
            seen = {}
            for node in node_defs:
                if node in seen:
                    warnings.append(f'Node "{node}" defined multiple times')
                seen[node] = True

        # Check for very short diagrams (likely incomplete)
        if len(lines) < 3:
            warnings.append('Diagram seems very short (less than 3 lines)')

        is_valid = len(errors) == 0

        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            diagram_type=diagram_type,
            method_used='pattern'
        )

    @classmethod
    def _validate_kroki(cls, code: str, diagram_type: Optional[str]) -> ValidationResult:
        """Validate using Kroki.io API (requires internet)."""
        try:
            import requests
        except ImportError:
            # Fall back to pattern validation
            result = cls._validate_pattern(code, diagram_type)
            result.warnings.append('requests library not available, using pattern validation')
            return result

        try:
            response = requests.post(
                'https://kroki.io/mermaid/svg',
                data=code.encode('utf-8'),
                headers={'Content-Type': 'text/plain'},
                timeout=10
            )

            if response.status_code == 200:
                return ValidationResult(
                    is_valid=True,
                    errors=[],
                    warnings=[],
                    diagram_type=diagram_type,
                    method_used='kroki'
                )
            else:
                # Extract error message from response
                error_msg = response.text[:500] if response.text else f'HTTP {response.status_code}'
                return ValidationResult(
                    is_valid=False,
                    errors=[f'Kroki validation failed: {error_msg}'],
                    warnings=[],
                    diagram_type=diagram_type,
                    method_used='kroki'
                )

        except requests.exceptions.Timeout:
            # Fall back to pattern validation
            result = cls._validate_pattern(code, diagram_type)
            result.warnings.append('Kroki API timeout, using pattern validation')
            return result
        except requests.exceptions.RequestException as e:
            # Fall back to pattern validation
            result = cls._validate_pattern(code, diagram_type)
            result.warnings.append(f'Kroki API error: {str(e)}, using pattern validation')
            return result

    @classmethod
    def _validate_mmdc(cls, code: str, diagram_type: Optional[str]) -> ValidationResult:
        """Validate using mmdc CLI (requires Node.js and mermaid-cli)."""
        import subprocess
        import tempfile
        import os

        try:
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
                        is_valid=True,
                        errors=[],
                        warnings=[],
                        diagram_type=diagram_type,
                        method_used='mmdc'
                    )
                else:
                    error_msg = result.stderr or result.stdout or 'Unknown mmdc error'
                    return ValidationResult(
                        is_valid=False,
                        errors=[f'mmdc validation failed: {error_msg}'],
                        warnings=[],
                        diagram_type=diagram_type,
                        method_used='mmdc'
                    )
            finally:
                # Cleanup temp files
                if os.path.exists(temp_input):
                    os.unlink(temp_input)
                if os.path.exists(temp_output):
                    os.unlink(temp_output)

        except FileNotFoundError:
            # mmdc not installed, fall back to pattern
            result = cls._validate_pattern(code, diagram_type)
            result.warnings.append('mmdc not found, using pattern validation')
            return result
        except subprocess.TimeoutExpired:
            result = cls._validate_pattern(code, diagram_type)
            result.warnings.append('mmdc timeout, using pattern validation')
            return result
        except Exception as e:
            result = cls._validate_pattern(code, diagram_type)
            result.warnings.append(f'mmdc error: {str(e)}, using pattern validation')
            return result

    @classmethod
    def validate_batch(
        cls,
        diagrams: Dict[str, str],
        method: str = 'pattern'
    ) -> Dict[str, ValidationResult]:
        """
        Validate multiple diagrams.

        Args:
            diagrams: Dict mapping diagram_id to mermaid code
            method: Validation method

        Returns:
            Dict mapping diagram_id to ValidationResult
        """
        results = {}
        for diagram_id, code in diagrams.items():
            results[diagram_id] = cls.validate(code, method)
        return results

    @classmethod
    def get_validation_summary(
        cls,
        results: Dict[str, ValidationResult]
    ) -> Dict[str, Any]:
        """
        Get summary statistics for validation results.

        Args:
            results: Dict of validation results

        Returns:
            Summary statistics
        """
        total = len(results)
        valid = sum(1 for r in results.values() if r.is_valid)
        invalid = total - valid

        all_errors = []
        all_warnings = []

        for diagram_id, result in results.items():
            for error in result.errors:
                all_errors.append(f'{diagram_id}: {error}')
            for warning in result.warnings:
                all_warnings.append(f'{diagram_id}: {warning}')

        return {
            'total': total,
            'valid': valid,
            'invalid': invalid,
            'success_rate': valid / total if total > 0 else 0,
            'errors': all_errors,
            'warnings': all_warnings,
        }


# Quick test function
def test_validator():
    """Test the MermaidValidator with sample diagrams."""

    # Valid flowchart
    valid_flowchart = """flowchart TD
    Start([Start]) --> Process[Process]
    Process --> Decision{Decision?}
    Decision -->|Yes| End([End])
    Decision -->|No| Process
"""

    # Invalid flowchart (missing direction)
    invalid_flowchart = """flowchart
    Start --> End
"""

    # Valid sequence diagram
    valid_sequence = """sequenceDiagram
    participant User
    participant System
    User->>System: Request
    System-->>User: Response
"""

    # Invalid (empty)
    invalid_empty = ""

    # Test cases
    test_cases = [
        ('valid_flowchart', valid_flowchart),
        ('invalid_flowchart', invalid_flowchart),
        ('valid_sequence', valid_sequence),
        ('invalid_empty', invalid_empty),
    ]

    print("=== MermaidValidator Test ===\n")

    for name, code in test_cases:
        result = MermaidValidator.validate(code)
        status = "VALID" if result.is_valid else "INVALID"
        print(f"{name}: {status}")
        print(f"  Type: {result.diagram_type}")
        if result.errors:
            print(f"  Errors: {result.errors}")
        if result.warnings:
            print(f"  Warnings: {result.warnings}")
        print()

    return True


if __name__ == '__main__':
    test_validator()
