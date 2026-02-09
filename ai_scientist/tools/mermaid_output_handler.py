"""
MermaidOutputHandler - Unescape and normalize mermaid diagram output.

Handles the double-escaping issue when kilocode output goes through
AutoGen JSON serialization:
  - kilocode returns raw markdown with \n
  - AutoGen wraps in JSON, escaping to \\n
  - File gets written with literal \n instead of actual newlines
"""

import json
import re
from typing import Tuple, Optional, List


class MermaidOutputHandler:
    """Handles mermaid diagram output normalization."""

    MERMAID_DIAGRAM_TYPES = [
        'flowchart', 'sequenceDiagram', 'classDiagram', 'stateDiagram',
        'erDiagram', 'gantt', 'pie', 'journey', 'gitgraph', 'mindmap',
        'timeline', 'quadrantChart', 'requirementDiagram', 'C4Context'
    ]

    @classmethod
    def strip_ansi_codes(cls, content: str) -> str:
        """
        Remove ANSI escape codes from terminal output.

        Handles both actual escape codes and their string representations:
        - Actual CSI sequences: \x1b[...
        - String literal: \\x1b[...
        - OSC sequences: \x1b]...
        - Other escape sequences
        """
        if not content:
            return content

        # First handle escaped string representations (\\x1b or \x1b as literals)
        # These appear when output goes through repr() or JSON serialization
        content = re.sub(r'\\x1b\[[0-9;?]*[a-zA-Z]', '', content)
        content = re.sub(r'\\x1b\][^\x07\\]*(?:\\x07|\\x1b\\\\)?', '', content)
        content = re.sub(r'\\x1b[()][AB012]', '', content)

        # Then handle actual escape codes
        # Standard CSI sequences: \x1b[...
        ansi_escape = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]')
        content = ansi_escape.sub('', content)

        # OSC sequences: \x1b]...BEL or ST
        osc_escape = re.compile(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?')
        content = osc_escape.sub('', content)

        # Other escape sequences
        other_escape = re.compile(r'\x1b[()][AB012]')
        content = other_escape.sub('', content)

        # Remove control characters that might slip through
        content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', content)

        # Remove single braces/brackets on their own line (terminal cleanup artifacts)
        content = re.sub(r'^[}\]]+\s*$', '', content, flags=re.MULTILINE)
        content = re.sub(r'^\s*[{}]\s*$', '', content, flags=re.MULTILINE)

        # Remove common terminal artifact patterns
        content = re.sub(r'\}\}\n+', '', content)
        content = re.sub(r'^\s*\}\s*$', '', content, flags=re.MULTILINE)

        # Reduce multiple blank lines
        content = re.sub(r'\n{3,}', '\n\n', content)

        return content.strip()

    @classmethod
    def unescape_content(cls, content: str) -> str:
        """
        Fully unescape JSON-encoded content.

        Handles:
        - ANSI escape codes (terminal output)
        - \\n -> \n (double-escaped newlines)
        - \\r -> \r
        - \\t -> \t
        - \\" -> "
        - \\\\ -> \\
        - Repeated escaping (\\\\n -> \n)
        """
        if not content:
            return content

        # First strip ANSI escape codes
        content = cls.strip_ansi_codes(content)

        # Try to detect if content is a JSON string (starts with ")
        if content.startswith('"') and content.endswith('"'):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                pass

        # Handle JSON array output from kilocode
        if content.strip().startswith('[') and content.strip().endswith(']'):
            try:
                parsed = json.loads(content)
                if isinstance(parsed, list) and len(parsed) > 0:
                    # Join array elements with newlines
                    content = '\n'.join(str(item) for item in parsed)
            except json.JSONDecodeError:
                pass

        # Handle multiple levels of escaping (up to 3 levels deep)
        for _ in range(3):
            prev_content = content
            content = content.replace('\\\\n', '\\n')
            content = content.replace('\\\\r', '\\r')
            content = content.replace('\\\\t', '\\t')
            content = content.replace('\\\\"', '\\"')
            if content == prev_content:
                break

        # Final unescape
        content = content.replace('\\n', '\n')
        content = content.replace('\\r', '\r')
        content = content.replace('\\t', '\t')
        content = content.replace('\\"', '"')
        content = content.replace('\\\\', '\\')

        return content

    @classmethod
    def extract_mermaid_block(cls, content: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract mermaid diagram from markdown content.

        Returns:
            Tuple of (diagram_type, mermaid_code) or (None, None)
        """
        content = cls.unescape_content(content)

        # Pattern for ```mermaid ... ``` blocks
        mermaid_pattern = r'```mermaid\s*([\s\S]*?)```'
        match = re.search(mermaid_pattern, content, re.IGNORECASE)

        if match:
            mermaid_code = match.group(1).strip()
            diagram_type = cls.detect_diagram_type(mermaid_code)
            return diagram_type, mermaid_code

        # Check if content IS a mermaid diagram (no markdown wrapper)
        for dtype in cls.MERMAID_DIAGRAM_TYPES:
            if content.strip().startswith(dtype):
                return dtype, content.strip()

        return None, None

    @classmethod
    def extract_all_mermaid_blocks(cls, content: str) -> List[Tuple[str, str]]:
        """
        Extract all mermaid diagrams from markdown content.

        Returns:
            List of tuples (diagram_type, mermaid_code)
        """
        content = cls.unescape_content(content)
        results = []

        # Pattern for ```mermaid ... ``` blocks
        mermaid_pattern = r'```mermaid\s*([\s\S]*?)```'
        matches = re.findall(mermaid_pattern, content, re.IGNORECASE)

        for match in matches:
            mermaid_code = match.strip()
            diagram_type = cls.detect_diagram_type(mermaid_code)
            results.append((diagram_type, mermaid_code))

        return results

    @classmethod
    def detect_diagram_type(cls, mermaid_code: str) -> str:
        """Detect the type of mermaid diagram from code."""
        first_line = mermaid_code.strip().split('\n')[0].strip()

        for dtype in cls.MERMAID_DIAGRAM_TYPES:
            if first_line.lower().startswith(dtype.lower()):
                return dtype

        return 'unknown'

    @classmethod
    def normalize_mermaid(cls, mermaid_code: str) -> str:
        """
        Normalize mermaid code for consistent storage.

        - Removes leading/trailing whitespace
        - Ensures consistent newline format (LF only)
        - Removes empty lines at start/end
        """
        code = cls.unescape_content(mermaid_code)

        # Normalize line endings
        code = code.replace('\r\n', '\n').replace('\r', '\n')

        # Remove leading/trailing empty lines
        lines = code.split('\n')
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()

        return '\n'.join(lines)

    @classmethod
    def wrap_in_markdown(cls, mermaid_code: str) -> str:
        """Wrap mermaid code in markdown code block."""
        code = cls.normalize_mermaid(mermaid_code)
        return f"```mermaid\n{code}\n```"

    @classmethod
    def handle_json_array_output(cls, content: str) -> List[str]:
        """
        Handle kilocode output that returns JSON array.

        Sometimes kilocode returns results as ["item1", "item2", ...]
        """
        content = cls.unescape_content(content)

        try:
            if content.strip().startswith('['):
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
        except json.JSONDecodeError:
            pass

        return [content]

    @classmethod
    def fix_malformed_markdown(cls, content: str) -> str:
        """
        Fix malformed markdown file content.

        Handles cases where:
        - Content starts with ["...] (JSON array as string)
        - Literal \\n instead of newlines
        - Missing mermaid code block wrappers
        """
        content = cls.unescape_content(content)

        # If content starts with [ and contains mermaid-like syntax, try to parse
        if content.strip().startswith('[') and ('-->' in content or '---' in content):
            # This is likely a malformed JSON array containing mermaid
            try:
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    content = '\n'.join(str(item) for item in parsed)
            except json.JSONDecodeError:
                # Remove the leading [ if it looks like broken output
                if content.strip().startswith('["'):
                    content = content.strip()[2:]  # Remove ["
                    if content.endswith('"]'):
                        content = content[:-2]  # Remove "]

        # Apply unescape again after potential JSON handling
        content = cls.unescape_content(content)

        return content
